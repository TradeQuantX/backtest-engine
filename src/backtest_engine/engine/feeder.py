"""
Parquet Data Feeder — fetches base-interval OHLC via DataProviderClient.

Implements DataFeeder for provider-agnostic data access.
Future feeders (MongoDB, TimescaleDB) implement the same protocol.
"""

from backtest_engine.data_provider.client import DataProviderClient
from backtest_engine.engine.interfaces import (
    BacktestConfig,
    DataFeeder,
    NormalizedOHLC,
)


class ParquetDataFeeder:
    """
    Data feeder that uses the existing DataProviderClient to fetch historical data.
    
    Reuses all existing infrastructure:
    - Async initialization & authentication
    - Caching (DiskCache + MemoryCache)
    - Request chunking (provider-specific limits)
    - Retry with exponential backoff + jitter
    - Rate limiting (token bucket per provider)
    - Data normalization to NormalizedOHLC
    - Parquet storage persistence
    
    This is the ONLY feeder implementation in Phase 1.
    The DataFeeder protocol seam allows future feeders without changing the engine.
    """
    
    def __init__(self, client: DataProviderClient | None = None):
        """
        Initialize the feeder.
        
        Args:
            client: Optional pre-configured DataProviderClient.
                   If None, creates a new one with default config.
        """
        self._client = client or DataProviderClient()
        self._initialized = False
    
    async def fetch_base_series(self, config: BacktestConfig) -> list[NormalizedOHLC]:
        """
        Fetch base-interval OHLC data for the configured symbol/date range.
        
        Args:
            config: BacktestConfig with symbol, exchange, segment, base_interval, dates
            
        Returns:
            List of NormalizedOHLC at the base_interval (e.g., 1-minute bars)
            
        Raises:
            DataNotFoundError: No data available for the request
            ValidationError: Invalid request parameters
            ProviderError: Provider-specific failures
        """
        if not self._initialized:
            await self._client.initialize()
            self._initialized = True
        
        # Convert BacktestConfig to individual parameters for DataProviderClient
        response = await self._client.get_historical_ohlc_data(
            symbol=config.symbol,
            exchange=config.exchange.value,
            segment=config.segment.value,
            interval=config.base_interval.value,
            from_date=config.from_date,
            to_date=config.to_date,
            continuous=False,
            oi=False,
        )
        
        if not response.data:
            from backtest_engine.data_provider.exceptions import DataNotFoundError
            raise DataNotFoundError(
                f"No data found for {config.symbol} {config.exchange.value} "
                f"{config.segment.value} {config.base_interval.value} "
                f"{config.from_date} to {config.to_date}",
                provider=response.provider,
            )
        
        return response.data
    
    async def close(self) -> None:
        """Close the underlying client connections."""
        if self._initialized:
            await self._client.close()
            self._initialized = False
    
    async def __aenter__(self) -> "ParquetDataFeeder":
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()