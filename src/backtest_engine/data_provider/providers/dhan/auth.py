"""
DhanHQ authentication helper.

Extracted from DhanProvider to provide reusable authentication logic.
Handles JWT token validation and file-based token storage.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

from backtest_engine.data_provider.config import DhanConfig
from backtest_engine.data_provider.exceptions import (
    AuthError,
)
from backtest_engine.data_provider.utils import IST


class DhanAuthHelper:
    """
    Handles DhanHQ authentication.
    
    Dhan uses simple JWT tokens (24-hour expiry) generated from web.dhan.co.
    No OAuth flow - user provides token manually.
    
    Provides:
    - JWT token validation via profile API
    - Secure file-based token storage (chmod 600)
    - Sandbox/production URL handling
    """
    
    def __init__(self, config: DhanConfig):
        self.config = config
    
    @property
    def base_url(self) -> str:
        """Get base URL (sandbox or production)."""
        return self.config.sandbox_url if self.config.sandbox else self.config.base_url
    
    @property
    def profile_url(self) -> str:
        """Get profile endpoint URL."""
        return f"{self.base_url}/v2/profile"
    
    async def authenticate(self, http_client: httpx.AsyncClient) -> str:
        """
        Authenticate with DhanHQ using provided access token.
        
        Returns:
            Valid access token string
            
        Raises:
            AuthError: If token validation fails
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
        
        # 3. No valid token available
        raise AuthError(
            "No valid access token provided. Generate one from web.dhan.co",
            provider="dhan",
        )
    
    async def validate_token(self, http_client: httpx.AsyncClient, token: str) -> bool:
        """Validate access token by calling user profile."""
        try:
            response = await http_client.get(
                self.profile_url,
                headers={"access-token": token},
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
            "client_id": self.config.client_id,
            "saved_at": datetime.now(IST).isoformat(),
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
        """
        Logout - Dhan doesn't have a server-side logout endpoint.
        Just deletes local token file.
        """
        await self._delete_token()
        return True
    
    async def _delete_token(self) -> bool:
        """Delete local token file."""
        token_file = Path(self.config.token_file).expanduser()
        if token_file.exists():
            token_file.unlink()
            return True
        return False