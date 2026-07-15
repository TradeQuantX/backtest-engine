"""
Zerodha Kite Connect provider implementation.
"""

import asyncio
from datetime import datetime
from typing import Optional

import httpx

from backtest_engine.data_provider.config import ZerodhaConfig
from backtest_engine.data_provider.exceptions import (
    AuthError,
    InstrumentNotFoundError,
    OAuthFlowError,
    ProviderResponseError,
    RateLimitExceededError,
    TokenExpiredError,
    UnsupportedIntervalError,
)
from backtest_engine.data_provider.interfaces import (
    HistoricalDataRequest,
    HistoricalDataResponse,
    NormalizedInstrument,
)
from backtest_engine.data_provider.providers.base import BaseProvider
from backtest_engine.data_provider.providers.registry import ProviderRegistry
from backtest_engine.data_provider.providers.zerodha.auth import ZerodhaAuthHelper
from backtest_engine.data_provider.utils import (
    normalize_exchange,
    normalize_instrument_type,
    normalize_interval,
    normalize_segment,
    normalize_timestamp,
    zerodha_instrument_to_normalized,
    zerodha_ohlc_to_normalized,
)


class ZerodhaProvider(BaseProvider):
    """Zerodha Kite Connect data provider."""
    
    name = "zerodha"
    supported_exchanges = ["NSE", "BSE", "NFO", "BFO", "CDS", "MCX", "BCD", "MF"]
    supported_intervals = [
        "minute", "3minute", "5minute", "10minute",
        "15minute", "30minute", "60minute", "day"
    ]
    
    BASE_URL = "https://api.kite.trade"
    LOGIN_URL = "https://kite.zerodha.com/connect/login"
    TOKEN_URL = "https://api.kite.trade/session/token"
    
    def __init__(self, config: ZerodhaConfig, global_config, cache=None, storage=None):
        super().__init__(config, global_config, cache, storage)
        self._client: Optional[httpx.AsyncClient] = None
        self._user_id: Optional[str] = None
        self._auth_helper = ZerodhaAuthHelper(config)
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                timeout=httpx.Timeout(
                    connect=self.config.connect_timeout,
                    read=self.config.read_timeout,
                    write=self.config.read_timeout,
                    pool=self.config.connect_timeout,
                ),
                headers={
                    "X-Kite-Version": "3",
                    "User-Agent": "TradeQuantX/1.0",
                },
            )
        return self._client
    
    def _get_auth_headers(self) -> dict:
        """Get authorization headers."""
        if not self._access_token:
            raise AuthError("Not authenticated", provider=self.name)
        return {
            "Authorization": f"token {self.config.api_key}:{self._access_token}",
        }
    
    async def _do_authenticate(self) -> str:
        """
        Authenticate with Zerodha using the auth helper.
        
        Returns access token.
        """
        client = await self._get_client()
        token = await self._auth_helper.authenticate(client)
        self._user_id = self._auth_helper.user_id
        return token
    
    async def _do_get_instruments(
        self,
        exchange: Optional[str] = None,
        segment: Optional[str] = None,
    ) -> list[NormalizedInstrument]:
        """Fetch instrument master from Zerodha."""
        client = await self._get_client()
        
        # Determine which exchanges to fetch
        exchanges = [exchange] if exchange else ["NSE", "BSE", "NFO", "BFO", "CDS", "MCX"]
        
        all_instruments = []
        errors = []
        
        for exch in exchanges:
            response = await client.get(
                f"/instruments/{exch}",
                headers=self._get_auth_headers(),
            )
            
            if response.status_code == 401 or response.status_code == 403:
                # Authentication failed - token is invalid/expired
                raise AuthError(
                    f"Authentication failed for {exch}: {response.text}",
                    provider=self.name,
                )
            
            if response.status_code != 200:
                errors.append(f"{exch}: HTTP {response.status_code} - {response.text}")
                continue
            
            # Parse CSV response
            import csv
            from io import StringIO
            
            csv_data = response.text
            reader = csv.DictReader(StringIO(csv_data))
            
            for row in reader:
                # Normalize segment first, then filter
                instrument = zerodha_instrument_to_normalized(row, self.name)
                
                # Filter by segment if specified (compare normalized segment)
                if segment and instrument.segment.value != segment:
                    continue
                
                all_instruments.append(instrument)
        
        if not all_instruments and errors:
            raise ProviderResponseError(
                f"Failed to fetch instruments: {'; '.join(errors)}",
                provider=self.name,
            )
        
        return all_instruments
    
    async def _do_get_historical_data(
        self,
        request: HistoricalDataRequest,
    ) -> HistoricalDataResponse:
        """Fetch historical data from Zerodha."""
        # Get instrument token
        instrument_token = await self.get_instrument_token(
            request.symbol,
            request.exchange.value,
            request.segment.value,
        )
        
        if not instrument_token:
            raise InstrumentNotFoundError(
                f"Instrument not found: {request.symbol}",
                symbol=request.symbol,
                exchange=request.exchange.value,
                provider=self.name,
            )
        
        # Map interval
        interval_map = {
            "1minute": "minute",
            "3minute": "3minute",
            "5minute": "5minute",
            "10minute": "10minute",
            "15minute": "15minute",
            "30minute": "30minute",
            "60minute": "60minute",
            "day": "day",
        }
        
        kite_interval = interval_map.get(request.interval.value, "minute")
        
        # Build request - dates are already IST-aware
        params = {
            "from": request.from_date.strftime("%Y-%m-%d %H:%M:%S"),
            "to": request.to_date.strftime("%Y-%m-%d %H:%M:%S"),
        }
        
        if request.continuous:
            params["continuous"] = "1"
        if request.oi:
            params["oi"] = "1"
        
        client = await self._get_client()
        response = await client.get(
            f"/instruments/historical/{instrument_token}/{kite_interval}",
            params=params,
            headers=self._get_auth_headers(),
        )
        
        if response.status_code == 403:
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
        if data.get("status") != "success":
            raise ProviderResponseError(
                f"API error: {data.get('message', 'Unknown error')}",
                provider=self.name,
            )
        
        candles = data.get("data", {}).get("candles", [])
        normalized = zerodha_ohlc_to_normalized(
            candles,
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
    
    async def _do_get_instrument_token(
        self,
        symbol: str,
        exchange: str,
        segment: str,
        expiry: Optional[datetime] = None,
        strike: Optional[float] = None,
        instrument_type: Optional[str] = None,
    ) -> Optional[str]:
        """Get instrument token from master."""
        instruments = await self.get_instruments(exchange, segment)
        
        for inst in instruments:
            if inst.symbol == symbol:
                # For derivatives, match expiry and strike
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