"""
Exception hierarchy for the data provider layer.

All exceptions inherit from DataProviderError for easy catching.
"""

from .auth import (
    AuthError,
    InvalidCredentialsError,
    InvalidTokenError,
    OAuthFlowError,
    SessionInvalidatedError,
    TokenExpiredError,
    TokenNotFoundError,
    TokenStorageError,
)
from .base import (
    ConfigurationError,
    DataProviderError,
    InvalidConfigurationError,
    ProviderNotFoundError,
)
from .data import (
    DataCorruptionError,
    DataError,
    DataNotFoundError,
    InsufficientDataError,
    SchemaMismatchError,
    ValidationError,
)
from .provider import (
    InstrumentNotFoundError,
    ProviderError,
    ProviderMaintenanceError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    UnsupportedIntervalError,
)
from .rate_limit import (
    QuotaExceededError,
    RateLimitError,
    RateLimitExceededError,
    RequestThrottledError,
)

__all__ = [
    # Base
    "DataProviderError",
    "ConfigurationError",
    "ProviderNotFoundError",
    "InvalidConfigurationError",
    # Auth
    "AuthError",
    "TokenExpiredError",
    "InvalidCredentialsError",
    "OAuthFlowError",
    "TokenNotFoundError",
    "TokenStorageError",
    "InvalidTokenError",
    "SessionInvalidatedError",
    # Rate Limit
    "RateLimitError",
    "RateLimitExceededError",
    "QuotaExceededError",
    "RequestThrottledError",
    # Data
    "DataError",
    "DataNotFoundError",
    "DataCorruptionError",
    "ValidationError",
    "SchemaMismatchError",
    "InsufficientDataError",
    # Provider
    "ProviderError",
    "ProviderUnavailableError",
    "ProviderResponseError",
    "ProviderTimeoutError",
    "ProviderMaintenanceError",
    "InstrumentNotFoundError",
    "UnsupportedIntervalError",
]