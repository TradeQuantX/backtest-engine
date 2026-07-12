"""
Rate limiting exceptions.
"""

from typing import Optional

from backtest_engine.data_provider.exceptions.base import DataProviderError


class RateLimitError(DataProviderError):
    """Base rate limit error."""
    
    def __init__(
        self,
        message: str,
        provider: Optional[str] = None,
        retry_after: Optional[float] = None,
        limit: Optional[int] = None,
        remaining: Optional[int] = None,
        reset_at: Optional[float] = None,
        **kwargs,
    ):
        super().__init__(message, provider, **kwargs)
        self.retry_after = retry_after
        self.limit = limit
        self.remaining = remaining
        self.reset_at = reset_at


class RateLimitExceededError(RateLimitError):
    """Rate limit exceeded - too many requests."""
    pass


class QuotaExceededError(RateLimitError):
    """Daily/monthly quota exceeded."""
    pass


class RequestThrottledError(RateLimitError):
    """Request throttled by provider."""
    pass