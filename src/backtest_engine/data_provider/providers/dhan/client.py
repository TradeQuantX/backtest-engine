"""
DhanHQ provider implementation.
"""

from datetime import datetime
from typing import Optional

import httpx

from backtest_engine.data_provider.config import DhanConfig
from backtest_engine.data_provider.exceptions import (
    AuthError,
    InstrumentNotFoundError,
    ProviderResponseError,
    RateLimitExceededError,
    TokenExpiredError,
)
from backtest_engine.data_provider.interfaces import (
    HistoricalDataRequest,
    HistoricalDataResponse,
    NormalizedInstrument,
)
from backtest_engine.data_provider.providers.base import BaseProvider
from backtest_engine.data_provider.providers.registry import ProviderRegistry
from backtest_engine.data_provider.providers.dhan.auth import DhanAuthHelper
from backtest_engine.data_provider.utils import (
    dhan_instrument_to_normalized,
    dhan_ohlc_to_normalized,
    normalize_exchange,
    normalize_instrument_type,
    normalize_interval,
    normalize_segment,
    normalize_timestamp,
)


class DhanProvider(BaseProvider):
    """DhanHQ data provider."""
    
    name = "dhan"
    supported_exchanges = ["NSE", "BSE", "NFO", "BFO", "MCX", "CDS"]
    supported_intervals = ["1", "5", "15", "30", "60", "day"]
    
    BASE_URL = "https://api.dhan.co"
    SANDBOX_URL = "https://sandbox.dhan.co"
    
    def __init__(self, config: DhanConfig, global_config, cache=None, storage=None):
        super().__init__(config, global_config, cache, storage)
        self._client: Optional[httpx.AsyncClient] = None
        self._auth_helper = DhanAuthHelper(config)
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            base_url = self.SANDBOX_URL if self.config.sandbox else self.BASE_URL
            self._client = httpx.AsyncClient(
                base_url=base_url,
                timeout=httpx.Timeout(
                    connect=self.config.connect_timeout,
                    read=self.config.read_timeout,
                ),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "TradeQuantX/1.0",
                },
            )
        return self._client
    
    def _get_auth_headers(self) -> dict:
        """Get authorization headers."""
        if not self._access_token:
            raise AuthError("Not authenticated", provider=self.name)
        return {
            "access-token": self._access_token,
        }
    
    async def _do_authenticate(self) -> str:
        """
        Authenticate with DhanHQ using the auth helper.
        
        Returns access token.
        """
        client = await self._get_client()
        return await self._auth_helper.authenticate(client)
    
    async def _do_get_instruments(
        self,
        exchange: Optional[str] = None,
        segment: Optional[str] = None,
    ) -> list[NormalizedInstrument]:
        """Fetch instrument master from DhanHQ."""
        client = await self._get_client()
        
        # Dhan provides a single instrument master file
        response = await client.get(
            "/v2/instruments",
            headers=self._get_auth_headers(),
        )
        
        if response.status_code != 200:
            raise ProviderResponseError(
                f"Failed to fetch instruments: {response.text}",
                status_code=response.status_code,
                provider=self.name,
            )
        
        data = response.json()
        instruments = []
        
        for item in data:
            # Filter by exchange/segment if specified
            if exchange and item.get("exchangeSegment") != exchange:
                continue
            if segment and item.get("instrument") != segment:
                continue
            
            instrument = dhan_instrument_to_normalized(item, self.name)
            instruments.append(instrument)
        
        return instruments
    
    async def _do_get_historical_data(
        self,
        request: HistoricalDataRequest,
    ) -> HistoricalDataResponse:
        """Fetch historical data from DhanHQ."""
        # Get security ID
        security_id = await self.get_instrument_token(
            request.symbol,
            request.exchange.value,
            request.segment.value,
        )
        
        if not security_id:
            raise InstrumentNotFoundError(
                f"Instrument not found: {request.symbol}",
                symbol=request.symbol,
                exchange=request.exchange.value,
                provider=self.name,
            )
        
        # Map interval
        interval_map = {
            "1minute": "1",
            "5minute": "5",
            "15minute": "15",
            "30minute": "30",
            "60minute": "60",
            "day": "day",
        }
        
        dhan_interval = interval_map.get(request.interval.value, "5")
        
        # Determine endpoint
        is_intraday = dhan_interval != "day"
        endpoint = "/v2/charts/intraday" if is_intraday else "/v2/charts/historical"
        
        # Build request body
        body = {
            "securityId": security_id,
            "exchangeSegment": self._map_exchange_segment(request.exchange, request.segment),
            "instrument": self._map_instrument_type(request.segment),
            "interval": dhan_interval,
            "fromDate": request.from_date.strftime("%Y-%m-%d"),
            "toDate": request.to_date.strftime("%Y-%m-%d"),
        }
        
        if request.oi:
            body["oi"] = "true"
        
        if not is_intraday and request.segment.value == "FO":
            body["expiryCode"] = 0  # Current expiry
        
        client = await self._get_client()
        response = await client.post(
            endpoint,
            json=body,
            headers=self._get_auth_headers(),
        )
        
        if response.status_code == 401:
            raise TokenExpiredError("Access token expired", provider=self.name)
        elif response.status_code == 429:
            raise RateLimitExceededError("Rate limit exceeded", provider=self.name)
        elif response.status_code != 200:
            raise ProviderResponseError(
                f"Historical data request failed: {response.text}",
                status_code=response.status_code,
                provider=self.name,
            )
        
        data = response.json()
        
        # Dhan returns data in format: {open: [], high: [], low: [], close: [], volume: [], timestamp: []}
        normalized = dhan_ohlc_to_normalized(
            data,
            request.symbol,
            request.exchange,
            request.segment,
            request.interval,
            self.name,
        )
        
        return HistoricalDataResponse(
            data=normalized,
            symbol=request.symbol,
            exchange=request.exchange,
            segment=request.segment,
            interval=request.interval,
            from_date=request.from_date,
            to_date=request.to_date,
            provider=self.name,
        )
    
    def _map_exchange_segment(self, exchange, segment) -> str:
        """Map exchange and segment to Dhan exchange segment."""
        if exchange.value == "NSE" and segment.value == "EQ":
            return "NSE_EQ"
        elif exchange.value == "BSE" and segment.value == "EQ":
            return "BSE_EQ"
        elif exchange.value == "NSE" and segment.value == "FO":
            return "NSE_FNO"
        elif exchange.value == "BSE" and segment.value == "FO":
            return "BSE_FNO"
        elif exchange.value == "MCX":
            return "MCX_COMM"
        elif exchange.value == "CDS":
            return "NSE_CDS"
        return "NSE_EQ"
    
    def _map_instrument_type(self, segment) -> str:
        """Map segment to Dhan instrument type."""
        if segment.value == "EQ":
            return "EQUITY"
        elif segment.value == "FO":
            return "FUTURES"  # or OPTIONS
        elif segment.value == "CDS":
            return "CURRENCY"
        elif segment.value == "MCX":
            return "COMMODITY"
        return "EQUITY"
    
    async def _do_get_instrument_token(
        self,
        symbol: str,
        exchange: str,
        segment: str,
        expiry: Optional[datetime] = None,
        strike: Optional[float] = None,
        instrument_type: Optional[str] = None,
    ) -> Optional[str]:
        """Get security ID from instrument master."""
        instruments = await self.get_instruments(exchange, segment)
        
        for inst in instruments:
            if inst.symbol == symbol:
                if expiry and inst.expiry != expiry:
                    continue
                if strike and inst.strike != strike:
                    continue
                if instrument_type and inst.instrument_type.value != instrument_type:
                    continue
                return inst.instrument_token
        
        return None
    
    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()