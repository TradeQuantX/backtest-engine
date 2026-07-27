"""
TradeQuantX Backtest Engine

A high-performance, event-driven backtesting framework for quantitative research.
"""

from backtest_engine.config import (
    load_data_provider_config,
    load_backtest_config,
    load_engine_config,
    DataProviderConfig,
    BacktestConfig,
    EngineConfig,
    BaseProviderConfig,
    ZerodhaConfig,
    DhanConfig,
    PositionManagerConfig,
    TradeLoggerConfig,
    DataFeederConfig,
)
from backtest_engine.data_provider import (
    DataProviderClient,
    get_historical_data,
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
)
from backtest_engine.shared.types import (
    Exchange,
    Segment,
    Interval,
    InstrumentType,
)

__version__ = "0.1.0"
__author__ = "TradeQuantX"
__all__ = [
    # Config
    "load_data_provider_config",
    "load_backtest_config",
    "load_engine_config",
    "DataProviderConfig",
    "BacktestConfig",
    "EngineConfig",
    "BaseProviderConfig",
    "ZerodhaConfig",
    "DhanConfig",
    "PositionManagerConfig",
    "TradeLoggerConfig",
    "DataFeederConfig",
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