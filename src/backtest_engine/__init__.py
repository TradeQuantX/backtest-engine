"""
TradeQuantX Backtest Engine

A high-performance, event-driven backtesting framework for quantitative research.
"""

from backtest_engine.data_provider import (
    DataProviderClient,
    get_historical_data,
    ConfigLoader,
    load_config,
    DataProviderConfig,
    ProviderConfig,
    ZerodhaConfig,
    DhanConfig,
    DataProviderError,
    ConfigurationError,
    AuthError,
    RateLimitError,
    DataError,
    ProviderError,
    CacheProtocol,
    DataProviderProtocol,
    HistoricalDataRequest,
    HistoricalDataResponse,
    NormalizedInstrument,
    NormalizedOHLC,
    StorageProtocol,
    Exchange,
    Segment,
    Interval,
    InstrumentType,
)

__version__ = "0.1.0"
__author__ = "TradeQuantX"
__all__ = [
    # Client
    "DataProviderClient",
    "get_historical_data",
    # Config
    "ConfigLoader",
    "load_config",
    "DataProviderConfig",
    "ProviderConfig",
    "ZerodhaConfig",
    "DhanConfig",
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