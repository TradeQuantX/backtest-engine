# Main Client & Provider Implementations

## DataProviderClient (Main Entry Point)
**Location**: `src/backtest_engine/data_provider/client.py`

### Key Methods
```python
client = DataProviderClient()
await client.initialize(config_path="~/.tradex/config.yml")  # Auto-loads config

# Main researcher API
data = await client.get_historical_ohlc_data(
    symbol="RELIANCE",
    exchange="NSE",
    segment="EQ",
    interval="minute",
    from_date="2024-01-01",
    to_date="2024-01-31",
    use_cache=True,
    store_data=True
)
# Returns: HistoricalDataResponse(data=[NormalizedOHLC, ...], metadata=...)

# Instrument lookup
instruments = await client.get_instruments(exchange="NSE", segment="EQ")
token = await client.get_instrument_token("RELIANCE", "NSE", "EQ")

# Context manager support
async with DataProviderClient() as client:
    await client.initialize()
    data = await client.get_historical_ohlc_data(...)
```

### Flow
1. `initialize()` → loads config → creates providers → authenticates → initializes cache/storage
2. `get_historical_ohlc_data()` → checks cache → chunks date range → fetches from provider → normalizes → validates → stores → returns

## Provider Registry
**Location**: `src/backtest_engine/data_provider/providers/registry.py`

### Auto-registration
```python
@register_provider("zerodha")
class ZerodhaProvider(BaseProvider):
    ...

@register_provider("dhan")
class DhanProvider(BaseProvider):
    ...
```

### Usage
```python
registry = ProviderRegistry()
provider = registry.create_provider("zerodha", config)
# or
provider = registry.get_instance("zerodha")  # singleton
```

## ZerodhaProvider (Kite Connect v3)
**Location**: `src/backtest_engine/data_provider/providers/zerodha/client.py`

### Auth Flow (OAuth)
1. User calls `authenticate()` → opens browser to `https://kite.zerodha.com/connect/login?v=3&api_key=...`
2. User logs in → redirects to `http://127.0.0.1:8080/?request_token=xxx`
3. Local HTTP server catches request_token
4. Server computes checksum: `sha256(api_key + request_token + api_secret)`
5. POST to `/session/token` → gets `access_token`
6. Token stored encrypted in `~/.tradex/tokens/zerodha.enc`

### API Endpoints
- Instruments: `GET /instruments` (CSV, ~1.5MB)
- Historical: `GET /instruments/historical/{instrument_token}/{interval}`

### Rate Limits
- 3 requests/second
- 100 requests/minute
- 3000 requests/hour

## DhanProvider (API v2)
**Location**: `src/backtest_engine/data_provider/providers/dhan/client.py`

### Auth (JWT)
- 24-hour JWT from `https://web.dhan.co` → Settings → API
- Paste into config: `access_token: "eyJhbGciOiJIUzI1NiIs..."`
- Validated on each request via `Authorization: Bearer <token>`

### API Endpoints
- Instruments: `GET /v2/instruments/master` (CSV)
- Intraday: `POST /v2/charts/intraday`
- Historical: `POST /v2/charts/historical`

### Rate Limits
- 5 requests/second
- 7000 requests/day

## BaseProvider
**Location**: `src/backtest_engine/data_provider/providers/base.py`

### Shared Logic
- Rate limiting (token bucket per instance)
- Retry with exponential backoff
- Caching (L1 memory + L2 disk)
- Storage (Parquet partitioning)
- Normalization & validation
- Instrument token resolution