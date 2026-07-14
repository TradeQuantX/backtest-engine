"""
Zerodha Kite Connect authentication helper.

Extracted from ZerodhaProvider to provide reusable authentication logic.
Handles OAuth flow, token exchange, validation, and file-based token storage.
"""

import asyncio
import hashlib
import json
import urllib.parse
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
from aiohttp import web

from backtest_engine.data_provider.config import ZerodhaConfig
from backtest_engine.data_provider.exceptions import (
    AuthError,
    OAuthFlowError,
    TokenExpiredError,
)


class ZerodhaAuthHelper:
    """
    Handles Zerodha Kite Connect authentication.
    
    Provides:
    - OAuth 2.0 flow with browser redirect (aiohttp-based)
    - Request token → Access token exchange
    - Token validation via user profile API
    - Secure file-based token storage (chmod 600)
    """
    
    LOGIN_URL = "https://kite.zerodha.com/connect/login"
    TOKEN_URL = "https://api.kite.trade/session/token"
    PROFILE_URL = "https://api.kite.trade/user/profile"
    KITE_VERSION = "3"
    
    def __init__(self, config: ZerodhaConfig):
        self.config = config
        self._user_id: Optional[str] = None
    
    @property
    def user_id(self) -> Optional[str]:
        """Get the authenticated user ID."""
        return self._user_id
    
    async def authenticate(self, http_client: httpx.AsyncClient) -> str:
        """
        Perform full authentication flow.
        
        Returns:
            Valid access token string
            
        Raises:
            AuthError: If authentication fails
            OAuthFlowError: If OAuth flow fails
        """
        # 1. Try config access_token
        if self.config.access_token:
            if await self.validate_token(http_client, self.config.access_token):
                return self.config.access_token
        
        # 2. Try loading saved token
        saved_token = await self._load_token()
        if saved_token:
            if await self.validate_token(http_client, saved_token):
                return saved_token
        
        # 3. Run OAuth flow
        return await self._run_oauth_flow(http_client)
    
    async def _run_oauth_flow(self, http_client: httpx.AsyncClient) -> str:
        """
        Run OAuth flow with browser redirect using aiohttp.
        
        This is the CLI wizard approach:
        1. Generate login URL
        2. Open browser
        3. Wait for redirect with request_token
        4. Exchange request_token for access_token
        """
        # Parse redirect_url to get host and port for callback server
        redirect_url = self.config.redirect_url
        parsed_url = urlparse(redirect_url)
        callback_host = parsed_url.hostname or "localhost"
        callback_port = parsed_url.port or 8080
        
        # Generate login URL
        login_url = (
            f"{self.LOGIN_URL}?"
            f"v={self.KITE_VERSION}&api_key={self.config.api_key}"
            f"&redirect_url={redirect_url}"
        )
        
        # Server to capture redirect
        request_token = None
        error = None
        
        async def handle_callback(request):
            nonlocal request_token, error
            query = urlparse(str(request.url)).query
            params = {}
            for param in query.split("&"):
                if "=" in param:
                    k, v = param.split("=", 1)
                    params.setdefault(k, []).append(v)
            
            if "request_token" in params:
                request_token = params["request_token"][0]
                return web.Response(
                    text="<h1>Authentication successful! You can close this window.</h1>",
                    content_type="text/html"
                )
            elif "error" in params:
                error = params["error"][0]
                return web.Response(
                    text=f"<h1>Authentication failed: {error}</h1>",
                    content_type="text/html",
                    status=400
                )
            else:
                return web.Response(
                    text="<h1>Invalid callback</h1>",
                    content_type="text/html",
                    status=400
                )
        
        # Create aiohttp app
        app = web.Application()
        app.router.add_get("/", handle_callback)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, callback_host, callback_port)
        await site.start()
        
        try:
            # Open browser in thread pool to avoid blocking event loop
            print(f"Opening browser for Zerodha login...")
            print(f"If browser doesn't open, visit: {login_url}")
            import asyncio
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, webbrowser.open, login_url)
            
            # Wait for callback (with timeout)
            for _ in range(120):  # 120 seconds timeout
                if request_token or error:
                    break
                await asyncio.sleep(1)
            
            if error:
                raise OAuthFlowError(f"OAuth error: {error}", provider="zerodha")
            
            if not request_token:
                raise OAuthFlowError("No request token received (timeout)", provider="zerodha")
            
            # Exchange request_token for access_token
            access_token = await self._exchange_token(http_client, request_token)
            return access_token
            
        finally:
            await runner.cleanup()
    
    async def _exchange_token(self, http_client: httpx.AsyncClient, request_token: str) -> str:
        """Exchange request_token for access_token."""
        checksum = hashlib.sha256(
            f"{self.config.api_key}{request_token}{self.config.api_secret}".encode()
        ).hexdigest()
        
        response = await http_client.post(
            self.TOKEN_URL,
            data={
                "api_key": self.config.api_key,
                "request_token": request_token,
                "checksum": checksum,
            },
            headers={"X-Kite-Version": self.KITE_VERSION},
        )
        
        if response.status_code != 200:
            raise OAuthFlowError(
                f"Token exchange failed: {response.text}",
                provider="zerodha",
            )
        
        data = response.json()
        if data.get("status") != "success":
            raise OAuthFlowError(
                f"Token exchange failed: {data.get('message', 'Unknown error')}",
                provider="zerodha",
            )
        
        access_token = data["data"]["access_token"]
        self._user_id = data["data"]["user_id"]
        
        # Save token
        await self._save_token(access_token)
        
        return access_token
    
    async def validate_token(self, http_client: httpx.AsyncClient, token: str) -> bool:
        """Validate access token by calling user profile."""
        try:
            response = await http_client.get(
                self.PROFILE_URL,
                headers={"Authorization": f"token {self.config.api_key}:{token}"},
            )
            return response.status_code == 200
        except Exception:
            return False
    
    async def _save_token(self, token: str) -> None:
        """Save token to file with restricted permissions."""
        import os
        
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
        
        # Restrict permissions to owner read/write only
        os.chmod(token_file, 0o600)
    
    async def _load_token(self) -> Optional[str]:
        """Load token from file."""
        token_file = Path(self.config.token_file).expanduser()
        if not token_file.exists():
            return None
        
        try:
            with open(token_file) as f:
                data = json.load(f)
            return data.get("access_token")
        except Exception:
            return None
    
    async def logout(self, http_client: httpx.AsyncClient, token: str) -> bool:
        """Invalidate token on server and delete local file."""
        try:
            response = await http_client.delete(
                self.TOKEN_URL,
                params={"api_key": self.config.api_key, "access_token": token},
                headers={"X-Kite-Version": self.KITE_VERSION},
            )
            # Delete local token file regardless of server response
            await self._delete_token()
            return response.status_code == 200
        except Exception:
            await self._delete_token()
            return False
    
    async def _delete_token(self) -> bool:
        """Delete local token file."""
        token_file = Path(self.config.token_file).expanduser()
        if token_file.exists():
            token_file.unlink()
            return True
        return False