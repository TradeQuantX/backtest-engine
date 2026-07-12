# TradeQuantX Backtest Engine - Memory Index

## Core Memories
- `mem:core` - Project overview, architecture, key decisions, researcher API
- `mem:data_provider/storage` - Parquet storage with monthly partitioning
- `mem:data_provider/utils` - Normalization, chunking, retry, validation, rate limiting
- `mem:data_provider/exceptions` - Unified exception hierarchy with retryable classification
- `mem:data_provider/client_providers` - DataProviderClient, ProviderRegistry, Zerodha/Dhan implementations

## Project Structure
```
TradeQuantX/backtest/backtest_engine/
├── src/backtest_engine/data_provider/   # Main package
├── tests/test_data_provider.py          # 26 tests passing
├── config.yml                           # Example config
├── pyproject.toml                       # Dependencies (uv)
└── examples/basic_usage.py              # Researcher demo
```

## Quick Reference
- **Main Entry**: `DataProviderClient()` → `initialize()` → `get_historical_ohlc_data()`
- **Config**: 3-tier (env > ~/.tradex/config.yml > ./config.yml)
- **Auth**: Zerodha=OAuth browser, Dhan=24hr JWT manual
- **Storage**: Monthly Parquet partitions, snappy compression
- **Cache**: L1 memory (LRU) + L2 disk (pickle)
- **Rate Limit**: Token bucket per provider (Zerodha 3/s, Dhan 5/s)
- **Tests**: `python -m pytest tests/test_data_provider.py -v` (26 passed)