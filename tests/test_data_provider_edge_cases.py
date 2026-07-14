"""
Edge case tests for the data provider layer.

Tests boundary conditions, error handling, and edge cases
to prevent regressions in production.
"""

import pytest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock, MagicMock, patch

from backtest_engine.data_provider.utils.normalization import (
    normalize_timestamp,
    normalize_interval,
    normalize_exchange,
    normalize_segment,
    normalize_instrument_type,
    zerodha_ohlc_to_normalized,
    dhan_ohlc_to_normalized,
    normalized_to_polars,
    polars_to_normalized,
)
from backtest_engine.data_provider.utils.chunking import (
    chunk_date_range,
    estimate_chunks,
    merge_chunks,
    DateChunk,
    ChunkingConfig,
)
from backtest_engine.data_provider.utils.rate_limiter import (
    RateLimitBucket,
    AsyncRateLimiter,
)
from backtest_engine.data_provider.utils.retry import (
    RetryConfig,
    retry_with_backoff,
    is_retryable_error,
    get_retry_delay,
)
from backtest_engine.data_provider.exceptions import (
    DataProviderError,
    ProviderUnavailableError,
    ProviderTimeoutError,
    RateLimitError,
    RateLimitExceededError,
    DataNotFoundError,
    ValidationError,
    ProviderResponseError,
    InstrumentNotFoundError,
)
from backtest_engine.data_provider.interfaces.models import (
    Exchange,
    Segment,
    Interval,
    NormalizedOHLC,
    NormalizedInstrument,
    InstrumentType,
)


