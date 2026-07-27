"""
TradeQuantX Backtest Engine — Execution Loop Package

A minimal, deterministic, event-driven backtesting framework for quantitative research.
"""

from backtest_engine.config import load_backtest_config, load_engine_config
from backtest_engine.config.models import BacktestConfig, EngineConfig
from backtest_engine.engine.engine import BacktestEngine, run_backtest
from backtest_engine.engine.interfaces import (
    BacktestContext,
    BacktestResult,
    CandleCallback,
    CandleEvent,
    DataFeeder,
    Preprocessor,
)
from backtest_engine.engine.position import (
    Position,
    PositionSide,
    PositionRequest,
    TradeRecord,
    EquityPoint,
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
    # Position Management
    "Position",
    "PositionSide",
    "PositionRequest",
    "TradeRecord",
    "EquityPoint",
]

__version__ = "0.1.0"