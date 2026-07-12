# Provider Implementations

## Location
`src/backtest_engine/data_provider/providers/`

## Base Provider
`base.py` - `BaseProvider` abstract class with:
- Rate limiting (token bucket per instance)
- Retry logic (exponential backoff + jitter)
- Chunking (date range splitting)
- Caching integration
- Normalization pipeline
- Storage integration

```python
class BaseProvider(Protocol):
    async def authenticate() -> bool
    async def get_instruments(exchange, segment) -> List[Instrument]
    async def get_instrument_token(symbol, exchange, segment) -> str
    async def get_historical_data(params) -> HistoricalDataResponse
```

## Zerodha Provider
`zerodha/client.py` - `ZerodhaProvider` implementing Kite Connect v3

### Authentication
- OAuth 2.0 with request_token → checksum → access_token
- Browser-based flow (opens localhost:8080 callback)
- Token refresh via refresh_token
- TOTP support for 2FA

### Endpoints
- `GET /instruments` - Full instrument master (CSV)
- `GET /instruments/historical/{instrument_token}/{interval}` - Historical data

### Rate Limits
- 3 requests/second
- 100 requests/minute
- 3000 requests/day

### Chunking
- Minute data: 30 days max per request
- Day data: 2000 days max per request

### Normalization
```python
# Raw Kite response
{"candles": [[timestamp, open, high, low, close, volume], ...]}

# Normalized
NormalizedOHLC(
    timestamp=datetime,
    open=Decimal,
    high=Decimal,
    low=Decimal,
    close=Decimal,
    volume=int,
    symbol="RELIANCE",
    exchange="NSE",
    segment="EQ",
    interval="minute"
)
```

## DhanHQ Provider
`dhan/client.py` - `DhanProvider` implementing API v2

### Authentication
- 24-hour JWT from web.dhan.co
- No refresh - must re-authenticate daily
- Client ID + Access Token in headers

### Endpoints
- `GET /v2/marketfeed/instruments` - Instrument master
- `POST /v2/charts/intraday` - Intraday (minute/5min/15min)
- `POST /v2/charts/historical` - Daily/weekly/monthly

### Rate Limits
- 5 requests/second
- 300 requests/minute
- 7000 requests/day

### Chunking
- Intraday: 30 days max
- Historical: 365 days max

### Normalization
```python
# Raw Dhan response
{"data": {"open": [...], "high": [...], "low": [...], "close": [...], "volume": [...], "timestamp": [...]}}

# Normalized to same NormalizedOHLC
```

## Provider Registry
`registry.py` - `ProviderRegistry` with auto-registration

```python
@register_provider("zerodha")
class ZerodhaProvider(BaseProvider): ...

@register_provider("dhan")
class DhanProvider(BaseProvider): ...

# Usage
provider = ProviderRegistry.create_provider("zerodha", config)
# Or get singleton
provider = ProviderRegistry.get_instance("zerodha")
```