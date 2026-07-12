"""
Tests for the data provider layer.
"""

import pytest
from datetime import datetime, timedelta, timezone

from backtest_engine.data_provider.interfaces.models import (
    Exchange,
    Segment,
    Interval,
    NormalizedOHLC,
    NormalizedInstrument,
    InstrumentType,
)
from backtest_engine.data_provider.utils.normalization import (
    normalize_timestamp,
    normalize_interval,
    normalize_exchange,
    normalize_segment,
    normalize_instrument_type,
)
from backtest_engine.data_provider.utils.chunking import (
    chunk_date_range,
    estimate_chunks,
    DateChunk,
    ChunkingConfig,
)
from backtest_engine.data_provider.utils.rate_limiter import (
    TokenBucket,
    AsyncRateLimiter,
)
from backtest_engine.data_provider.utils.retry import (
    RetryConfig,
    retry_with_backoff,
    is_retryable_error,
)
from backtest_engine.data_provider.exceptions import (
    DataProviderError,
    AuthError,
    TokenExpiredError,
    RateLimitError,
    RateLimitExceededError,
    DataNotFoundError,
    ProviderResponseError,
    InstrumentNotFoundError,
)


class TestModels:
    """Test normalized data models."""
    
    def test_normalized_ohlc_creation(self):
        """Test creating NormalizedOHLC."""
        ohlc = NormalizedOHLC(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            segment=Segment.EQ,
            interval=Interval.MINUTE_1,
            timestamp=datetime(2024, 1, 1, 9, 15, tzinfo=timezone.utc),
            open=2500.0,
            high=2510.0,
            low=2495.0,
            close=2505.0,
            volume=100000,
            open_interest=50000,
        )
        
        assert ohlc.symbol == "RELIANCE"
        assert ohlc.exchange == Exchange.NSE
        assert ohlc.segment == Segment.EQ
        assert ohlc.interval == Interval.MINUTE_1
        assert ohlc.open == 2500.0
        assert ohlc.high == 2510.0
        assert ohlc.low == 2495.0
        assert ohlc.close == 2505.0
        assert ohlc.volume == 100000
        assert ohlc.open_interest == 50000
    
    def test_normalized_instrument_creation(self):
        """Test creating NormalizedInstrument."""
        inst = NormalizedInstrument(
            instrument_token="12345",
            symbol="RELIANCE",
            name="Reliance Industries Ltd",
            exchange=Exchange.NSE,
            segment=Segment.EQ,
            instrument_type=InstrumentType.EQ,
            lot_size=1,
            tick_size=0.05,
        )
        
        assert inst.instrument_token == "12345"
        assert inst.symbol == "RELIANCE"
        assert inst.exchange == Exchange.NSE
        assert inst.segment == Segment.EQ
        assert inst.instrument_type == InstrumentType.EQ


