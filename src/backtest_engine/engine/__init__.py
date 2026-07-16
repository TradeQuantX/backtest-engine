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
]

__version__ = "0.1.0"