"""
TradeQuantX Backtest Engine — Execution Loop Package

A minimal, deterministic, event-driven backtesting framework for quantitative research.
"""

from backtest_engine.config import load_backtest_config, load_engine_config
from backtest_engine.config.models import BacktestConfig, EngineConfig
from backtest_engine.engine.engine import BacktestEngine, run_backtest
from backtest_engine.engine.models import (
    BacktestContext,
    BacktestResult,
    CandleCallback,
    CandleEvent,
    Position,
    PositionSide,
    PositionRequest,
    TradeRecord,
    EquityPoint,
)
from backtest_engine.engine.protocols import (
    DataFeeder,
    Preprocessor,
    PositionManagerProtocol,
    TradeLoggerProtocol,
    TargetQuantity,
    SignalCallback,
)

__all__ = [
    # Engine
    "BacktestEngine",
    "run_backtest",
    # Config (new unified config)
    "load_backtest_config",
    "load_engine_config",
    "BacktestConfig",
    "EngineConfig",
    # Events & Callbacks
    "CandleEvent",
    "CandleCallback",
    # Context & Result
    "BacktestContext",
    "BacktestResult",
    # Protocols
    "DataFeeder",
    "Preprocessor",
    "PositionManagerProtocol",
    "TradeLoggerProtocol",
    # Position Management
    "Position",
    "PositionSide",
    "PositionRequest",
    "TradeRecord",
    "EquityPoint",
    # Type aliases
    "TargetQuantity",
    "SignalCallback",
]

__version__ = "0.1.0"