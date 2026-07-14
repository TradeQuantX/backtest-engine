"""
Cache interface for data providers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


@dataclass(frozen=True, slots=True)
class CacheEntry:
    """Cache entry with metadata."""
    key: str
    value: Any
    created_at: datetime
    expires_at: Optional[datetime] = None
    metadata: Optional[dict] = None

    @property
    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() >= self.expires_at


class CacheProtocol(ABC):
    """Abstract base class for cache implementations."""
    
    @abstractmethod
    async def get(self, key: str) -> Optional[CacheEntry]:
        """Get cache entry by key."""
        ...
    
    @abstractmethod
    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[int] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """Set cache entry with optional TTL."""
        ...
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete cache entry. Returns True if existed."""
        ...
    
    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        ...
    
    @abstractmethod
    async def clear(self, pattern: Optional[str] = None) -> int:
        """
        Clear cache entries matching pattern.
        
        Args:
            pattern: Optional glob pattern (e.g., "zerodha:*")
            
        Returns:
            Number of entries cleared.
        """
        ...
    
    @abstractmethod
    async def get_stats(self) -> dict:
        """Get cache statistics."""
        ...