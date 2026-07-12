"""
Token bucket rate limiter implementation.

Thread-safe implementation for per-provider rate limiting.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass(slots=True)
class RateLimitInfo:
    """Current rate limit status."""
    limit: int
    remaining: int
    reset_at: float
    retry_after: Optional[float] = None


class TokenBucket:
    """
    Token bucket rate limiter.
    
    Allows burst up to capacity, then enforces steady rate.
    Thread-safe for asyncio.
    """
    
    def __init__(
        self,
        rate: float,      # tokens per second
        capacity: int,    # max burst tokens
        initial_tokens: Optional[int] = None,
    ):
        self.rate = rate
        self.capacity = capacity
        self._tokens = initial_tokens if initial_tokens is not None else capacity
        self._last_update = time.monotonic()
        self._lock = asyncio.Lock()
    
    async def acquire(self, tokens: int = 1) -> float:
        """
        Acquire tokens, blocking until available.
        
        Args:
            tokens: Number of tokens to acquire
            
        Returns:
            Time waited in seconds
        """
        async with self._lock:
            now = time.monotonic()
            self._refill(now)
            
            if self._tokens >= tokens:
                self._tokens -= tokens
                return 0.0
            
            # Calculate wait time
            needed = tokens - self._tokens
            wait_time = needed / self.rate
            
            # Wait
            await asyncio.sleep(wait_time)
            
            # Refill after wait
            now = time.monotonic()
            self._refill(now)
            self._tokens -= tokens
            
            return wait_time
    
    async def try_acquire(self, tokens: int = 1) -> bool:
        """
        Try to acquire tokens without blocking.
        
        Returns:
            True if acquired, False otherwise
        """
        async with self._lock:
            now = time.monotonic()
            self._refill(now)
            
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False
    
    def _refill(self, now: float) -> None:
        """Refill tokens based on elapsed time."""
        elapsed = now - self._last_update
        new_tokens = elapsed * self.rate
        self._tokens = min(self.capacity, self._tokens + new_tokens)
        self._last_update = now
    
    def get_info(self) -> RateLimitInfo:
        """Get current rate limit status."""
        now = time.monotonic()
        self._refill(now)
        
        return RateLimitInfo(
            limit=self.capacity,
            remaining=int(self._tokens),
            reset_at=now + (self.capacity - self._tokens) / self.rate if self._tokens < self.capacity else now,
        )
    
    def reset(self) -> None:
        """Reset bucket to full capacity."""
        self._tokens = self.capacity
        self._last_update = time.monotonic()


class AsyncRateLimiter:
    """
    Async rate limiter with token bucket per provider.
    
    Manages rate limits for multiple providers independently.
    """
    
    def __init__(self):
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = asyncio.Lock()
    
    def get_bucket(self, provider: str, rate: float, capacity: int) -> TokenBucket:
        """Get or create token bucket for provider."""
        if provider not in self._buckets:
            self._buckets[provider] = TokenBucket(rate, capacity)
        return self._buckets[provider]
    
    async def acquire(
        self,
        provider: str,
        rate: float,
        capacity: int,
        tokens: int = 1,
    ) -> float:
        """
        Acquire tokens for provider.
        
        Returns:
            Time waited in seconds
        """
        bucket = self.get_bucket(provider, rate, capacity)
        return await bucket.acquire(tokens)
    
    async def try_acquire(
        self,
        provider: str,
        rate: float,
        capacity: int,
        tokens: int = 1,
    ) -> bool:
        """Try to acquire tokens without blocking."""
        bucket = self.get_bucket(provider, rate, capacity)
        return await bucket.try_acquire(tokens)
    
    def get_status(self, provider: str) -> Optional[RateLimitInfo]:
        """Get rate limit status for provider."""
        if provider in self._buckets:
            return self._buckets[provider].get_info()
        return None
    
    def reset(self, provider: Optional[str] = None) -> None:
        """Reset rate limiter for provider or all."""
        if provider:
            if provider in self._buckets:
                self._buckets[provider].reset()
        else:
            for bucket in self._buckets.values():
                bucket.reset()


# Global rate limiter instance
_rate_limiter: Optional[AsyncRateLimiter] = None


def get_rate_limiter() -> AsyncRateLimiter:
    """Get global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = AsyncRateLimiter()
    return _rate_limiter