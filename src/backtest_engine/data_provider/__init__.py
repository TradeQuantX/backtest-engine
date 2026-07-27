"""
Data Provider Layer for Backtest Engine.

A unified interface for accessing historical market data from multiple providers
(Zerodha, Dhan, etc.) with built-in caching, rate limiting, and data normalization.

Usage:
    from backtest_engine.data_provider import DataProviderClient
    
    client = DataProviderClient()
    
    data = await client.get_historical_ohlc_data(
        symbol="RELIANCE",
        exchange="NSE",
        segment="EQ",
        interval="minute",
        from_date="2024-01-01",
        to_date="2024-01-31"
    )
"""

from backtest_engine.data_provider.client import DataProviderClient, get_historical_data
from backtest_engine.data_provider.exceptions import (
    DataProviderError,
    ConfigurationError,
    AuthError,
    RateLimitError,
    DataError,
    ProviderError,
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
from backtest_engine.shared.types import (
    Exchange,
    Segment,
    Interval,
    InstrumentType,
)

__all__ = [
    # Client
    "DataProviderClient",
    "get_historical_data",
    # Exceptions
    "DataProviderError",
    "ConfigurationError",
    "AuthError",
    "RateLimitError",
    "DataError",
    "ProviderError",
    # Interfaces
    "CacheProtocol",
    "DataProviderProtocol",
    "HistoricalDataRequest",
    "HistoricalDataResponse",
    "NormalizedInstrument",
    "NormalizedOHLC",
    "StorageProtocol",
    # Models
    "Exchange",
    "Segment",
    "Interval",
    "InstrumentType",
]

__version__ = "0.1.0"