"""
Provider-specific exceptions.
"""

from typing import Optional

from backtest_engine.data_provider.exceptions.base import DataProviderError


class ProviderError(DataProviderError):
    """Base provider error."""
    pass


class ProviderUnavailableError(ProviderError):
    """Provider service is unavailable."""
    pass


class ProviderResponseError(ProviderError):
    """Provider returned an error response."""
    
    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        error_type: Optional[str] = None,
        error_code: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.status_code = status_code
        self.error_type = error_type
        self.error_code = error_code


class ProviderTimeoutError(ProviderError):
    """Provider request timed out."""
    pass


class ProviderMaintenanceError(ProviderError):
    """Provider is under maintenance."""
    pass


class InstrumentNotFoundError(ProviderError):
    """Instrument not found in provider's master."""
    
    def __init__(
        self,
        message: str,
        symbol: Optional[str] = None,
        exchange: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.symbol = symbol
        self.exchange = exchange


class UnsupportedIntervalError(ProviderError):
    """Requested interval not supported by provider."""
    
    def __init__(
        self,
        message: str,
        interval: Optional[str] = None,
        supported: Optional[list[str]] = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.interval = interval
        self.supported = supported