class TestNormalizationEdgeCases:
    """Edge case tests for normalization utilities."""

    def test_normalize_timestamp_dst_transition(self):
        """Test timestamp normalization across DST boundaries."""
        # Spring forward (March 10, 2024 in US)
        ts = normalize_timestamp("2024-03-10 02:30:00", source_tz="US/Eastern", target_tz="UTC")
        assert ts.tzinfo is not None
        
        # Fall back (November 3, 2024 in US)
        ts = normalize_timestamp("2024-11-03 01:30:00", source_tz="US/Eastern", target_tz="UTC")
        assert ts.tzinfo is not None

    def test_normalize_timestamp_leap_year(self):
        """Test timestamp normalization on leap day."""
        ts = normalize_timestamp("2024-02-29 12:00:00")
        assert ts.year == 2024
        assert ts.month == 2
        assert ts.day == 29

    def test_normalize_timestamp_timezone_aware_input(self):
        """Test normalization preserves timezone-aware datetimes correctly."""
        dt = datetime(2024, 1, 1, 9, 15, tzinfo=ZoneInfo("Asia/Kolkata"))
        ts = normalize_timestamp(dt)
        assert ts.tzinfo is not None
        # Should be converted to UTC
        assert ts.hour == 3  # 9:15 IST = 3:45 UTC
        assert ts.minute == 45

    def test_normalize_timestamp_epoch_milliseconds(self):
        """Test epoch milliseconds are handled correctly."""
        # 2024-01-01 09:15:00 UTC in milliseconds
        ts = normalize_timestamp(1704092100000)
        assert ts.year == 2024
        assert ts.month == 1
        assert ts.day == 1

    def test_normalize_timestamp_invalid_formats(self):
        """Test various invalid timestamp formats raise appropriate errors."""
        invalid_inputs = [
            "not-a-timestamp",
            "",
            "2024-13-01",  # Invalid month
            "2024-01-32",  # Invalid day
            None,
            [],
            {},
            object(),
        ]
        for invalid in invalid_inputs:
            with pytest.raises((ValueError, TypeError)):
                normalize_timestamp(invalid)

    def test_normalize_interval_case_insensitive(self):
        """Test interval normalization is case insensitive."""
        assert normalize_interval("MINUTE", "zerodha") == Interval.MINUTE_1
        assert normalize_interval("Minute", "zerodha") == Interval.MINUTE_1
        assert normalize_interval(" 5minute ", "zerodha") == Interval.MINUTE_5
        assert normalize_interval("DAY", "zerodha") == Interval.DAY

    def test_normalize_interval_unknown_provider(self):
        """Test interval normalization with unknown provider falls back to direct match."""
        # Unknown provider returns default for known intervals that match enum values
        assert normalize_interval("1minute", "unknown") == Interval.MINUTE_1
        assert normalize_interval("day", "unknown") == Interval.DAY
        # Unknown interval with unknown provider raises ValueError
        with pytest.raises(ValueError):
            normalize_interval("unknown_interval", "unknown")

    def test_normalize_exchange_case_insensitive(self):
        """Test exchange normalization is case insensitive."""
        assert normalize_exchange("nse", "zerodha") == Exchange.NSE
        assert normalize_exchange("Nse", "zerodha") == Exchange.NSE
        assert normalize_exchange(" nse_eq ", "dhan") == Exchange.NSE

    def test_normalize_exchange_unknown_provider(self):
        """Test exchange normalization with unknown provider."""
        assert normalize_exchange("NSE", "unknown") == Exchange.NSE
        assert normalize_exchange("BSE", "unknown") == Exchange.BSE

    def test_normalize_segment_case_insensitive(self):
        """Test segment normalization is case insensitive."""
        assert normalize_segment("eq", "zerodha") == Segment.EQ
        assert normalize_segment("Eq", "zerodha") == Segment.EQ
        assert normalize_segment(" equity ", "dhan") == Segment.EQ

    def test_normalize_instrument_type_case_insensitive(self):
        """Test instrument type normalization is case insensitive."""
        assert normalize_instrument_type("eq", "zerodha") == InstrumentType.EQ
        assert normalize_instrument_type("Eq", "zerodha") == InstrumentType.EQ
        assert normalize_instrument_type(" futures ", "dhan") == InstrumentType.FUT

    def test_zerodha_ohlc_to_normalized_empty_candles(self):
        """Test Zerodha OHLC conversion with empty candle list."""
        result = zerodha_ohlc_to_normalized([], "RELIANCE", Exchange.NSE, Segment.EQ, Interval.MINUTE_1)
        assert result == []

    def test_zerodha_ohlc_to_normalized_invalid_candles(self):
        """Test Zerodha OHLC conversion skips invalid candles."""
        candles = [
            [1704092100, 2500.0, 2510.0, 2495.0, 2505.0, 100000],  # Valid
            [1704092160, 2505.0],  # Invalid - too few elements
            [1704092220, 2510.0, 2520.0, 2505.0, 2515.0, 80000],  # Valid
        ]
        result = zerodha_ohlc_to_normalized(candles, "RELIANCE", Exchange.NSE, Segment.EQ, Interval.MINUTE_1)
        assert len(result) == 2  # Only valid candles

    def test_dhan_ohlc_to_normalized_empty_data(self):
        """Test Dhan OHLC conversion with empty data."""
        data = {"open": [], "high": [], "low": [], "close": [], "volume": [], "timestamp": []}
        result = dhan_ohlc_to_normalized(data, "RELIANCE", Exchange.NSE, Segment.EQ, Interval.MINUTE_1)
        assert result == []

    def test_dhan_ohlc_to_normalized_mismatched_arrays(self):
        """Test Dhan OHLC conversion handles mismatched array lengths."""
        data = {
            "open": [2500.0, 2505.0],
            "high": [2510.0],
            "low": [2495.0, 2500.0],
            "close": [2505.0, 2510.0],
            "volume": [100000, 80000],
            "timestamp": [1704092100, 1704092160],
        }
        result = dhan_ohlc_to_normalized(data, "RELIANCE", Exchange.NSE, Segment.EQ, Interval.MINUTE_1)
        assert len(result) == 1  # Limited by shortest array (high)

    def test_normalized_to_polars_empty(self):
        """Test conversion of empty list to Polars DataFrame."""
        df = normalized_to_polars([])
        assert df.height == 0
        assert "symbol" in df.columns
        assert "timestamp" in df.columns

    def test_polars_to_normalized_empty(self):
        """Test conversion of empty Polars DataFrame to list."""
        import polars as pl
        df = pl.DataFrame(schema={
            "symbol": pl.Utf8,
            "exchange": pl.Utf8,
            "segment": pl.Utf8,
            "interval": pl.Utf8,
            "timestamp": pl.Datetime("us", "UTC"),
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Int64,
            "open_interest": pl.Int64,
        })
        result = polars_to_normalized(df)
        assert result == []