class TestNormalization:
    """Test data normalization utilities."""
    
    def test_normalize_timestamp_string(self):
        """Test timestamp normalization from string."""
        ts = normalize_timestamp("2024-01-01 09:15:00")
        assert isinstance(ts, datetime)
        assert ts.year == 2024
        assert ts.month == 1
        assert ts.day == 1
    
    def test_normalize_timestamp_epoch(self):
        """Test timestamp normalization from epoch."""
        ts = normalize_timestamp(1704092100)  # 2024-01-01 09:15:00 UTC
        assert isinstance(ts, datetime)
        assert ts.year == 2024
    
    def test_normalize_interval_zerodha(self):
        """Test interval normalization for Zerodha."""
        assert normalize_interval("minute", "zerodha") == Interval.MINUTE_1
        assert normalize_interval("5minute", "zerodha") == Interval.MINUTE_5
        assert normalize_interval("day", "zerodha") == Interval.DAY
    
    def test_normalize_interval_dhan(self):
        """Test interval normalization for Dhan."""
        assert normalize_interval("1", "dhan") == Interval.MINUTE_1
        assert normalize_interval("5", "dhan") == Interval.MINUTE_5
        assert normalize_interval("day", "dhan") == Interval.DAY
    
    def test_normalize_exchange_zerodha(self):
        """Test exchange normalization for Zerodha."""
        assert normalize_exchange("NSE", "zerodha") == Exchange.NSE
        assert normalize_exchange("BSE", "zerodha") == Exchange.BSE
        assert normalize_exchange("NFO", "zerodha") == Exchange.NFO
    
    def test_normalize_exchange_dhan(self):
        """Test exchange normalization for Dhan."""
        assert normalize_exchange("NSE_EQ", "dhan") == Exchange.NSE
        assert normalize_exchange("BSE_EQ", "dhan") == Exchange.BSE
        assert normalize_exchange("NSE_FNO", "dhan") == Exchange.NFO
    
    def test_normalize_segment_zerodha(self):
        """Test segment normalization for Zerodha."""
        assert normalize_segment("EQ", "zerodha") == Segment.EQ
        assert normalize_segment("FO", "zerodha") == Segment.FO
    
    def test_normalize_segment_dhan(self):
        """Test segment normalization for Dhan."""
        assert normalize_segment("EQUITY", "dhan") == Segment.EQ
        assert normalize_segment("FUTURES", "dhan") == Segment.FO
        assert normalize_segment("OPTIONS", "dhan") == Segment.FO


class TestChunking:
    """Test date range chunking."""
    
    def test_chunk_date_range_single(self):
        """Test chunking when range fits in one chunk."""
        from_date = datetime(2024, 1, 1)
        to_date = datetime(2024, 1, 15)
        
        chunks = chunk_date_range(from_date, to_date, "minute")
        
        assert len(chunks) == 1
        assert chunks[0].from_date == from_date
        assert chunks[0].to_date == to_date
        assert chunks[0].chunk_index == 0
        assert chunks[0].total_chunks == 1
    
    def test_chunk_date_range_multiple(self):
        """Test chunking when range spans multiple chunks."""
        from_date = datetime(2024, 1, 1)
        to_date = datetime(2024, 2, 15)  # ~45 days
        
        chunks = chunk_date_range(from_date, to_date, "minute")
        
        # minute has max 30 days
        assert len(chunks) == 2
        assert chunks[0].from_date == from_date
        assert chunks[-1].to_date == to_date
    
    def test_chunk_date_range_daily(self):
        """Test chunking for daily interval."""
        from_date = datetime(2024, 1, 1)
        to_date = datetime(2025, 1, 1)  # ~365 days
        
        chunks = chunk_date_range(from_date, to_date, "day")
        
        # day has max 2000 days
        assert len(chunks) == 1
    
    def test_estimate_chunks(self):
        """Test chunk estimation."""
        from_date = datetime(2024, 1, 1)
        to_date = datetime(2024, 2, 15)
        
        count = estimate_chunks(from_date, to_date, "minute")
        assert count == 2


class TestRateLimiter:
    """Test token bucket rate limiter."""
    
    @pytest.mark.asyncio
    async def test_token_bucket_basic(self):
        """Test basic token bucket operation."""
        bucket = TokenBucket(rate=10, capacity=10)
        
        # Should be able to acquire immediately
        wait = await bucket.acquire(5)
        assert wait == 0.0
        
        info = bucket.get_info()
        assert info.remaining == 5
    
    @pytest.mark.asyncio
    async def test_token_bucket_refill(self):
        """Test token bucket refill over time."""
        bucket = TokenBucket(rate=10, capacity=10)
        
        # Use all tokens
        await bucket.acquire(10)
        info = bucket.get_info()
        assert info.remaining == 0
        
        # Wait for refill
        import asyncio
        await asyncio.sleep(0.5)
        
        info = bucket.get_info()
        assert info.remaining >= 4  # ~5 tokens refilled
    
    @pytest.mark.asyncio
    async def test_async_rate_limiter(self):
        """Test async rate limiter."""
        limiter = AsyncRateLimiter()
        
        # Acquire tokens
        wait = await limiter.acquire("test_provider", rate=10, capacity=10, tokens=5)
        assert wait == 0.0
        
        status = limiter.get_status("test_provider")
        assert status is not None
        assert status.remaining == 5


