"""
Utilities package for data provider layer.
"""

from zoneinfo import ZoneInfo

# Centralized timezone constant - all timestamps are IST
IST = ZoneInfo("Asia/Kolkata")

from backtest_engine.data_provider.utils.chunking import (
    ChunkingConfig,
    DateChunk,
    chunk_date_range,
    estimate_chunks,
    get_max_days_for_interval,
    merge_chunks,
)
from backtest_engine.data_provider.utils.normalization import (
    dhan_instrument_to_normalized,
    dhan_ohlc_to_normalized,
    normalize_exchange,
    normalize_instrument_type,
    normalize_interval,
    normalize_segment,
    normalize_timestamp,
    normalized_to_polars,
    polars_to_normalized,
    zerodha_instrument_to_normalized,
    zerodha_ohlc_to_normalized,
)
from backtest_engine.data_provider.utils.rate_limiter import (
    AsyncRateLimiter,
    RateLimitBucket,
    RateLimitInfo,
    get_rate_limiter,
)
from backtest_engine.data_provider.utils.retry import (
    RetryConfig,
    RetryResult,
    get_retry_delay,
    is_retryable_error,
    retry_with_backoff,
)
from backtest_engine.data_provider.utils.validation import (
    validate_dataframe_schema,
    validate_historical_request,
    validate_instrument,
    validate_ohlc_data,
    validate_ohlc_dataframe,
)

__all__ = [
    # Timezone
    "IST",
    # Chunking
    "ChunkingConfig",
    "DateChunk",
    "chunk_date_range",
    "estimate_chunks",
    "get_max_days_for_interval",
    "merge_chunks",
    # Normalization
    "normalize_timestamp",
    "normalize_interval",
    "normalize_exchange",
    "normalize_segment",
    "normalize_instrument_type",
    "zerodha_ohlc_to_normalized",
    "dhan_ohlc_to_normalized",
    "zerodha_instrument_to_normalized",
    "dhan_instrument_to_normalized",
    "normalized_to_polars",
    "polars_to_normalized",
    # Rate Limiter
    "AsyncRateLimiter",
    "RateLimitBucket",
    "get_rate_limiter",
    # Retry
    "RetryConfig",
    "RetryResult",
    "retry_with_backoff",
    "is_retryable_error",
    "get_retry_delay",
    # Validation
    "validate_ohlc_data",
    "validate_ohlc_dataframe",
    "validate_instrument",
    "validate_historical_request",
    "validate_dataframe_schema",
]