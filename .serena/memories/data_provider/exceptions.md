# Exception Hierarchy

## Location
`src/backtest_engine/data_provider/exceptions.py`

## Hierarchy
```
DataProviderError (base)
├── ConfigurationError
├── AuthenticationError
│   ├── TokenExpiredError
│   ├── InvalidCredentialsError
│   └── AuthFlowError
├── RateLimitError
│   ├── RateLimitExceededError
│   └── DailyLimitExceededError
├── NetworkError
│   ├── ConnectionError
│   ├── TimeoutError
│   └── DNSError
├── ProviderError
│   ├── ProviderUnavailableError
│   ├── InvalidSymbolError
│   ├── InvalidIntervalError
│   ├── DataNotFoundError
│   └── ProviderAPIError
├── ValidationError
│   ├── InvalidSymbolFormatError
│   ├── InvalidDateRangeError
│   └── InvalidIntervalError
├── CacheError
│   ├── CacheMissError
│   └── CacheWriteError
├── StorageError
│   ├── StorageReadError
│   ├── StorageWriteError
│   └── PartitionError
└── DataQualityError
    ├── MissingDataError
    ├── DuplicateDataError
    └── OutOfOrderDataError
```

## Logging
All exceptions use `loguru` with `.exception()` for full stack traces:
```python
logger.exception("Failed to fetch data: {}", error)
```

## Retryable Exceptions
- `RateLimitError` (with retry-after header)
- `NetworkError` (transient)
- `ProviderUnavailableError` (5xx)
- `TimeoutError`

## Non-Retryable
- `AuthenticationError` (needs user action)
- `ValidationError` (bad input)
- `InvalidSymbolError` (symbol doesn't exist)
- `DataNotFoundError` (no data for range)