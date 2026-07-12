"""
Zerodha Kite Connect provider implementation.
"""

import hashlib
import hmac
import json
from datetime import datetime
from typing import Optional
from urllib.parse import urlencode

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
from backtest_engine.data_provider.providers.registry import register_provider
from backtest_engine.data_provider.utils import (
    normalize_exchange,
    normalize_instrument_type,
    normalize_interval,
    normalize_segment,
    normalize_timestamp,
    zerodha_instrument_to_normalized,
    zerodha_ohlc_to_normalized,
)


@register_provider
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
            raise AuthenticationError("Not authenticated", provider=self.name)
        return {
            "Authorization": f"token {self.config.api_key}:{self._access_token}",
        }
    
    async def _do_authenticate(self) -> str:
        """
        Authenticate with Zerodha.
        
        For MVP: Uses CLI wizard with browser redirect.
        Returns access token.
        """
        # Check if we have a valid token in config
        if self.config.access_token:
            if await self._validate_token(self.config.access_token):
                self._access_token = self.config.access_token
                return self._access_token
        
        # Try loading saved token from file
        saved_token = await self._load_token()
        if saved_token:
            if await self._validate_token(saved_token):
                self._access_token = saved_token
                return self._access_token
        
        # Need to run OAuth flow
        return await self._run_oauth_flow()
    
    async def _run_oauth_flow(self) -> str:
        """
        Run OAuth flow with browser redirect.
        
        This is the CLI wizard approach:
        1. Generate login URL
        2. Open browser
        3. Wait for redirect with request_token
        4. Exchange request_token for access_token
        """
        import webbrowser
        from http.server import HTTPServer, BaseHTTPRequestHandler
        import threading
        import urllib.parse
        from urllib.parse import urlparse
        
        # Parse redirect_url to get host and port for callback server
        redirect_url = self.config.redirect_url
        parsed_url = urlparse(redirect_url)
        callback_host = parsed_url.hostname or "localhost"
        callback_port = parsed_url.port or 8080
        
        # Generate login URL
        login_url = (
            f"{self.LOGIN_URL}?"
            f"v=3&api_key={self.config.api_key}"
            f"&redirect_url={urllib.parse.quote(redirect_url)}"
        )
        
        # Server to capture redirect
        request_token = None
        error = None
        
        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                nonlocal request_token, error
                query = urllib.parse.urlparse(self.path).query
                params = urllib.parse.parse_qs(query)
                
                if "request_token" in params:
                    request_token = params["request_token"][0]
                    self.send_response(200)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()
                    self.wfile.write(b"<h1>Authentication successful! You can close this window.</h1>")
                elif "error" in params:
                    error = params["error"][0]
                    self.send_response(400)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()
                    self.wfile.write(f"<h1>Authentication failed: {error}</h1>".encode())
                else:
                    self.send_response(400)
                    self.end_headers()
                
                # Shutdown server
                threading.Thread(target=self.server.shutdown).start()
            
            def log_message(self, format, *args):
                pass  # Suppress logs
        
        # Start callback server on the same host/port as redirect_url
        server = HTTPServer((callback_host, callback_port), CallbackHandler)
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        
        try:
            # Open browser
            print(f"Opening browser for Zerodha login...")
            print(f"If browser doesn't open, visit: {login_url}")
            webbrowser.open(login_url)
            
            # Wait for callback
            server_thread.join(timeout=120)
            
            if error:
                raise OAuthFlowError(f"OAuth error: {error}", provider=self.name)
            
            if not request_token:
                raise OAuthFlowError("No request token received", provider=self.name)
            
            # Exchange request_token for access_token
            access_token = await self._exchange_token(request_token)
            return access_token
            
        finally:
            server.shutdown()
    
    async def _exchange_token(self, request_token: str) -> str:
        """Exchange request_token for access_token."""
        checksum = hashlib.sha256(
            f"{self.config.api_key}{request_token}{self.config.api_secret}".encode()
        ).hexdigest()
        
        client = await self._get_client()
        response = await client.post(
            "/session/token",
            data={
                "api_key": self.config.api_key,
                "request_token": request_token,
                "checksum": checksum,
            },
            headers={"X-Kite-Version": "3"},
        )
        
        if response.status_code != 200:
            raise OAuthFlowError(
                f"Token exchange failed: {response.text}",
                provider=self.name,
            )
        
        data = response.json()
        if data.get("status") != "success":
            raise OAuthFlowError(
                f"Token exchange failed: {data.get('message', 'Unknown error')}",
                provider=self.name,
            )
        
        access_token = data["data"]["access_token"]
        self._user_id = data["data"]["user_id"]
        
        # Save token
        await self._save_token(access_token)
        
        return access_token
    
    async def _validate_token(self, token: str) -> bool:
        """Validate access token by calling user profile."""
        try:
            client = await self._get_client()
            response = await client.get(
                "/user/profile",
                headers={"Authorization": f"token {self.config.api_key}:{token}"},
            )
            return response.status_code == 200
        except Exception:
            return False
    
    async def _save_token(self, token: str) -> None:
        """Save token to file."""
        import os
        from pathlib import Path
        
        token_file = Path(self.config.token_file).expanduser()
        token_file.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "access_token": token,
            "api_key": self.config.api_key,
            "user_id": self._user_id,
            "saved_at": datetime.utcnow().isoformat(),
        }
        
        with open(token_file, "w") as f:
            json.dump(data, f)
        
        # Restrict permissions
        os.chmod(token_file, 0o600)
    
    async def _load_token(self) -> Optional[str]:
        """Load token from file."""
        from pathlib import Path
        
        token_file = Path(self.config.token_file).expanduser()
        if not token_file.exists():
            return None
        
        try:
            with open(token_file) as f:
                data = json.load(f)
            return data.get("access_token")
        except Exception:
            return None
    
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
        
        # Build request
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