class TestChunkingEdgeCases:
    """Edge case tests for date range chunking."""

    def test_chunk_date_range_same_day(self):
        """Test chunking when from_date equals to_date."""
        from_date = datetime(2024, 1, 1)
        to_date = datetime(2024, 1, 1)
        chunks = chunk_date_range(from_date, to_date, "minute")
        assert len(chunks) == 1
        assert chunks[0].from_date == from_date
        assert chunks[0].to_date == to_date

    def test_chunk_date_range_reversed_dates(self):
        """Test chunking with reversed dates returns empty."""
        from_date = datetime(2024, 1, 15)
        to_date = datetime(2024, 1, 1)
        chunks = chunk_date_range(from_date, to_date, "minute")
        assert len(chunks) == 0  # Empty range

    def test_chunk_date_range_timezone_aware(self):
        """Test chunking with timezone-aware datetimes."""
        from_date = datetime(2024, 1, 1, tzinfo=ZoneInfo("Asia/Kolkata"))
        to_date = datetime(2024, 1, 15, tzinfo=ZoneInfo("Asia/Kolkata"))
        chunks = chunk_date_range(from_date, to_date, "minute")
        assert len(chunks) == 1
        assert chunks[0].from_date.tzinfo is not None

    def test_chunk_date_range_dst_boundary(self):
        """Test chunking across DST boundaries."""
        # Spring forward
        from_date = datetime(2024, 3, 9, tzinfo=ZoneInfo("US/Eastern"))
        to_date = datetime(2024, 3, 11, tzinfo=ZoneInfo("US/Eastern"))
        chunks = chunk_date_range(from_date, to_date, "minute")
        assert len(chunks) >= 1

    def test_chunk_date_range_leap_year(self):
        """Test chunking across leap year boundary."""
        from_date = datetime(2024, 2, 28)
        to_date = datetime(2024, 3, 1)
        chunks = chunk_date_range(from_date, to_date, "minute")
        assert len(chunks) == 1

    def test_chunk_date_range_different_intervals(self):
        """Test chunking with different intervals."""
        from_date = datetime(2024, 1, 1)
        to_date = datetime(2024, 12, 31)
        
        # Minute: 30 days max -> ~12 chunks
        minute_chunks = chunk_date_range(from_date, to_date, "minute")
        assert len(minute_chunks) >= 12
        
        # Day: 2000 days max -> 1 chunk
        day_chunks = chunk_date_range(from_date, to_date, "day")
        assert len(day_chunks) == 1

    def test_estimate_chunks_matches_actual(self):
        """Test estimate_chunks matches actual chunk count."""
        from_date = datetime(2024, 1, 1)
        to_date = datetime(2024, 2, 15)
        
        for interval in ["minute", "5minute", "15minute", "day"]:
            estimated = estimate_chunks(from_date, to_date, interval)
            actual = len(chunk_date_range(from_date, to_date, interval))
            assert estimated == actual

    def test_merge_chunks_adjacent(self):
        """Test merging adjacent chunks."""
        chunks = [
            DateChunk(datetime(2024, 1, 1), datetime(2024, 1, 15), 0, 0),
            DateChunk(datetime(2024, 1, 16), datetime(2024, 1, 31), 1, 0),
        ]
        merged = merge_chunks(chunks)
        assert len(merged) == 1
        assert merged[0].from_date == datetime(2024, 1, 1)
        assert merged[0].to_date == datetime(2024, 1, 31)

    def test_merge_chunks_overlapping(self):
        """Test merging overlapping chunks."""
        chunks = [
            DateChunk(datetime(2024, 1, 1), datetime(2024, 1, 20), 0, 0),
            DateChunk(datetime(2024, 1, 15), datetime(2024, 1, 31), 1, 0),
        ]
        merged = merge_chunks(chunks)
        assert len(merged) == 1
        assert merged[0].from_date == datetime(2024, 1, 1)
        assert merged[0].to_date == datetime(2024, 1, 31)

    def test_merge_chunks_with_gaps(self):
        """Test merging preserves gaps between non-adjacent chunks."""
        chunks = [
            DateChunk(datetime(2024, 1, 1), datetime(2024, 1, 15), 0, 0),
            DateChunk(datetime(2024, 2, 1), datetime(2024, 2, 15), 1, 0),  # Gap!
        ]
        merged = merge_chunks(chunks)
        assert len(merged) == 2  # Gap preserved

    def test_merge_chunks_empty(self):
        """Test merging empty chunk list."""
        assert merge_chunks([]) == []

    def test_chunking_config_custom_limits(self):
        """Test chunking with custom configuration."""
        config = ChunkingConfig(max_days_per_interval={"minute": 10, "day": 100})
        from_date = datetime(2024, 1, 1)
        to_date = datetime(2024, 1, 25)
        chunks = chunk_date_range(from_date, to_date, "minute", config)
        assert len(chunks) == 3  # 25 days / 10 = 3 chunks


