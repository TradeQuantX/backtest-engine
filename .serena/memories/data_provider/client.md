# Data Provider Client - Main Researcher API

## Location
`src/backtest_engine/data_provider/client.py`

## Main Class
`DataProviderClient` - Single entry point for researchers

## Key Methods
- `initialize(config_path=None)` - Auto-discovers providers, loads config
- `get_historical_ohlc_data(symbol, exchange, segment, interval, from_date, to_date, provider=None)` - Main data fetch
- `get_available_symbols(exchange, segment, provider=None)` - Symbol discovery
- `get_provider_status(provider=None)` - Health/status check
- `close()` - Cleanup

## Auto-Discovery
- Scans `providers/` for `@register_provider` decorated classes
- Auto-instantiates with config from ConfigLoader
- No manual registration needed

## Usage Pattern
```python
client = DataProviderClient()
await client.initialize()
data = await client.get_historical_ohlc_data(
    symbol="RELIANCE", exchange="NSE", segment="EQ",
    interval="minute", from_date="2024-01-01", to_date="2024-01-31"
)
await client.close()
```

## Config Priority
1. `config_path` arg to initialize()
2. `~/.tradex/config.yml`
3. `./config.yml`
4. Environment variables (TRADING_* prefix)