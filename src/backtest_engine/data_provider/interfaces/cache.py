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
    async def set(self, entry: CacheEntry) -> bool:
        """Set cache entry. Returns True on success."""
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
    async def clear(self) -> int:
        """Clear all cache entries. Returns number of entries cleared."""
        ...
    
    @abstractmethod
    async def get_stats(self) -> dict:
        """Get cache statistics."""
        ...