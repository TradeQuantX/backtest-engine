"""
Base provider class with common functionality.

All providers should inherit from this class.
"""

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Optional

import polars as pl

from backtest_engine.data_provider.config import DataProviderConfig, ProviderConfig
from backtest_engine.data_provider.exceptions import (
    DataNotFoundError,
    InstrumentNotFoundError,
    ProviderError,
    RateLimitExceededError,
    UnsupportedIntervalError,
)
from backtest_engine.data_provider.interfaces import (
    CacheProtocol,
    DataProviderProtocol,
    HistoricalDataRequest,
    HistoricalDataResponse,
    NormalizedInstrument,
    NormalizedOHLC,
    StorageProtocol,
)
from backtest_engine.data_provider.utils import (
    AsyncRateLimiter,
    ChunkingConfig,
    IST,
    RetryConfig,
    chunk_date_range,
    get_rate_limiter,
    retry_with_backoff,
    validate_historical_request,
    validate_ohlc_data,
)
from backtest_engine.data_provider.utils.normalization import normalized_to_polars


class BaseProvider(DataProviderProtocol, ABC):
    """
    Base class for all data providers.
    
    Provides common functionality:
    - Rate limiting
    - Retry logic
    - Request chunking
    - Caching
    - Storage
    - Data validation
    """
    
    def __init__(
        self,
        config: ProviderConfig,
        global_config: DataProviderConfig,
        cache: Optional[CacheProtocol] = None,
        storage: Optional[StorageProtocol] = None,
    ):
        self.config = config
        self.global_config = global_config
        self.cache = cache
        self.storage = storage
        
        # Rate limiter
        self._rate_limiter = get_rate_limiter()
        
        # Chunking config
        self._chunking_config = ChunkingConfig()
        
        # Retry config
        self._retry_config = RetryConfig(
            max_retries=global_config.max_retries,
            base_delay=global_config.retry_base_delay,
            max_delay=global_config.retry_max_delay,
            exponential_base=global_config.retry_exponential_base,
        )
        
        # Authentication state
        self._access_token: Optional[str] = None
        self._authenticated = False
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
        ...
    
    @property
    @abstractmethod
    def supported_exchanges(self) -> list[str]:
        """Supported exchanges."""
        ...
    
    @property
    @abstractmethod
    def supported_intervals(self) -> list[str]:
        """Supported intervals."""
        ...
    
    @abstractmethod
    async def _do_authenticate(self) -> str:
        """Perform actual authentication. Returns access token."""
        ...
    
    @abstractmethod
    async def _do_get_instruments(
        self,
        exchange: Optional[str] = None,
        segment: Optional[str] = None,
    ) -> list[NormalizedInstrument]:
        """Fetch instruments from provider API."""
        ...
    
    @abstractmethod
    async def _do_get_historical_data(
        self,
        request: HistoricalDataRequest,
    ) -> HistoricalDataResponse:
        """Fetch historical data from provider API."""
        ...
    
    @abstractmethod
    async def _do_get_instrument_token(
        self,
        symbol: str,
        exchange: str,
        segment: str,
        expiry: Optional[datetime] = None,
        strike: Optional[float] = None,
        instrument_type: Optional[str] = None,
    ) -> Optional[str]:
        """Get provider-specific instrument token."""
        ...
    
    async def authenticate(self) -> bool:
        """Authenticate with the provider."""
        try:
            self._access_token = await self._do_authenticate()
            self._authenticated = True
            return True
        except Exception as e:
            self._authenticated = False
            raise
    
    async def is_authenticated(self) -> bool:
        """Check if authenticated."""
        return self._authenticated and self._access_token is not None
    
    async def get_instruments(
        self,
        exchange: Optional[str] = None,
        segment: Optional[str] = None,
        force_refresh: bool = False,
    ) -> list[NormalizedInstrument]:
        """Get instrument master with caching."""
        cache_key = f"instruments:{self.name}:{exchange or 'all'}:{segment or 'all'}"
        
        # Check cache first
        if not force_refresh and self.cache:
            cached = await self.cache.get(cache_key)
            if cached and not cached.is_expired:
                return cached.value
        
        # Fetch from provider
        instruments = await self._do_get_instruments(exchange, segment)
        
        # Cache result only if we got instruments (don't cache empty results)
        if instruments and self.cache:
            from backtest_engine.data_provider.interfaces.cache import CacheEntry
            entry = CacheEntry(
                key=cache_key,
                value=instruments,
                created_at=datetime.now(IST),
                expires_at=datetime.now(IST) + timedelta(
                    seconds=self.global_config.instrument_cache_ttl_seconds
                ),
            )
            await self.cache.set(entry)
        
        return instruments
    
    async def get_historical_data(
        self,
        request: HistoricalDataRequest,
    ) -> HistoricalDataResponse:
        """Get historical data with chunking, caching, and retry."""
        # Validate request
        errors = validate_historical_request(request)
        if errors:
            raise ValueError(f"Invalid request: {errors}")
        
        # Check cache first
        cache_key = self._make_cache_key(request)
        if self.cache:
            cached = await self.cache.get(cache_key)
            if cached and not cached.is_expired:
                response = cached.value
                # Create new response with cached=True (frozen dataclass)
                return HistoricalDataResponse(
                    data=response.data,
                    symbol=response.symbol,
                    exchange=response.exchange,
                    segment=response.segment,
                    interval=response.interval,
                    from_date=response.from_date,
                    to_date=response.to_date,
                    provider=response.provider,
                    cached=True,
                )
        
        # Check storage
        if self.storage:
            stored = await self._read_from_storage(request)
            if stored and stored.data:  # Check if list is not empty
                response = HistoricalDataResponse(
                    data=stored.data,
                    symbol=request.symbol,
                    exchange=request.exchange,
                    segment=request.segment,
                    interval=request.interval,
                    from_date=request.from_date,
                    to_date=request.to_date,
                    provider=self.name,
                    cached=True,
                )
                # Also cache in memory
                if self.cache:
                    from backtest_engine.data_provider.interfaces.cache import CacheEntry
                    entry = CacheEntry(
                        key=cache_key,
                        value=response,
                        created_at=datetime.now(IST),
                    )
                    await self.cache.set(entry)
                return response
        
        # Chunk the request
        chunks = chunk_date_range(
            request.from_date,
            request.to_date,
            request.interval,
            self._chunking_config,
        )
        
        all_data = []
        
        for chunk in chunks:
            chunk_request = HistoricalDataRequest(
                symbol=request.symbol,
                exchange=request.exchange,
                segment=request.segment,
                interval=request.interval,
                from_date=chunk.from_date,
                to_date=chunk.to_date,
                continuous=request.continuous,
                oi=request.oi,
            )
            
            # Fetch with retry and rate limiting
            chunk_data = await self._fetch_chunk_with_retry(chunk_request)
            all_data.extend(chunk_data)
        
        # Validate combined data
        errors = validate_ohlc_data(all_data)
        if errors:
            # Log warnings but don't fail
            pass
        
        # Create response
        response = HistoricalDataResponse(
            data=all_data,
            symbol=request.symbol,
            exchange=request.exchange,
            segment=request.segment,
            interval=request.interval,
            from_date=request.from_date,
            to_date=request.to_date,
            provider=self.name,
            cached=False,
        )
        
        # Cache response
        if self.cache:
            from backtest_engine.data_provider.interfaces.cache import CacheEntry
            entry = CacheEntry(
                key=cache_key,
                value=response,
                created_at=datetime.now(IST),
            )
            await self.cache.set(entry)
        
        # Store to persistent storage
        if self.storage and all_data:
            df = normalized_to_polars(all_data)
            await self._write_to_storage(df, request)
        
        return response
    
    async def _fetch_chunk_with_retry(
        self,
        request: HistoricalDataRequest,
    ) -> list[NormalizedOHLC]:
        """Fetch a single chunk with retry and rate limiting."""
        
        async def _fetch():
            # Rate limiting
            await self._rate_limiter.acquire(
                self.name,
                self.config.rate_limit_per_second,
                int(self.config.rate_limit_per_second * 2),  # burst capacity
            )
            
            return await self._do_get_historical_data(request)
        
        result = await retry_with_backoff(_fetch, config=self._retry_config)
        
        if not result.success:
            raise result.last_exception or ProviderError(
                f"Failed to fetch data after {self._retry_config.max_retries} retries",
                provider=self.name,
            )
        
        return result.result.data
    
    def _make_cache_key(self, request: HistoricalDataRequest) -> str:
        """Generate cache key for request."""
        return (
            f"ohlc:{self.name}:"
            f"{request.symbol}:"
            f"{request.exchange.value}:"
            f"{request.segment.value}:"
            f"{request.interval.value}:"
            f"{request.from_date.date()}:"
            f"{request.to_date.date()}:"
            f"{request.continuous}:"
            f"{request.oi}"
        )
    
    async def _read_from_storage(
        self,
        request: HistoricalDataRequest,
    ) -> Optional[HistoricalDataResponse]:
        """Read data from persistent storage."""
        if not self.storage:
            return None
        
        from backtest_engine.data_provider.interfaces.storage import StorageConfig
        
        config = StorageConfig(
            base_path=str(self.global_config.data_dir),
            provider=self.name,
            exchange=request.exchange.value,
            segment=request.segment.value,
            symbol=request.symbol,
            timeframe=request.interval.value,
            partition_by=self.global_config.storage_partition_by,
            compression=self.global_config.storage_compression,
            row_group_size=self.global_config.storage_row_group_size,
        )
        
        result = await self.storage.read_ohlc(
            config,
            from_date=request.from_date,
            to_date=request.to_date,
        )
        
        if result.success and result.data is not None:
            data = self._polars_to_normalized(result.data, request)
            if data:  # Check if list is not empty
                return HistoricalDataResponse(
                    data=data,
                    symbol=request.symbol,
                    exchange=request.exchange,
                    segment=request.segment,
                    interval=request.interval,
                    from_date=request.from_date,
                    to_date=request.to_date,
                    provider=self.name,
                    cached=True,
                )
        
        return None
    
    async def _write_to_storage(
        self,
        df: pl.DataFrame,
        request: HistoricalDataRequest,
    ) -> None:
        """Write data to persistent storage."""
        if not self.storage:
            return
        
        from backtest_engine.data_provider.interfaces.storage import StorageConfig
        
        config = StorageConfig(
            base_path=str(self.global_config.data_dir),
            provider=self.name,
            exchange=request.exchange.value,
            segment=request.segment.value,
            symbol=request.symbol,
            timeframe=request.interval.value,
            partition_by=self.global_config.storage_partition_by,
            compression=self.global_config.storage_compression,
            row_group_size=self.global_config.storage_row_group_size,
        )
        
        await self.storage.write_ohlc(df, config, mode="append")
    
    def _polars_to_normalized(
        self,
        df: pl.DataFrame,
        request: HistoricalDataRequest,
    ) -> list[NormalizedOHLC]:
        """Convert Polars DataFrame to NormalizedOHLC list."""
        from backtest_engine.data_provider.utils import polars_to_normalized
        return polars_to_normalized(df)
    
    async def get_instrument_token(
        self,
        symbol: str,
        exchange: str,
        segment: str,
        expiry: Optional[datetime] = None,
        strike: Optional[float] = None,
        instrument_type: Optional[str] = None,
    ) -> Optional[str]:
        """Get instrument token with caching."""
        cache_key = f"token:{self.name}:{symbol}:{exchange}:{segment}:{expiry}:{strike}:{instrument_type}"
        
        if self.cache:
            cached = await self.cache.get(cache_key)
            if cached and not cached.is_expired:
                return cached.value
        
        token = await self._do_get_instrument_token(
            symbol, exchange, segment, expiry, strike, instrument_type
        )
        
        if token and self.cache:
            from backtest_engine.data_provider.interfaces.cache import CacheEntry
            entry = CacheEntry(
                key=cache_key,
                value=token,
                created_at=datetime.now(IST),
                expires_at=datetime.now(IST) + timedelta(days=1),
            )
            await self.cache.set(entry)
        
        return token
    
    async def close(self) -> None:
        """Close connections."""
        pass
    
    def get_rate_limit_info(self) -> dict:
        """Get current rate limit status."""
        return self._rate_limiter.get_status(self.name)