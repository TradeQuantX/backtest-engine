"""
Authentication implementations for data providers.
"""

import asyncio
import hashlib
import json
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Optional
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import urllib.parse

import httpx

from backtest_engine.data_provider.config import DhanConfig, ZerodhaConfig
from backtest_engine.data_provider.exceptions import (
    AuthenticationError,
    OAuthFlowError,
    TokenExpiredError,
    TokenNotFoundError,
    TokenStorageError,
)
from backtest_engine.data_provider.interfaces import AuthConfig, AuthProviderProtocol


class TokenStore:
    """Secure token storage with encryption."""
    
    def __init__(self, token_dir: Path):
        self.token_dir = Path(token_dir).expanduser().resolve()
        self.token_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_token_file(self, provider: str) -> Path:
        return self.token_dir / f"{provider}.json"
    
    async def save_token(
        self,
        provider: str,
        access_token: str,
        api_key: str = "",
        extra: Optional[dict] = None,
    ) -> None:
        """Save token to encrypted file."""
        file_path = self._get_token_file(provider)
        
        data = {
            "access_token": access_token,
            "api_key": api_key,
            "saved_at": datetime.utcnow().isoformat(),
            "extra": extra or {},
        }
        
        try:
            with open(file_path, "w") as f:
                json.dump(data, f)
            file_path.chmod(0o600)
        except Exception as e:
            raise TokenStorageError(f"Failed to save token: {e}")
    
    async def load_token(self, provider: str) -> Optional[dict]:
        """Load token from file."""
        file_path = self._get_token_file(provider)
        
        if not file_path.exists():
            return None
        
        try:
            with open(file_path) as f:
                return json.load(f)
        except Exception:
            return None
    
    async def delete_token(self, provider: str) -> bool:
        """Delete token file."""
        file_path = self._get_token_file(provider)
        if file_path.exists():
            file_path.unlink()
            return True
        return False


class ZerodhaAuthProvider(AuthProviderProtocol):
    """Zerodha Kite Connect authentication provider."""
    
    name = "zerodha"
    
    def __init__(self, token_store: TokenStore):
        self.token_store = token_store
    
    async def authenticate(self, config: AuthConfig) -> str:
        """Authenticate with Zerodha."""
        if not isinstance(config, ZerodhaAuthConfig):
            raise AuthenticationError("Invalid config type for Zerodha")
        
        # Try loading existing token
        token_data = await self.token_store.load_token(self.name)
        if token_data and token_data.get("access_token"):
            if await self.validate_token(token_data["access_token"]):
                return token_data["access_token"]
        
        # If we have request_token, exchange it
        if config.request_token:
            return await self._exchange_request_token(config)
        
        # Run OAuth flow
        return await self._run_oauth_flow(config)
    
    async def _exchange_request_token(self, config: ZerodhaAuthConfig) -> str:
        """Exchange request_token for access_token."""
        checksum = hashlib.sha256(
            f"{config.api_key}{config.request_token}{config.api_secret}".encode()
        ).hexdigest()
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.kite.trade/session/token",
                data={
                    "api_key": config.api_key,
                    "request_token": config.request_token,
                    "checksum": checksum,
                },
                headers={"X-Kite-Version": "3"},
            )
        
        if response.status_code != 200:
            raise OAuthFlowError(f"Token exchange failed: {response.text}")
        
        data = response.json()
        if data.get("status") != "success":
            raise OAuthFlowError(f"Token exchange failed: {data.get('message')}")
        
        access_token = data["data"]["access_token"]
        
        # Save token
        await self.token_store.save_token(
            self.name,
            access_token,
            config.api_key,
            {"user_id": data["data"]["user_id"]},
        )
        
        return access_token
    
    async def _run_oauth_flow(self, config: ZerodhaAuthConfig) -> str:
        """Run OAuth flow with browser redirect."""
        # Generate login URL
        login_url = (
            f"https://kite.zerodha.com/connect/login?"
            f"v=3&api_key={config.api_key}"
            f"&redirect_url={urllib.parse.quote(config.redirect_url)}"
        )
        
        # Parse redirect_url to get host and port for callback server
        parsed_url = urllib.parse.urlparse(config.redirect_url)
        callback_host = parsed_url.hostname or "localhost"
        callback_port = parsed_url.port or 8080
        
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
                pass
        
        # Start callback server on the same host/port as redirect_url
        server = HTTPServer((callback_host, callback_port), CallbackHandler)
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        
        try:
            print(f"Opening browser for Zerodha login...")
            print(f"If browser doesn't open, visit: {login_url}")
            webbrowser.open(login_url)
            
            server_thread.join(timeout=120)
            
            if error:
                raise OAuthFlowError(f"OAuth error: {error}")
            
            if not request_token:
                raise OAuthFlowError("No request token received")
            
            # Exchange for access token
            config.request_token = request_token
            return await self._exchange_request_token(config)
            
        finally:
            server.shutdown()
    
    async def refresh_token(self, config: AuthConfig) -> str:
        """Refresh token (re-run OAuth for Zerodha)."""
        return await self.authenticate(config)
    
    async def validate_token(self, token: str) -> bool:
        """Validate access token."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.kite.trade/user/profile",
                    headers={"Authorization": f"token {config.api_key}:{token}"},
                )
            return response.status_code == 200
        except Exception:
            return False
    
    async def logout(self, token: str) -> bool:
        """Invalidate token."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    "https://api.kite.trade/session/token",
                    params={"api_key": config.api_key, "access_token": token},
                    headers={"X-Kite-Version": "3"},
                )
            return response.status_code == 200
        except Exception:
            return False


