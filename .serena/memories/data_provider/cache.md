# Cache Module

## Location
`src/backtest_engine/data_provider/cache/`

## Components
- `memory_cache.py` - `MemoryCache` (LRU with TTL)
- `disk_cache.py` - `DiskCache` (pickle + index file)
- `multi_level_cache.py` - `MultiLevelCache` (L1 memory + L2 disk)

## MemoryCache
- LRU eviction with `max_size` (default 1000 entries)
- TTL support (default 1 hour)
- Thread-safe with `asyncio.Lock`
- Key format: `{provider}:{exchange}:{segment}:{symbol}:{interval}:{from_date}:{to_date}`

```python
cache = MemoryCache(max_size=1000, ttl_seconds=3600)
await cache.set(key, data)
data = await cache.get(key)  # Returns None if missing/expired
await cache.delete(key)
await cache.clear()
```

## DiskCache
- Pickle serialization with `protocol=5`
- Index file (JSON) maps keys to file paths + metadata
- Max size limit (default 500MB) with LRU eviction
- Compression: `lz4` if available, else `gzip`

```python
cache = DiskCache(path="~/.tradex/cache", max_size_mb=500)
await cache.set(key, data)
data = await cache.get(key)
```

## MultiLevelCache
- L1: MemoryCache (fast, small)
- L2: DiskCache (slower, larger)
- Read: Check L1 → L2 → miss
- Write: Write to both L1 and L2
- Invalidation: Removes from both levels

```python
cache = MultiLevelCache(
    l1=MemoryCache(max_size=1000),
    l2=DiskCache(path="~/.tradex/cache", max_size_mb=500)
)
await cache.set(key, data)
data = await cache.get(key)
```

## Cache Key Strategy
```
{provider}:{exchange}:{segment}:{symbol}:{interval}:{from_date}:{to_date}
Example: zerodha:NSE:EQ:RELIANCE:minute:2024-01-01:2024-01-31
```

## Invalidation
- TTL-based (auto-expire)
- Manual: `await cache.invalidate(pattern="zerodha:NSE:EQ:RELIANCE:*")`
- On data write: `await cache.invalidate(symbol_key)` before storing fresh data