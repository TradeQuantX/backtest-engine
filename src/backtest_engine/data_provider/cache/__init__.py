"""
Cache implementations for the data provider layer.
"""

import asyncio
import json
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from backtest_engine.data_provider.interfaces import CacheEntry, CacheProtocol


class MemoryCache(CacheProtocol):
    """In-memory LRU cache implementation."""
    
    def __init__(self, max_size: int = 1000):
        self._cache: dict[str, CacheEntry] = {}
        self._max_size = max_size
        self._access_times: dict[str, datetime] = {}
        self._lock = asyncio.Lock()
    
    async def get(self, key: str) -> Optional[CacheEntry]:
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            
            if entry.is_expired:
                del self._cache[key]
                self._access_times.pop(key, None)
                return None
            
            self._access_times[key] = datetime.utcnow()
            return entry
    
    async def set(self, entry: CacheEntry) -> bool:
        async with self._lock:
            # Evict if at capacity
            if len(self._cache) >= self._max_size and key not in self._cache:
                await self._evict_lru()
            
            self._cache[entry.key] = entry
            self._access_times[entry.key] = datetime.utcnow()
            return True
    
    async def delete(self, key: str) -> bool:
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._access_times.pop(key, None)
                return True
            return False
    
    async def exists(self, key: str) -> bool:
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return False
            if entry.is_expired:
                del self._cache[key]
                self._access_times.pop(key, None)
                return False
            return True
    
    async def clear(self, tags: Optional[list[str]] = None) -> int:
        async with self._lock:
            if tags is None:
                count = len(self._cache)
                self._cache.clear()
                self._access_times.clear()
                return count
            
            # Clear entries with matching tags
            keys_to_delete = [
                key for key, entry in self._cache.items()
                if any(tag in entry.tags for tag in tags)
            ]
            for key in keys_to_delete:
                del self._cache[key]
                self._access_times.pop(key, None)
            return len(keys_to_delete)
    
    async def get_stats(self) -> dict:
        async with self._lock:
            return {
                "type": "memory",
                "size": len(self._cache),
                "max_size": self._max_size,
                "entries": list(self._cache.keys()),
            }
    
    async def _evict_lru(self) -> None:
        """Evict least recently used entry."""
        if not self._access_times:
            return
        
        lru_key = min(self._access_times, key=self._access_times.get)
        del self._cache[lru_key]
        del self._access_times[lru_key]


