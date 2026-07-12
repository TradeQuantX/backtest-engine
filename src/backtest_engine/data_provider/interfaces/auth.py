"""
Authentication interface for data providers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, slots=True)
class AuthConfig:
    """Base authentication configuration."""
    provider: str
    api_key: str
    api_secret: Optional[str] = None
    access_token: Optional[str] = None
    extra: Optional[dict] = None


@dataclass(frozen=True, slots=True)
class ZerodhaAuthConfig(AuthConfig):
    """Zerodha-specific authentication configuration."""
    request_token: Optional[str] = None
    redirect_url: Optional[str] = None
    totp_secret: Optional[str] = None


@dataclass(frozen=True, slots=True)
class DhanAuthConfig(AuthConfig):
    """Dhan-specific authentication configuration."""
    client_id: Optional[str] = None
    static_ip: Optional[str] = None


class AuthProviderProtocol(ABC):
    """Abstract base class for authentication providers."""
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider name this auth handles."""
        ...
    
    @abstractmethod
    async def authenticate(self, config: AuthConfig) -> str:
        """
        Perform authentication and return access token.
        
        Args:
            config: Authentication configuration
            
        Returns:
            Access token string
            
        Raises:
            AuthError: If authentication fails
        """
        ...
    
    @abstractmethod
    async def refresh_token(self, config: AuthConfig) -> str:
        """
        Refresh expired access token.
        
        Args:
            config: Authentication configuration
            
        Returns:
            New access token string
        """
        ...
    
    @abstractmethod
    async def validate_token(self, token: str) -> bool:
        """
        Validate if token is still valid.
        
        Args:
            token: Access token to validate
            
        Returns:
            True if valid, False otherwise
        """
        ...
    
    @abstractmethod
    async def logout(self, token: str) -> bool:
        """
        Invalidate token (logout).
        
        Args:
            token: Access token to invalidate
            
        Returns:
            True if successful
        """
        ...