"""
Core interfaces, protocols, and data models for the execution engine.

This module defines the contracts that all engine components must adhere to.
Researchers interact only with BacktestConfig, CandleEvent, and CandleCallback.
"""

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Callable, Optional, Protocol, TYPE_CHECKING, runtime_checkable

import polars as pl

from backtest_engine.data_provider.interfaces.models import (
    Exchange,
    Interval,
    NormalizedOHLC,
    Segment,
)

if TYPE_CHECKING:
    from backtest_engine.engine.feeder import DataFeeder
    from backtest_engine.engine.ingestor import Preprocessor


# =============================================================================
# Configuration
# =============================================================================

@dataclass(frozen=True, slots=True)
class BacktestConfig:
    """
    Complete configuration for a backtest run.
    
    All parameters are immutable after construction. Use the constructor directly
    or create a new instance with modified fields via dataclasses.replace().
    """
    symbol: str
    exchange: Exchange
    segment: Segment
    base_interval: Interval          # e.g., Interval.MINUTE_1
    timeframes: list[Interval]       # e.g., [Interval.MINUTE_1, Interval.MINUTE_5, Interval.DAY]
    from_date: datetime              # IST-aware
    to_date: datetime                # IST-aware
    strict_validation: bool = True   # Raise on gaps/invalid OHLC
    preprocessor: "Preprocessor" = None  # Default set in __post_init__
    
    def __post_init__(self):
        if self.preprocessor is None:
            from backtest_engine.engine.defaults import get_default_preprocessor
            object.__setattr__(self, 'preprocessor', get_default_preprocessor())


# =============================================================================
# Events & Callbacks
# =============================================================================

@dataclass(frozen=True, slots=True)
class CandleEvent:
    """
    A single closed candle emitted to the researcher callback.
    
    The timestamp represents the CLOSE time (boundary) of the candle,
    ensuring no lookahead bias — the callback fires only after all
    constituent base bars are processed.
    """
    timestamp: datetime              # IST, candle CLOSE time (boundary)
    timeframe: Interval              # Which timeframe this candle belongs to
    ohlc: NormalizedOHLC             # The closed candle data
    context: Optional["BacktestContext"] = None  # Run metadata (symbol, progress, etc.)


# Type alias for the researcher callback - receives event and context separately
type CandleCallback = Callable[["CandleEvent", "BacktestContext"], None]


# =============================================================================
# Run Context
# =============================================================================

@dataclass(frozen=True, slots=True)
class BacktestContext:
    """
    Runtime context passed to every callback invocation.
    
    Includes progress tracking (total_bars known upfront from merged event list).
    """
    symbol: str
    exchange: Exchange
    segment: Segment
    base_interval: Interval
    timeframes: list[Interval]
    total_bars: int                  # KNOWN UPFRONT from merged event list
    current_bar_index: int
    progress_pct: float
    
    def with_progress(self, current_bar_index: int) -> "BacktestContext":
        """Return a new context with updated progress (1-based)."""
        return replace(
            self,
            current_bar_index=current_bar_index,
            progress_pct=(current_bar_index + 1) / self.total_bars * 100 if self.total_bars > 0 else 0.0,
        )


# =============================================================================
# Result
# =============================================================================

@dataclass(frozen=True, slots=True)
class BacktestResult:
    """Result returned after a backtest run completes."""
    events_processed: int
    duration_seconds: float


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
    async def fetch_base_series(self, config: BacktestConfig) -> list[NormalizedOHLC]: ...


@runtime_checkable
class Preprocessor(Protocol):
    """
    Optional preprocessing hook for feature/indicator computation.
    
    Runs on the base-interval Polars DataFrame BEFORE resampling.
    Use for vectorized indicators (SMA, EMA, RSI, etc.) on the base series.
    
    Default: no-op identity function (pass-through).
    """
    def process(self, base_df: pl.DataFrame) -> pl.DataFrame: ...