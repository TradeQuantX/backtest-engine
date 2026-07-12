# Data Provider Module - Core Memory

## Overview
Complete broker/data access layer for backtest-engine. Supports Zerodha Kite Connect v3 and DhanHQ API v2 with unified interface for researchers.

## Architecture
```
src/backtest_engine/data_provider/
├── __init__.py              # Public API exports
├── client.py                # DataProviderClient (main entry point)
├── config/                  # Configuration (3-tier priority)
├── interfaces/              # Protocols (Provider, Auth, Cache, Storage)
├── providers/               # Zerodha + Dhan implementations
├── auth/                    # Token management (encrypted)
├── cache/                   # Multi-level (memory + disk)
├── storage/                 # Parquet partitioned storage
├── utils/                   # Normalization, chunking, rate limiting, retry
├── exceptions/              # Unified exception hierarchy
└── models/                  # NormalizedOHLC, Instrument, etc.
```

## Key Components

### DataProviderClient (Main API)
```python
client = DataProviderClient()
await client.initialize()  # Loads config, creates providers, authenticates

data = await client.get_historical_ohlc_data(
    symbol="RELIANCE",
    exchange="NSE",
    segment="EQ",
    interval="minute",
    from_date="2024-01-01",
    to_date="2024-01-31"
)
# Returns HistoricalDataResponse with list[NormalizedOHLC]
```

### Provider Abstraction
- Protocol-based (SOLID: Interface Segregation, Dependency Inversion)
- Auto-registration via `@register_provider`
- Unified rate limiting, retry, chunking, caching, normalization

### Configuration
- 3-tier: env vars > ~/.tradex/config.yml > ./config.yml
- Deep merge with Pydantic validation
- Provider-specific configs (ZerodhaConfig, DhanConfig)

## Related Memories
- `mem:data_provider/auth` - Authentication (OAuth, JWT, token storage)
- `mem:data_provider/cache` - Multi-level caching (memory + disk)
- `mem:data_provider/config` - Configuration system
- `mem:data_provider/providers` - Zerodha & Dhan implementations
- `mem:data_provider/storage` - Parquet partitioned storage

## Testing
```bash
python -m pytest tests/test_data_provider.py -v
# 26 tests passing
```

## Usage Example
See `examples/basic_usage.py` for complete researcher workflow.