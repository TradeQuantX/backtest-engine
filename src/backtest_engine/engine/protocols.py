"""
Protocol definitions for the backtest engine.

Provider-agnostic contracts that all engine components must adhere to.
This module has ZERO dependencies on implementation modules.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional, Protocol, runtime_checkable

import polars as pl

from backtest_engine.shared.types import (
    Exchange,
    Interval,
    Segment,
)
from backtest_engine.data_provider.interfaces.models import NormalizedOHLC


# =============================================================================
# Protocols (Provider-Agnostic Contracts)
# =============================================================================

@runtime_checkable
class DataFeeder(Protocol):
    """
    Provider-agnostic interface for fetching base-interval OHLC data.
    
    Implementations:
    - ParquetDataFeeder: wraps DataProviderClient (async, cached, chunked)
    - MongoDataFeeder: future direct MongoDB reads
    - TimescaleDataFeeder: future direct TimescaleDB reads
    """
    async def fetch_base_series(self, config: "BacktestConfig") -> list[NormalizedOHLC]: ...


@runtime_checkable
class Preprocessor(Protocol):
    """
    Optional preprocessing hook for feature/indicator computation.
    
    Runs on the base-interval Polars DataFrame BEFORE resampling.
    Use for vectorized indicators (SMA, EMA, RSI, etc.) on the base series.
    
    Default: no-op identity function (pass-through).
    """
    def process(self, base_df: pl.DataFrame) -> pl.DataFrame: ...


# =============================================================================
# Position Management Protocols
# =============================================================================

@runtime_checkable
class PositionManagerProtocol(Protocol):
    """
    Protocol for position management.
    
    Allows different implementations (backtest, paper, live) with same interface.
    """
    def get_positions(self, symbol: Optional[str] = None) -> list["Position"]: ...
    def get_unrealized_pnl(self, symbol: Optional[str] = None) -> float: ...
    def get_realized_pnl(self, symbol: Optional[str] = None) -> float: ...
    def get_equity(self) -> float: ...
    def get_trade_log(self) -> list["TradeRecord"]: ...
    def get_equity_curve(self) -> list["EquityPoint"]: ...


@runtime_checkable
class TradeLoggerProtocol(Protocol):
    """Protocol for trade logging."""
    def log_trade(self, trade: "TradeRecord") -> None: ...
    def log_equity(self, timestamp: datetime, equity: float, unrealized_pnl: float, realized_pnl: float, cash: float) -> None: ...
    def finalize(self, position_manager: "PositionManagerProtocol") -> dict: ...


# Type alias for researcher signal callback
# Returns dict of {symbol: target_quantity} where:
#   positive = long target, negative = short target, 0/absent = flat
type TargetQuantity = dict[str, float]

# Type alias for signal callback - returns target quantities per symbol
type SignalCallback = Callable[["CandleEvent", "BacktestContext"], TargetQuantity]


# Forward references for type hints (resolved at runtime via models.py)
# These are imported in models.py and re-exported from there
Position = "Position"
PositionSide = "PositionSide"
TradeRecord = "TradeRecord"
EquityPoint = "EquityPoint"
PositionRequest = "PositionRequest"
BacktestConfig = "BacktestConfig"
CandleEvent = "CandleEvent"
CandleCallback = "CandleCallback"
BacktestContext = "BacktestContext"
BacktestResult = "BacktestResult"