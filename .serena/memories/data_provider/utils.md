# Utilities

## Location
`src/backtest_engine/data_provider/utils/`

## Components
- `normalization.py` - `normalize_ohlcv()`, `normalize_symbol()`, `normalize_interval()`
- `chunking.py` - `chunk_date_range()` for API limit compliance
- `retry.py` - `retry_with_backoff()` decorator (exponential backoff, jitter)
- `validation.py` - `validate_symbol()`, `validate_date_range()`, `validate_interval()`
- `rate_limiter.py` - `TokenBucketRateLimiter` (per-provider instance)

## Normalization
- **OHLCV**: Ensures float64, UTC timestamps, sorted ascending, no duplicates
- **Symbol**: Uppercase, exchange-specific format (NSE: RELIANCE, BSE: 500325)
- **Interval**: Maps provider-specific to canonical (minute, 5minute, 15minute, 30minute, 60minute, day)

## Chunking
- Splits date ranges to respect API limits
- Zerodha: max 60 days for minute, 2000 days for day
- DhanHQ: max 100 days for intraday, 365 days for daily
- Returns list of (from_date, to_date) tuples

## Retry Logic
```python
@retry_with_backoff(
    max_retries=3,
    base_delay=1.0,
    max_delay=60.0,
    exponential_base=2,
    jitter=True,
    retryable_exceptions=(RateLimitError, NetworkError, ServerError)
)
async def fetch_data(...):
    ...
```

## Rate Limiter (Token Bucket)
- Per-provider instance (not global)
- Configurable: `requests_per_second`, `burst_size`, `daily_limit`
- Async-friendly with `asyncio.Lock`
- Blocks until token available

## Validation
- Symbol format per exchange/segment
- Date range: not future, not before 2000, max range per interval
- Interval: valid for provider