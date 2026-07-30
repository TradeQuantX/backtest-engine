"""
Core data models for the execution engine.

This module contains ALL dataclasses, enums, and type aliases used across the engine.
It has ZERO dependencies on implementation modules - only stdlib, shared.types, and data_provider interfaces.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional
from uuid import uuid4

import polars as pl

from backtest_engine.shared.types import (
    Exchange,
    Interval,
    Segment,
)
from backtest_engine.data_provider.interfaces.models import NormalizedOHLC


# =============================================================================
# Enums
# =============================================================================

from enum import Enum

class PositionSide(str, Enum):
    """Position side: LONG or SHORT."""
    LONG = "LONG"
    SHORT = "SHORT"


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

@dataclass(slots=True)
class BacktestContext:
    """
    Runtime context passed to every callback invocation.
    
    Includes progress tracking (total_bars known upfront from merged event list).
    Hot-path fields (current_bar_index, progress_pct, current_prices) are mutable
    to avoid allocation on every bar in the execution loop.
    """
    symbol: str
    exchange: Exchange
    segment: Segment
    base_interval: Interval
    timeframes: list[Interval]
    total_bars: int                  # KNOWN UPFRONT from merged event list
    current_bar_index: int = 0
    progress_pct: float = 0.0
    
    # Position management (added by engine at runtime)
    position_manager: "PositionManagerProtocol" = field(default=None, repr=False)
    trade_logger: "TradeLoggerProtocol" = field(default=None, repr=False)
    current_prices: dict[str, float] = field(default_factory=dict, repr=False)
    
    def update_progress(self, current_bar_index: int) -> None:
        """Update progress in-place (mutates for hot-path efficiency)."""
        self.current_bar_index = current_bar_index
        self.progress_pct = (current_bar_index + 1) / self.total_bars * 100 if self.total_bars > 0 else 0.0


# =============================================================================
# Result
# =============================================================================

@dataclass(frozen=True, slots=True)
class BacktestResult:
    """Result returned after a backtest run completes."""
    events_processed: int
    duration_seconds: float
    
    # Trade logging results
    trade_log_path: Optional[str] = None
    equity_curve_path: Optional[str] = None
    run_dir: Optional[str] = None
    summary_stats: Optional[dict] = None


# =============================================================================
# Position Management Models
# =============================================================================

@dataclass(frozen=True, slots=True)
class Position:
    """
    Active position state.
    
    Immutable - use PositionManager methods to create updated positions.
    """
    position_id: str = field(default_factory=lambda: str(uuid4()))
    symbol: str = ""
    side: PositionSide = PositionSide.LONG
    quantity: float = 0.0
    entry_price: float = 0.0
    entry_time: datetime = field(default_factory=datetime.now)
    entry_condition: str = ""
    
    # Exit parameters
    stop_loss: Optional[float] = None
    trailing_stop_pct: Optional[float] = None
    take_profit: Optional[float] = None
    custom_exit_fn: Optional[Callable[["Position", "BacktestContext"], bool]] = None
    
    # Trailing stop state (updated on favorable moves)
    highest_price: float = 0.0  # For LONG trailing stops
    lowest_price: float = 0.0   # For SHORT trailing stops
    
    # Current state
    unrealized_pnl: float = 0.0
    
    def __post_init__(self):
        # Initialize trailing stop reference prices
        if self.highest_price == 0.0:
            object.__setattr__(self, 'highest_price', self.entry_price)
        if self.lowest_price == 0.0:
            object.__setattr__(self, 'lowest_price', self.entry_price)
    
    def with_unrealized_pnl(self, pnl: float) -> "Position":
        """Return new Position with updated unrealized PnL."""
        return Position(
            position_id=self.position_id,
            symbol=self.symbol,
            side=self.side,
            quantity=self.quantity,
            entry_price=self.entry_price,
            entry_time=self.entry_time,
            entry_condition=self.entry_condition,
            stop_loss=self.stop_loss,
            trailing_stop_pct=self.trailing_stop_pct,
            take_profit=self.take_profit,
            custom_exit_fn=self.custom_exit_fn,
            highest_price=self.highest_price,
            lowest_price=self.lowest_price,
            unrealized_pnl=pnl,
        )
    
    def with_trailing_update(self, highest: float, lowest: float) -> "Position":
        """Return new Position with updated trailing stop reference prices."""
        return Position(
            position_id=self.position_id,
            symbol=self.symbol,
            side=self.side,
            quantity=self.quantity,
            entry_price=self.entry_price,
            entry_time=self.entry_time,
            entry_condition=self.entry_condition,
            stop_loss=self.stop_loss,
            trailing_stop_pct=self.trailing_stop_pct,
            take_profit=self.take_profit,
            custom_exit_fn=self.custom_exit_fn,
            highest_price=highest,
            lowest_price=lowest,
            unrealized_pnl=self.unrealized_pnl,
        )


@dataclass(frozen=True, slots=True)
class TradeRecord:
    """
    Completed trade record for logging.
    
    Matches user-specified CSV schema:
    Entry Time, Exit Time, Entry Price, Exit Price, Symbol, Base Symbol,
    Quantity, PositionStatus, Entry Condition, Exit Condition, PnL, Fees
    """
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    symbol: str
    base_symbol: str
    quantity: float
    position_status: str  # "LONG" for LONG, "SHORT" for SHORT
    entry_condition: str
    exit_condition: str
    pnl: float
    fees: float = 0.0
    
    def to_csv_row(self) -> list[str]:
        """Convert to CSV row matching the specified schema."""
        return [
            self.entry_time.isoformat(),
            self.exit_time.isoformat(),
            f"{self.entry_price:.4f}",
            f"{self.exit_price:.4f}",
            self.symbol,
            self.base_symbol,
            f"{self.quantity:.4f}",
            self.position_status,
            self.entry_condition,
            self.exit_condition,
            f"{self.pnl:.4f}",
            f"{self.fees:.4f}",
        ]
    
    @staticmethod
    def csv_header() -> list[str]:
        """CSV header matching user specification."""
        return [
            "Entry Time", "Exit Time", "Entry Price", "Exit Price",
            "Symbol", "Base Symbol", "Quantity", "PositionStatus",
            "Entry Condition", "Exit Condition", "PnL", "Fees"
        ]


@dataclass(frozen=True, slots=True)
class EquityPoint:
    """Single point on the equity curve."""
    timestamp: datetime
    equity: float
    unrealized_pnl: float
    realized_pnl: float
    cash: float
    
    def to_csv_row(self) -> list[str]:
        """Convert to CSV row."""
        return [
            self.timestamp.isoformat(),
            f"{self.equity:.4f}",
            f"{self.unrealized_pnl:.4f}",
            f"{self.realized_pnl:.4f}",
            f"{self.cash:.4f}",
        ]
    
    @staticmethod
    def csv_header() -> list[str]:
        """CSV header for equity curve."""
        return ["Timestamp", "Equity", "Unrealized PnL", "Realized PnL", "Cash"]


@dataclass(frozen=True, slots=True)
class PositionRequest:
    """
    Request to open a new position.
    
    Use this instead of passing 11 parameters to open_position().
    All fields are required except exit parameters.
    """
    symbol: str
    side: PositionSide
    quantity: float
    entry_price: float
    entry_time: datetime
    entry_condition: str
    stop_loss: Optional[float] = None
    trailing_stop_pct: Optional[float] = None
    take_profit: Optional[float] = None
    custom_exit_fn: Optional[Callable[["Position", "BacktestContext"], bool]] = None
    
    def __post_init__(self):
        if self.quantity <= 0:
            raise ValueError("Quantity must be positive")
        if self.entry_price <= 0:
            raise ValueError("Entry price must be positive")


# =============================================================================
# Forward references for protocols (resolved at runtime)
# =============================================================================

# These are imported by protocols.py for type hints
# The actual classes are defined above
Preprocessor = "Preprocessor"
PositionManagerProtocol = "PositionManagerProtocol"
TradeLoggerProtocol = "TradeLoggerProtocol"
TargetQuantity = dict[str, float]
SignalCallback = Callable[["CandleEvent", "BacktestContext"], TargetQuantity]