class DhanAuthProvider(AuthProviderProtocol):
    """DhanHQ authentication provider."""
    
    name = "dhan"
    
    def __init__(self, token_store: TokenStore):
        self.token_store = token_store
    
    async def authenticate(self, config: AuthConfig) -> str:
        """Authenticate with DhanHQ."""
        if not isinstance(config, DhanAuthConfig):
            raise AuthenticationError("Invalid config type for Dhan")
        
        # Try loading existing token
        token_data = await self.token_store.load_token(self.name)
        if token_data and token_data.get("access_token"):
            if await self.validate_token(token_data["access_token"]):
                return token_data["access_token"]
        
        # Use provided access token
        if config.access_token:
            if await self.validate_token(config.access_token):
                await self.token_store.save_token(
                    self.name,
                    config.access_token,
                    config.client_id,
                )
                return config.access_token
        
        raise AuthenticationError(
            "No valid access token. Generate one from web.dhan.co",
            provider=self.name,
        )
    
    async def refresh_token(self, config: AuthConfig) -> str:
        """Refresh token (re-authenticate for Dhan)."""
        return await self.authenticate(config)
    
    async def validate_token(self, token: str) -> bool:
        """Validate access token."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.dhan.co/v2/profile",
                    headers={"access-token": token},
                )
            return response.status_code == 200
        except Exception:
            return False
    
    async def logout(self, token: str) -> bool:
        """Dhan doesn't have a logout endpoint for tokens."""
        await self.token_store.delete_token(self.name)
        return True


class AuthManager:
    """Manages authentication for all providers."""
    
    def __init__(self, token_dir: Path):
        self.token_store = TokenStore(token_dir)
        self._providers: dict[str, AuthProviderProtocol] = {
            "zerodha": ZerodhaAuthProvider(self.token_store),
            "dhan": DhanAuthProvider(self.token_store),
        }
    
    def get_provider(self, name: str) -> Optional[AuthProviderProtocol]:
        """Get auth provider by name."""
        return self._providers.get(name)
    
    async def authenticate(
        self,
        provider: str,
        config: AuthConfig,
    ) -> str:
        """Authenticate with a provider."""
        auth_provider = self.get_provider(provider)
        if not auth_provider:
            raise AuthenticationError(f"Unknown provider: {provider}")
        
        return await auth_provider.authenticate(config)
    
    async def validate_token(self, provider: str, token: str) -> bool:
        """Validate token for a provider."""
        auth_provider = self.get_provider(provider)
        if not auth_provider:
            return False
        return await auth_provider.validate_token(token)
    
    async def logout(self, provider: str, token: str) -> bool:
        """Logout from a provider."""
        auth_provider = self.get_provider(provider)
        if not auth_provider:
            return False
        return await auth_provider.logout(token)