class TestRetry:
    """Test retry logic."""
    
    @pytest.mark.asyncio
    async def test_retry_success(self):
        """Test successful retry."""
        call_count = 0
        
        async def succeed():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = await retry_with_backoff(succeed)
        
        assert result.success
        assert result.result == "success"
        assert result.attempts == 1
    
    @pytest.mark.asyncio
    async def test_retry_eventual_success(self):
        """Test retry with eventual success."""
        call_count = 0
        
        async def fail_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Temporary failure")
            return "success"
        
        config = RetryConfig(max_retries=3, base_delay=0.01)
        result = await retry_with_backoff(fail_twice, config=config)
        
        assert result.success
        assert result.result == "success"
        assert result.attempts == 3
    
    @pytest.mark.asyncio
    async def test_retry_exhausted(self):
        """Test retry exhaustion."""
        async def always_fail():
            raise ConnectionError("Permanent failure")
        
        config = RetryConfig(max_retries=2, base_delay=0.01)
        result = await retry_with_backoff(always_fail, config=config)
        
        assert not result.success
        assert result.attempts == 3  # initial + 2 retries
        assert isinstance(result.last_exception, ConnectionError)
    
    def test_is_retryable_error(self):
        """Test retryable error detection."""
        from backtest_engine.data_provider.exceptions import (
            ProviderUnavailableError,
            ProviderTimeoutError,
            RateLimitExceededError,
        )
        
        assert is_retryable_error(ProviderUnavailableError("down"))
        assert is_retryable_error(ProviderTimeoutError("timeout"))
        assert is_retryable_error(RateLimitExceededError("rate limited"))
        assert is_retryable_error(ConnectionError("connection failed"))
        assert is_retryable_error(TimeoutError("timeout"))
        
        # Non-retryable
        assert not is_retryable_error(ValueError("invalid value"))


class TestExceptions:
    """Test exception hierarchy."""
    
    def test_base_exception(self):
        """Test base exception."""
        exc = DataProviderError("Test error", provider="zerodha", error_code="TEST")
        
        assert str(exc) == "Test error | provider=zerodha | code=TEST"
        assert exc.provider == "zerodha"
        assert exc.error_code == "TEST"
    
    def test_auth_exceptions(self):
        """Test authentication exceptions."""
        exc = AuthError("Auth failed", provider="zerodha")
        assert isinstance(exc, DataProviderError)
        
        exc = TokenExpiredError("Token expired", provider="zerodha")
        assert isinstance(exc, AuthError)
    
    def test_rate_limit_exceptions(self):
        """Test rate limit exceptions."""
        exc = RateLimitError("Rate limited", provider="zerodha", retry_after=60)
        assert exc.retry_after == 60
        
        exc = RateLimitExceededError("Exceeded", provider="zerodha", limit=100, remaining=0)
        assert exc.limit == 100
        assert exc.remaining == 0
    
    def test_data_exceptions(self):
        """Test data exceptions."""
        exc = DataNotFoundError("Not found", symbol="RELIANCE", exchange="NSE")
        assert exc.symbol == "RELIANCE"
        assert exc.exchange == "NSE"
    
    def test_provider_exceptions(self):
        """Test provider exceptions."""
        exc = ProviderResponseError("API error", provider="zerodha", status_code=500)
        assert exc.status_code == 500
        
        exc = InstrumentNotFoundError("Not found", symbol="RELIANCE", exchange="NSE")
        assert exc.symbol == "RELIANCE"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])