class TestRateLimiterEdgeCases:
    """Edge case tests for rate limiter."""

    @pytest.mark.asyncio
    async def test_token_bucket_concurrent_access(self):
        """Test token bucket handles concurrent access correctly."""
        import asyncio
        
        bucket = RateLimitBucket(rate=100, capacity=100)
        
        async def acquire_tokens():
            return await bucket.acquire(1)
        
        # Fire 50 concurrent requests
        tasks = [acquire_tokens() for _ in range(50)]
        results = await asyncio.gather(*tasks)
        
        # All should succeed immediately
        assert all(r == 0.0 for r in results)
        assert bucket.get_info().remaining == 50

    @pytest.mark.asyncio
    async def test_token_bucket_burst_then_wait(self):
        """Test burst capacity then wait for refill."""
        bucket = RateLimitBucket(rate=10, capacity=10)
        
        # Burst: use all 10 tokens
        wait = await bucket.acquire(10)
        assert wait == 0.0
        assert bucket.get_info().remaining == 0
        
        # Next acquire must wait
        import asyncio
        start = asyncio.get_event_loop().time()
        wait = await bucket.acquire(1)
        elapsed = asyncio.get_event_loop().time() - start
        
        assert wait > 0.05  # Should wait ~0.1s for 1 token at rate 10/s
        assert elapsed > 0.05

    @pytest.mark.asyncio
    async def test_token_bucket_try_acquire(self):
        """Test try_acquire doesn't block."""
        bucket = RateLimitBucket(rate=10, capacity=10)
        
        # Should succeed
        assert await bucket.try_acquire(5) is True
        assert bucket.get_info().remaining == 5
        
        # Should fail when exhausted
        await bucket.acquire(5)
        assert await bucket.try_acquire(1) is False

    @pytest.mark.asyncio
    async def test_async_rate_limiter_multi_provider_isolation(self):
        """Test rate limiters for different providers are isolated."""
        limiter = AsyncRateLimiter()
        
        # Use tokens from provider A
        await limiter.acquire("provider_a", rate=10, capacity=10, tokens=5)
        # Use tokens from provider B
        await limiter.acquire("provider_b", rate=5, capacity=5, tokens=3)
        
        status_a = limiter.get_status("provider_a")
        status_b = limiter.get_status("provider_b")
        
        assert status_a.remaining == 5
        assert status_b.remaining == 2
        assert status_a.limit == 10
        assert status_b.limit == 5

    @pytest.mark.asyncio
    async def test_async_rate_limiter_reset(self):
        """Test rate limiter reset functionality."""
        limiter = AsyncRateLimiter()
        
        await limiter.acquire("test", rate=10, capacity=10, tokens=10)
        assert limiter.get_status("test").remaining == 0
        
        limiter.reset("test")
        assert limiter.get_status("test").remaining == 10
        
        limiter.reset()  # Reset all
        assert limiter.get_status("test").remaining == 10

    @pytest.mark.asyncio
    async def test_token_bucket_zero_rate(self):
        """Test token bucket with zero rate (allows initial burst but no refill)."""
        bucket = RateLimitBucket(rate=0, capacity=10)
        
        # Should be able to acquire from initial capacity
        wait = await bucket.acquire(5)
        assert wait == 0.0
        
        # After exhausting capacity, cannot acquire more (zero refill)
        wait = await bucket.acquire(5)
        assert wait == 0.0
        
        # Next acquire should wait forever (or very long)
        # Since rate=0, wait_time = needed / 0 = infinite
        import asyncio
        try:
            wait = await asyncio.wait_for(bucket.acquire(1), timeout=0.1)
            assert False, "Should have timed out"
        except asyncio.TimeoutError:
            pass  # Expected
        
        # get_info should not crash with zero rate when bucket is full
        bucket2 = RateLimitBucket(rate=0, capacity=10)
        info = bucket2.get_info()
        assert info.limit == 10
        assert info.remaining == 10


