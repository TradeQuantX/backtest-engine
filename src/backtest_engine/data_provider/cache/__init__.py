"""
Cache implementations for the data provider layer.
"""

import asyncio
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from backtest_engine.data_provider.interfaces import CacheEntry, CacheProtocol


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
    
    async def clear(self) -> int:
        async with self._lock:
            count = 0
            
            # Clear all
            for file_path in self.cache_dir.glob("*.cache"):
                file_path.unlink()
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