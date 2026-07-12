# TradeQuantX Backtest Engine - Memory Index

## Core Memories
- `mem:data_provider/core` - Main data provider module overview
- `mem:data_provider/auth` - Authentication (Zerodha OAuth, Dhan JWT, token storage)
- `mem:data_provider/cache` - Multi-level caching (memory + disk)
- `mem:data_provider/config` - Configuration (3-tier priority, env vars, YAML)
- `mem:data_provider/providers` - Provider implementations (Zerodha v3, Dhan v2)
- `mem:data_provider/storage` - Parquet partitioned storage

## Project Structure
```
backtest_engine/
├── src/backtest_engine/data_provider/   # Core data provider module
├── tests/                               # 26 tests passing
├── examples/                            # Usage examples
├── config.yml                           # Project config template
├── pyproject.toml                       # Dependencies (uv)
└── README.md
```

## Key Technologies
- Python 3.13+, uv package manager
- httpx (async HTTP), pydantic (config validation)
- polars + pyarrow (Parquet), loguru (logging)
- tenacity (retry), cryptography (token encryption)
- pytest + pytest-asyncio + respx (testing)

## Quick Start
```python
from backtest_engine.data_provider import DataProviderClient

client = DataProviderClient()
await client.initialize()

data = await client.get_historical_ohlc_data(
    symbol="RELIANCE",
    exchange="NSE",
    segment="EQ",
    interval="minute",
    from_date="2024-01-01",
    to_date="2024-01-31"
)
```

## Testing
```bash
python -m pytest tests/test_data_provider.py -v  # 26 passed
```