class TestRetryEdgeCases:
    """Edge case tests for retry logic."""

    @pytest.mark.asyncio
    async def test_retry_jitter_statistical(self):
        """Test jitter is applied statistically."""
        config = RetryConfig(
            max_retries=3,
            base_delay=1.0,
            max_delay=10.0,
            exponential_base=2.0,
            jitter=0.5,  # 50% jitter
        )
        
        delays = []
        for attempt in range(100):
            delay = get_retry_delay(attempt, 1.0, 10.0, 2.0, 0.5)
            delays.append(delay)
        
        # With 50% jitter, delays should vary
        assert max(delays) > min(delays)
        # All delays should be within expected bounds
        for i, d in enumerate(delays):
            base = min(1.0 * (2.0 ** i), 10.0)
            # Jitter is applied AFTER max_delay cap, so max can exceed max_delay
            expected_max = base * 1.5
            assert base <= d <= expected_max

    @pytest.mark.asyncio
    async def test_retry_max_delay_cap(self):
        """Test max_delay caps exponential backoff."""
        config = RetryConfig(
            max_retries=10,
            base_delay=1.0,
            max_delay=2.0,  # Cap at 2 seconds
            exponential_base=2.0,
            jitter=0.0,
        )
        
        call_count = [0]
        async def fail():
            call_count[0] += 1
            raise ConnectionError("fail")
        
        result = await retry_with_backoff(fail, config=config)
        
        assert not result.success
        assert result.attempts == 11  # initial + 10 retries
        # Total time should be bounded by max_delay * attempts
        assert result.total_time < 25.0  # Well under 11 * 2 = 22s

    @pytest.mark.asyncio
    async def test_retry_non_retryable_exception(self):
        """Test non-retryable exceptions are not retried."""
        config = RetryConfig(max_retries=3, base_delay=0.01)
        
        call_count = [0]
        async def fail_with_value_error():
            call_count[0] += 1
            raise ValueError("invalid input")
        
        result = await retry_with_backoff(fail_with_value_error, config=config)
        
        assert not result.success
        assert call_count[0] == 1  # Only one attempt, no retries
        assert isinstance(result.last_exception, ValueError)

    @pytest.mark.asyncio
    async def test_retry_unknown_exception(self):
        """Test unknown exceptions are not retried by default."""
        config = RetryConfig(max_retries=3, base_delay=0.01)
        
        call_count = [0]
        async def fail_with_runtime_error():
            call_count[0] += 1
            raise RuntimeError("unknown error")
        
        result = await retry_with_backoff(fail_with_runtime_error, config=config)
        
        assert not result.success
        assert call_count[0] == 1  # Only one attempt

    @pytest.mark.asyncio
    async def test_retry_sync_function(self):
        """Test retry works with sync functions (wrapped in async)."""
        config = RetryConfig(max_retries=2, base_delay=0.01)
        
        call_count = [0]
        def sync_fail():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ConnectionError("temp")
            return "success"
        
        # Wrap sync function
        async def async_wrapper():
            return sync_fail()
        
        result = await retry_with_backoff(async_wrapper, config=config)
        
        assert result.success
        assert result.result == "success"
        assert result.attempts == 3

    def test_is_retryable_error_comprehensive(self):
        """Test is_retryable_error covers all retryable exception types."""
        retryable = [
            ProviderUnavailableError("down"),
            ProviderTimeoutError("timeout"),
            RateLimitError("rate limited"),
            ConnectionError("connection failed"),
            TimeoutError("timeout"),
            RateLimitExceededError("exceeded", provider="test", limit=100, remaining=0),
        ]
        
        for exc in retryable:
            assert is_retryable_error(exc), f"{type(exc).__name__} should be retryable"
        
        non_retryable = [
            ValueError("invalid"),
            KeyError("missing"),
            TypeError("wrong type"),
            DataProviderError("generic"),
            ValidationError("validation failed"),
        ]
        
        for exc in non_retryable:
            assert not is_retryable_error(exc), f"{type(exc).__name__} should not be retryable"

    def test_get_retry_delay_edge_cases(self):
        """Test get_retry_delay with edge case parameters."""
        # Zero jitter
        assert get_retry_delay(0, 1.0, 60.0, 2.0, 0.0) == 1.0
        assert get_retry_delay(1, 1.0, 60.0, 2.0, 0.0) == 2.0
        assert get_retry_delay(2, 1.0, 60.0, 2.0, 0.0) == 4.0
        
        # Max delay cap
        assert get_retry_delay(10, 1.0, 5.0, 2.0, 0.0) == 5.0
        
        # High jitter
        delay = get_retry_delay(0, 1.0, 60.0, 2.0, 1.0)  # 100% jitter
        assert 1.0 <= delay <= 2.0


