"""
Base exceptions for the data provider layer.
"""

from typing import Optional


class DataProviderError(Exception):
    """Base exception for all data provider errors."""
    
    def __init__(
        self,
        message: str,
        provider: Optional[str] = None,
        error_code: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.error_code = error_code
        self.details = details or {}
    
    def __str__(self) -> str:
        parts = [self.message]
        if self.provider:
            parts.append(f"provider={self.provider}")
        if self.error_code:
            parts.append(f"code={self.error_code}")
        return " | ".join(parts)


class ConfigurationError(DataProviderError):
    """Configuration-related errors."""
    pass


class ProviderNotFoundError(ConfigurationError):
    """Requested provider not found or not configured."""
    pass


class InvalidConfigurationError(ConfigurationError):
    """Invalid configuration provided."""
    pass