class DiskCache(CacheProtocol):
    """Disk-based cache using JSON/msgpack files."""
    
    def __init__(self, cache_dir: Path, max_size_mb: int = 500):
        self.cache_dir = Path(cache_dir).expanduser().resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self._lock = asyncio.Lock()
    
    def _get_file_path(self, key: str) -> Path:
        """Get file path for cache key."""
        # Sanitize key for filesystem
        safe_key = key.replace(":", "_").replace("/", "_").replace("\\", "_")
        return self.cache_dir / f"{safe_key}.cache"
    
    async def get(self, key: str) -> Optional[CacheEntry]:
        async with self._lock:
            file_path = self._get_file_path(key)
            
            if not file_path.exists():
                return None
            
            try:
                with open(file_path, "rb") as f:
                    data = pickle.load(f)
                
                entry = CacheEntry(**data)
                
                if entry.is_expired:
                    file_path.unlink(missing_ok=True)
                    return None
                
                return entry
            except Exception:
                # Corrupted cache file
                file_path.unlink(missing_ok=True)
                return None
    
    async def set(self, entry: CacheEntry) -> bool:
        async with self._lock:
            file_path = self._get_file_path(entry.key)
            
            try:
                # Check size limit
                await self._enforce_size_limit()
                
                data = {
                    "key": entry.key,
                    "value": entry.value,
                    "created_at": entry.created_at,
                    "expires_at": entry.expires_at,
                    "tags": entry.tags,
                    "metadata": entry.metadata,
                }
                
                with open(file_path, "wb") as f:
                    pickle.dump(data, f)
                
                return True
            except Exception:
                return False
    
    async def delete(self, key: str) -> bool:
        async with self._lock:
            file_path = self._get_file_path(key)
            if file_path.exists():
                file_path.unlink()
                return True
            return False
    
    async def exists(self, key: str) -> bool:
        async with self._lock:
            file_path = self._get_file_path(key)
            if not file_path.exists():
                return False
            
            try:
                with open(file_path, "rb") as f:
                    data = pickle.load(f)
                entry = CacheEntry(**data)
                if entry.is_expired:
                    file_path.unlink(missing_ok=True)
                    return False
                return True
            except Exception:
                file_path.unlink(missing_ok=True)
                return False
    
    async def clear(self, tags: Optional[list[str]] = None) -> int:
        async with self._lock:
            count = 0
            
            if tags is None:
                # Clear all
                for file_path in self.cache_dir.glob("*.cache"):
                    file_path.unlink()
                    count += 1
            else:
                # Clear by tags
                for file_path in self.cache_dir.glob("*.cache"):
                    try:
                        with open(file_path, "rb") as f:
                            data = pickle.load(f)
                        entry = CacheEntry(**data)
                        if any(tag in entry.tags for tag in tags):
                            file_path.unlink()
                            count += 1
                    except Exception:
                        file_path.unlink(missing_ok=True)
                        count += 1
            
            return count
    
    async def get_stats(self) -> dict:
        async with self._lock:
            total_size = 0
            count = 0
            
            for file_path in self.cache_dir.glob("*.cache"):
                total_size += file_path.stat().st_size
                count += 1
            
            return {
                "type": "disk",
                "path": str(self.cache_dir),
                "entries": count,
                "total_size_bytes": total_size,
                "max_size_bytes": self.max_size_bytes,
            }
    
    async def _enforce_size_limit(self) -> None:
        """Remove oldest entries if cache exceeds size limit."""
        total_size = sum(
            f.stat().st_size for f in self.cache_dir.glob("*.cache")
        )
        
        if total_size < self.max_size_bytes:
            return
        
        # Get files sorted by modification time (oldest first)
        files = sorted(
            self.cache_dir.glob("*.cache"),
            key=lambda f: f.stat().st_mtime,
        )
        
        for file_path in files:
            if total_size < self.max_size_bytes * 0.8:  # Leave 20% headroom
                break
            file_path.unlink()
            total_size -= file_path.stat().st_size


class HybridCache(CacheProtocol):
    """Hybrid cache with memory L1 and disk L2."""
    
    def __init__(
        self,
        memory_cache: MemoryCache,
        disk_cache: DiskCache,
    ):
        self.memory = memory_cache
        self.disk = disk_cache
    
    async def get(self, key: str) -> Optional[CacheEntry]:
        # Try memory first
        entry = await self.memory.get(key)
        if entry:
            return entry
        
        # Try disk
        entry = await self.disk.get(key)
        if entry:
            # Promote to memory
            await self.memory.set(entry)
            return entry
        
        return None
    
    async def set(self, entry: CacheEntry) -> bool:
        # Write to both
        await self.memory.set(entry)
        await self.disk.set(entry)
        return True
    
    async def delete(self, key: str) -> bool:
        mem_result = await self.memory.delete(key)
        disk_result = await self.disk.delete(key)
        return mem_result or disk_result
    
    async def exists(self, key: str) -> bool:
        return await self.memory.exists(key) or await self.disk.exists(key)
    
    async def clear(self, tags: Optional[list[str]] = None) -> int:
        mem_count = await self.memory.clear(tags)
        disk_count = await self.disk.clear(tags)
        return mem_count + disk_count
    
    async def get_stats(self) -> dict:
        return {
            "memory": await self.memory.get_stats(),
            "disk": await self.disk.get_stats(),
        }