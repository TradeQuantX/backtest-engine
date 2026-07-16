"""
TradeQuantX Backtest Engine — Execution Loop Package

A minimal, deterministic, event-driven backtesting framework for quantitative research.
"""

from backtest_engine.engine.engine import BacktestEngine, run_backtest
from backtest_engine.engine.interfaces import (
    BacktestConfig,
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
    # Config
    "BacktestConfig",
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