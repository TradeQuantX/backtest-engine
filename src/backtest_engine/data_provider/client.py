"""
Main client for the data provider layer.

This is the single entry point for researchers to access historical data.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from backtest_engine.data_provider.config import (
    ConfigLoader,
    DataProviderConfig,
    DhanConfig,
    ZerodhaConfig,
    load_config,
)
from backtest_engine.data_provider.exceptions import (
    ConfigurationError,
    ProviderNotFoundError,
)
from backtest_engine.data_provider.interfaces import (
    CacheProtocol,
    HistoricalDataRequest,
    HistoricalDataResponse,
    NormalizedInstrument,
    NormalizedOHLC,
    StorageProtocol,
)
from backtest_engine.data_provider.providers import ProviderRegistry
from backtest_engine.data_provider.providers.base import BaseProvider


class DataProviderClient:
    """
    Main client for accessing historical market data.
    
    Automatically handles:
    - Configuration loading (priority: env vars > ~/.tradex/config.yml > ./config.yml)
    - Provider selection and initialization
    - Authentication
    - Caching
    - Storage
    - Rate limiting
    - Request chunking
    - Data normalization
    
    Usage:
        client = DataProviderClient()
        
        data = client.get_historical_ohlc_data(
            symbol="RELIANCE",
            exchange="NSE",
            segment="EQ",
            interval="minute",
            from_date="2024-01-01",
            to_date="2024-01-31"
        )
    """
    
    def __init__(
        self,
        config: Optional[DataProviderConfig] = None,
        project_config: Optional[Path] = None,
        user_config: Optional[Path] = None,
        cache: Optional[CacheProtocol] = None,
        storage: Optional[StorageProtocol] = None,
    ):
        """
        Initialize the data provider client.
        
        Args:
            config: Pre-loaded configuration (optional)
            project_config: Path to project config.yml
            user_config: Path to user config.yml
            cache: Cache implementation (optional)
            storage: Storage implementation (optional)
        """
        self._config = config
        self._project_config = project_config
        self._user_config = user_config
        self._cache = cache
        self._storage = storage
        self._providers: dict[str, BaseProvider] = {}
        self._default_provider: Optional[BaseProvider] = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize the client (load config, create providers, authenticate)."""
        if self._initialized:
            return
        
        # Load configuration
        if self._config is None:
            self._config = load_config(self._project_config, self._user_config)
        
        # Create cache and storage if not provided
        if self._cache is None:
            self._cache = await self._create_cache()
        
        if self._storage is None:
            self._storage = await self._create_storage()
        
        # Create providers
        await self._create_providers()
        
        # Authenticate default provider
        if self._default_provider:
            await self._default_provider.authenticate()
        
        self._initialized = True
    
    async def _create_cache(self) -> CacheProtocol:
        """Create cache implementation."""
        from backtest_engine.data_provider.cache import DiskCache
        
        cache_dir = self._config.resolve_path(self._config.cache_dir)
        return DiskCache(cache_dir)
    
    async def _create_storage(self) -> StorageProtocol:
        """Create storage implementation."""
        from backtest_engine.data_provider.storage import ParquetStorage
        
        data_dir = self._config.resolve_path(self._config.data_dir)
        return ParquetStorage(data_dir)
    
    async def _create_providers(self) -> None:
        """Create provider instances from configuration."""
        enabled_providers = self._config.get_enabled_providers()
        
        if not enabled_providers:
            raise ConfigurationError(
                "No providers enabled in configuration",
                provider="config",
            )
        
        for provider_config in enabled_providers:
            provider = ProviderRegistry.create_provider(
                provider_config.name,
                provider_config,
                self._config,
                self._cache,
                self._storage,
            )
            
            if provider:
                self._providers[provider_config.name] = provider
                
                # Set as default if it's the default provider
                if provider_config.name == self._config.default_provider:
                    self._default_provider = provider
        
        # If default provider not found, use first enabled
        if not self._default_provider and self._providers:
            self._default_provider = list(self._providers.values())[0]
    
    def get_provider(self, name: str) -> Optional[BaseProvider]:
        """Get a specific provider by name."""
        return self._providers.get(name)
    
    def get_default_provider(self) -> BaseProvider:
        """Get the default provider."""
        if not self._default_provider:
            raise ProviderNotFoundError(
                "No default provider available",
                provider=self._config.default_provider if self._config else "unknown",
            )
        return self._default_provider
    
    async def get_historical_ohlc_data(
        self,
        symbol: str,
        exchange: str,
        segment: str,
        interval: str,
        from_date: str | datetime,
        to_date: str | datetime,
        provider: Optional[str] = None,
        continuous: bool = False,
        oi: bool = False,
    ) -> HistoricalDataResponse:
        """
        Get historical OHLC data.
        
        Args:
            symbol: Trading symbol (e.g., "RELIANCE")
            exchange: Exchange code (e.g., "NSE", "BSE")
            segment: Market segment (e.g., "EQ", "FO")
            interval: Time interval (e.g., "minute", "5minute", "day")
            from_date: Start date (string or datetime)
            to_date: End date (string or datetime)
            provider: Specific provider to use (optional)
            continuous: Get continuous contract data (for futures)
            oi: Include open interest data
            
        Returns:
            HistoricalDataResponse with normalized OHLC data
        """
        await self.initialize()
        
        # Parse dates
        if isinstance(from_date, str):
            from_date = datetime.fromisoformat(from_date)
        if isinstance(to_date, str):
            to_date = datetime.fromisoformat(to_date)
        
        # Normalize enums
        from backtest_engine.data_provider.interfaces.models import (
            Exchange,
            Interval,
            Segment,
        )
        
        request = HistoricalDataRequest(
            symbol=symbol,
            exchange=Exchange(exchange.upper()),
            segment=Segment(segment.upper()),
            interval=Interval(interval.lower()),
            from_date=from_date,
            to_date=to_date,
            continuous=continuous,
            oi=oi,
        )
        
        # Get provider
        if provider:
            prov = self.get_provider(provider)
            if not prov:
                raise ProviderNotFoundError(f"Provider not found: {provider}")
        else:
            prov = self.get_default_provider()
        
        return await prov.get_historical_data(request)
    
    async def get_instruments(
        self,
        exchange: Optional[str] = None,
        segment: Optional[str] = None,
        provider: Optional[str] = None,
        force_refresh: bool = False,
    ) -> list[NormalizedInstrument]:
        """
        Get instrument master.
        
        Args:
            exchange: Filter by exchange
            segment: Filter by segment
            provider: Specific provider to use
            force_refresh: Force refresh from provider
            
        Returns:
            List of normalized instruments
        """
        await self.initialize()
        
        if provider:
            prov = self.get_provider(provider)
            if not prov:
                raise ProviderNotFoundError(f"Provider not found: {provider}")
        else:
            prov = self.get_default_provider()
        
        return await prov.get_instruments(exchange, segment, force_refresh)
    
    async def get_instrument_token(
        self,
        symbol: str,
        exchange: str,
        segment: str,
        expiry: Optional[datetime] = None,
        strike: Optional[float] = None,
        instrument_type: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> Optional[str]:
        """Get provider-specific instrument token."""
        await self.initialize()
        
        if provider:
            prov = self.get_provider(provider)
            if not prov:
                raise ProviderNotFoundError(f"Provider not found: {provider}")
        else:
            prov = self.get_default_provider()
        
        return await prov.get_instrument_token(
            symbol, exchange, segment, expiry, strike, instrument_type
        )
    
    async def close(self) -> None:
        """Close all provider connections."""
        for provider in self._providers.values():
            await provider.close()
        self._providers.clear()
        self._default_provider = None
        self._initialized = False
    
    def __enter__(self):
        """Sync context manager entry."""
        import asyncio
        asyncio.run(self.initialize())
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Sync context manager exit."""
        import asyncio
        asyncio.run(self.close())
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


# Convenience function for simple usage
async def get_historical_data(
    symbol: str,
    exchange: str,
    segment: str,
    interval: str,
    from_date: str | datetime,
    to_date: str | datetime,
    **kwargs,
) -> HistoricalDataResponse:
    """
    Convenience function for one-off data requests.
    
    Usage:
        data = await get_historical_data(
            symbol="RELIANCE",
            exchange="NSE",
            segment="EQ",
            interval="minute",
            from_date="2024-01-01",
            to_date="2024-01-31"
        )
    """
    async with DataProviderClient() as client:
        return await client.get_historical_ohlc_data(
            symbol=symbol,
            exchange=exchange,
            segment=segment,
            interval=interval,
            from_date=from_date,
            to_date=to_date,
            **kwargs,
        )