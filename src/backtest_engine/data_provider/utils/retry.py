"""
Retry logic with exponential backoff.

Provides configurable retry behavior for provider requests.
"""

import asyncio
import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from backtest_engine.data_provider.exceptions import (
    ProviderError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    RateLimitError,
)

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: float = 0.1  # 0-1, fraction of delay to add as jitter
    
    # Exception types to retry
    retryable_exceptions: tuple[type[Exception], ...] = (
        ProviderUnavailableError,
        ProviderTimeoutError,
        RateLimitError,
        ConnectionError,
        TimeoutError,
    )
    
    # Exception types to NOT retry
    non_retryable_exceptions: tuple[type[Exception], ...] = (
        ProviderError,  # Generic provider error - might be non-retryable
    )


@dataclass(frozen=True, slots=True)
class RetryResult:
    """Result of a retry operation."""
    success: bool
    attempts: int
    total_time: float
    last_exception: Exception | None = None
    result: Any = None


async def retry_with_backoff(
    func: Callable[..., T],
    *args,
    config: RetryConfig | None = None,
    **kwargs,
) -> RetryResult:
    """
    Execute function with exponential backoff retry.
    
    Args:
        func: Async function to execute
        *args: Positional arguments for func
        config: Retry configuration
        **kwargs: Keyword arguments for func
        
    Returns:
        RetryResult with success status and result or last exception
    """
    config = config or RetryConfig()
    start_time = asyncio.get_event_loop().time()
    last_exception = None
    
    for attempt in range(config.max_retries + 1):
        try:
            result = await func(*args, **kwargs)
            return RetryResult(
                success=True,
                attempts=attempt + 1,
                total_time=asyncio.get_event_loop().time() - start_time,
                result=result,
            )
        except config.non_retryable_exceptions as e:
            # Don't retry these
            last_exception = e
            break
        except config.retryable_exceptions as e:
            last_exception = e
            
            if attempt < config.max_retries:
                delay = min(
                    config.base_delay * (config.exponential_base ** attempt),
                    config.max_delay,
                )
                # Add jitter
                jitter_amount = delay * config.jitter * random.random()
                delay += jitter_amount
                
                await asyncio.sleep(delay)
            else:
                break
        except Exception as e:
            # Unknown exception - don't retry by default
            last_exception = e
            break
    
    return RetryResult(
        success=False,
        attempts=config.max_retries + 1,
        total_time=asyncio.get_event_loop().time() - start_time,
        last_exception=last_exception,
    )


def is_retryable_error(exception: Exception) -> bool:
    """Check if an exception is retryable."""
    retryable_types = (
        ProviderUnavailableError,
        ProviderTimeoutError,
        RateLimitError,
        ConnectionError,
        TimeoutError,
    )
    return isinstance(exception, retryable_types)


def get_retry_delay(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: float = 0.1,
) -> float:
    """Calculate delay for a given attempt number."""
    delay = min(base_delay * (exponential_base ** attempt), max_delay)
    jitter_amount = delay * jitter * random.random()
    return delay + jitter_amount