class TestExceptionEdgeCases:
    """Edge case tests for exception hierarchy."""

    def test_exception_chaining_preserves_cause(self):
        """Test exception chaining preserves original cause."""
        try:
            try:
                raise ValueError("original cause")
            except ValueError as e:
                raise ProviderResponseError("API failed", provider="zerodha", status_code=500) from e
        except ProviderResponseError as e:
            assert e.__cause__ is not None
            assert isinstance(e.__cause__, ValueError)
            assert str(e.__cause__) == "original cause"

    def test_exception_attributes_preserved(self):
        """Test custom exception attributes are preserved."""
        exc = DataNotFoundError(
            "Not found",
            symbol="RELIANCE",
            exchange="NSE",
            interval="minute",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )
        
        assert exc.symbol == "RELIANCE"
        assert exc.exchange == "NSE"
        assert exc.interval == "minute"
        assert exc.from_date == "2024-01-01"
        assert exc.to_date == "2024-01-31"

    def test_rate_limit_exception_attributes(self):
        """Test rate limit exception attributes."""
        exc = RateLimitExceededError(
            "Rate limit exceeded",
            provider="zerodha",
            limit=100,
            remaining=0,
            retry_after=60,
        )
        
        assert exc.provider == "zerodha"
        assert exc.limit == 100
        assert exc.remaining == 0
        assert exc.retry_after == 60

    def test_provider_response_error_attributes(self):
        """Test provider response error attributes."""
        exc = ProviderResponseError(
            "API error",
            provider="zerodha",
            status_code=429,
            error_type="rate_limit",
            error_code="TOO_MANY_REQUESTS",
        )
        
        assert exc.provider == "zerodha"
        assert exc.status_code == 429
        assert exc.error_type == "rate_limit"
        assert exc.error_code == "TOO_MANY_REQUESTS"

    def test_instrument_not_found_error_attributes(self):
        """Test instrument not found error attributes."""
        exc = InstrumentNotFoundError(
            "Instrument not found",
            symbol="INVALID",
            exchange="NSE",
        )
        
        assert exc.symbol == "INVALID"
        assert exc.exchange == "NSE"

    def test_exception_string_representation(self):
        """Test exception string representation includes context."""
        exc = DataProviderError("Test error", provider="zerodha", error_code="TEST")
        str_repr = str(exc)
        
        assert "Test error" in str_repr
        assert "zerodha" in str_repr
        assert "TEST" in str_repr


