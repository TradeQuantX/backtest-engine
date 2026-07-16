"""
Position data models for the backtest engine.

Immutable, frozen dataclasses with slots for Nuitka compatibility and performance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Optional
from uuid import uuid4

from backtest_engine.data_provider.interfaces.models import NormalizedOHLC
from backtest_engine.engine.interfaces import BacktestContext


class PositionSide(str, Enum):
    """Position side: LONG or SHORT."""
    LONG = "LONG"
    SHORT = "SHORT"


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
    custom_exit_fn: Optional[Callable[[Position, BacktestContext], bool]] = None
    
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
    custom_exit_fn: Optional[Callable[[Position, BacktestContext], bool]] = None
    
    def __post_init__(self):
        if self.quantity <= 0:
            raise ValueError("Quantity must be positive")
        if self.entry_price <= 0:
            raise ValueError("Entry price must be positive")