class TestModelEdgeCases:
    """Edge case tests for data models."""

    def test_normalized_ohlc_negative_values(self):
        """Test NormalizedOHLC handles negative prices (valid for some instruments)."""
        ohlc = NormalizedOHLC(
            symbol="TEST",
            exchange=Exchange.NSE,
            segment=Segment.EQ,
            interval=Interval.MINUTE_1,
            timestamp=datetime(2024, 1, 1, 9, 15, tzinfo=timezone.utc),
            open=-100.0,
            high=-90.0,
            low=-110.0,
            close=-95.0,
            volume=1000,
        )
        assert ohlc.open == -100.0
        assert ohlc.high == -90.0

    def test_normalized_ohlc_zero_volume(self):
        """Test NormalizedOHLC with zero volume."""
        ohlc = NormalizedOHLC(
            symbol="TEST",
            exchange=Exchange.NSE,
            segment=Segment.EQ,
            interval=Interval.MINUTE_1,
            timestamp=datetime(2024, 1, 1, 9, 15, tzinfo=timezone.utc),
            open=100.0,
            high=110.0,
            low=90.0,
            close=105.0,
            volume=0,
        )
        assert ohlc.volume == 0

    def test_normalized_ohlc_none_open_interest(self):
        """Test NormalizedOHLC with None open_interest."""
        ohlc = NormalizedOHLC(
            symbol="TEST",
            exchange=Exchange.NSE,
            segment=Segment.EQ,
            interval=Interval.MINUTE_1,
            timestamp=datetime(2024, 1, 1, 9, 15, tzinfo=timezone.utc),
            open=100.0,
            high=110.0,
            low=90.0,
            close=105.0,
            volume=1000,
            open_interest=None,
        )
        assert ohlc.open_interest is None

    def test_normalized_instrument_optional_fields(self):
        """Test NormalizedInstrument with optional fields."""
        inst = NormalizedInstrument(
            instrument_token="12345",
            symbol="RELIANCE",
            name="Reliance Industries",
            exchange=Exchange.NSE,
            segment=Segment.EQ,
            instrument_type=InstrumentType.EQ,
            lot_size=1,
            tick_size=0.05,
            expiry=None,
            strike=None,
        )
        assert inst.expiry is None
        assert inst.strike is None

    def test_normalized_instrument_with_expiry_strike(self):
        """Test NormalizedInstrument with expiry and strike for derivatives."""
        inst = NormalizedInstrument(
            instrument_token="12345",
            symbol="RELIANCE24JAN2500CE",
            name="RELIANCE 2500 CALL",
            exchange=Exchange.NFO,
            segment=Segment.FO,
            instrument_type=InstrumentType.OPT,
            lot_size=250,
            tick_size=0.05,
            expiry=datetime(2024, 1, 25, tzinfo=timezone.utc),
            strike=2500.0,
        )
        assert inst.expiry is not None
        assert inst.strike == 2500.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])