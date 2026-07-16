"""
Position Manager - Core position management for the backtest engine.

Supports hedging mode (multiple independent positions per symbol),
continuous exit evaluation on every base-timeframe tick,
and query-based researcher API.

Exit Evaluation Priority (enforced in evaluate_exits):
1. Stop Loss (highest priority - capital protection)
2. Trailing Stop (protects profits)
3. Take Profit (locks in gains)
4. Custom Exit (lowest priority - researcher-defined logic)

This priority ensures protective exits always trigger before profit-taking
exits, preventing scenarios where both SL and TP are hit in the same bar
but the wrong one executes.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Callable

from backtest_engine.data_provider.interfaces.models import NormalizedOHLC
from backtest_engine.engine.interfaces import BacktestContext
from backtest_engine.engine.position import Position, PositionSide, TradeRecord, PositionRequest
from backtest_engine.engine.exits import evaluate_exits


@dataclass
class ClosedPosition:
    """Result of a position being closed."""
    position: Position
    exit_price: float
    exit_time: datetime
    exit_reason: str
    pnl: float
    trade_record: TradeRecord


class PositionManager:
    """
    Manages positions for backtesting.
    
    Features:
    - Hedging mode: multiple independent positions per symbol (LONG + SHORT simultaneously)
    - Exit evaluation on every base-timeframe tick (SL, TS, TP, Custom)
    - Priority-based exit resolution: SL > TS > TP > Custom
    - Query API for researchers: get_positions(), get_unrealized_pnl(), get_realized_pnl()
    - Trade logging integration
    
    Thread-safety: Not thread-safe. Single-threaded use in ExecutionLoop only.
    Nuitka: Pure Python, no dynamic dispatch in hot path.
    """
    
    def __init__(
        self,
        initial_cash: float = 1_000_000.0,
        commission_per_share: float = 0.0,
        commission_pct: float = 0.0,
        slippage_pct: float = 0.0,
    ):
        """
        Initialize PositionManager.
        
        Args:
            initial_cash: Starting cash balance
            commission_per_share: Fixed commission per share/contract
            commission_pct: Percentage commission (e.g., 0.001 = 0.1%)
            slippage_pct: Slippage percentage per trade
        """
        # Positions keyed by symbol -> list of Position (supports hedging)
        self._positions: dict[str, list[Position]] = {}
        
        # Completed trades
        self._trade_log: list[TradeRecord] = []
        
        # Equity curve points
        self._equity_curve: list[tuple[datetime, float, float, float, float]] = []  # (ts, equity, unrealized, realized, cash)
        
        # Account state
        self._cash = initial_cash
        self._initial_cash = initial_cash
        self._realized_pnl = 0.0
        self._unrealized_pnl = 0.0
        
        # Cost model
        self._commission_per_share = commission_per_share
        self._commission_pct = commission_pct
        self._slippage_pct = slippage_pct
    
    # =========================================================================
    # Position Management
    # =========================================================================
    
    def open_position(
        self,
        symbol: str,
        side: PositionSide,
        quantity: float,
        entry_price: float,
        entry_time: datetime,
        entry_condition: str,
        stop_loss: Optional[float] = None,
        trailing_stop_pct: Optional[float] = None,
        take_profit: Optional[float] = None,
        custom_exit_fn: Optional[Callable[[Position, BacktestContext], bool]] = None,
    ) -> Position:
        """
        Open a new position.
        
        Args:
            symbol: Trading symbol
            side: LONG or SHORT
            quantity: Position size (positive)
            entry_price: Entry price
            entry_time: Entry timestamp
            entry_condition: Description of entry signal
            stop_loss: Stop loss price (absolute)
            trailing_stop_pct: Trailing stop percentage (e.g., 0.02 = 2%)
            take_profit: Take profit price (absolute)
            custom_exit_fn: Custom exit callable(position, context) -> bool
            
        Returns:
            The created Position
        """
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        
        position = Position(
            position_id=str(uuid.uuid4())[:8],
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            entry_time=entry_time,
            entry_condition=entry_condition,
            stop_loss=stop_loss,
            trailing_stop_pct=trailing_stop_pct,
            take_profit=take_profit,
            custom_exit_fn=custom_exit_fn,
            highest_price=entry_price,
            lowest_price=entry_price,
            unrealized_pnl=0.0,
        )
        
        if symbol not in self._positions:
            self._positions[symbol] = []
        self._positions[symbol].append(position)
        
        return position
    
    def open_position_from_request(self, request: PositionRequest) -> Position:
        """
        Open a new position from a PositionRequest dataclass.
        
        Preferred API - use this instead of open_position() with 11 parameters.
        
        Args:
            request: PositionRequest with all position parameters
            
        Returns:
            The created Position
        """
        return self.open_position(
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            entry_price=request.entry_price,
            entry_time=request.entry_time,
            entry_condition=request.entry_condition,
            stop_loss=request.stop_loss,
            trailing_stop_pct=request.trailing_stop_pct,
            take_profit=request.take_profit,
            custom_exit_fn=request.custom_exit_fn,
        )
    
    def close_position(
        self,
        position: Position,
        exit_price: float,
        exit_time: datetime,
        exit_reason: str,
    ) -> TradeRecord:
        """
        Close a position and record the trade.
        
        Args:
            position: Position to close
            exit_price: Exit price
            exit_time: Exit timestamp
            exit_reason: Reason for exit (STOP_LOSS, TRAILING_STOP, TAKE_PROFIT, CUSTOM)
            
        Returns:
            TradeRecord for logging
        """
        # Calculate PnL
        if position.side == PositionSide.LONG:
            pnl = (exit_price - position.entry_price) * position.quantity
        else:
            pnl = (position.entry_price - exit_price) * position.quantity
        
        # Calculate fees
        fees = self._calculate_fees(position.quantity, exit_price)
        net_pnl = pnl - fees
        
        # Update cash and realized PnL
        self._cash += position.quantity * exit_price - fees
        self._realized_pnl += net_pnl
        
        # Create trade record
        trade = TradeRecord(
            entry_time=position.entry_time,
            exit_time=exit_time,
            entry_price=position.entry_price,
            exit_price=exit_price,
            symbol=position.symbol,
            base_symbol=position.symbol,  # Could be different for futures
            quantity=position.quantity,
            position_status=position.side.value,  # "LONG" or "SHORT"
            entry_condition=position.entry_condition,
            exit_condition=exit_reason,
            pnl=net_pnl,
            fees=fees,
        )
        
        self._trade_log.append(trade)
        
        # Remove from active positions
        symbol_positions = self._positions.get(position.symbol, [])
        if position in symbol_positions:
            symbol_positions.remove(position)
            if not symbol_positions:
                del self._positions[position.symbol]
        
        return trade
    
    def _calculate_fees(self, quantity: float, price: float) -> float:
        """Calculate total fees for a trade."""
        notional = quantity * price
        fees = self._commission_per_share * quantity
        fees += notional * self._commission_pct
        fees += notional * self._slippage_pct
        return fees
    
    # =========================================================================
    # Mark-to-Market & Exit Evaluation (Hot Path)
    # =========================================================================
    
    def update_marks(self, symbol: str, ohlc: NormalizedOHLC) -> None:
        """
        Update unrealized PnL for all positions in a symbol.
        
        Called on every base-timeframe tick for the symbol.
        Maintains running _unrealized_pnl for O(1) equity access.
        """
        positions = self._positions.get(symbol, [])
        symbol_unrealized = 0.0
        for idx, position in enumerate(positions):
            if position.side == PositionSide.LONG:
                unrealized = (ohlc.close - position.entry_price) * position.quantity
            else:
                unrealized = (position.entry_price - ohlc.close) * position.quantity
            
            symbol_unrealized += unrealized
            # Update position with new unrealized PnL (immutable, so we replace)
            self._positions[symbol][idx] = position.with_unrealized_pnl(unrealized)
        
        # Update running total
        self._unrealized_pnl = sum(
            p.unrealized_pnl for positions in self._positions.values() for p in positions
        )
    
    def evaluate_exits(
        self, 
        symbol: str, 
        ohlc: NormalizedOHLC, 
        context: BacktestContext
    ) -> list[ClosedPosition]:
        """
        Evaluate all exit conditions for positions in a symbol.
        
        Priority: Stop Loss > Trailing Stop > Take Profit > Custom Exit
        
        Returns list of ClosedPosition for positions that should be closed.
        """
        positions = self._positions.get(symbol, [])
        closed = []
        
        # Iterate over copy since we may modify the list
        for position in list(positions):
            triggered, exit_price, exit_reason, new_highest, new_lowest = evaluate_exits(
                position, ohlc, context
            )
            
            if triggered:
                # Close position
                trade = self.close_position(position, exit_price, ohlc.timestamp, exit_reason)
                # Update running unrealized PnL (remove closed position's unrealized PnL)
                self._unrealized_pnl -= position.unrealized_pnl
                closed.append(ClosedPosition(
                    position=position,
                    exit_price=exit_price,
                    exit_time=ohlc.timestamp,
                    exit_reason=exit_reason,
                    pnl=trade.pnl,
                    trade_record=trade,
                ))
            else:
                # Update trailing stop reference prices if they changed
                if new_highest != position.highest_price or new_lowest != position.lowest_price:
                    # Find index using enumerate (avoid O(n) .index() call)
                    for idx, pos in enumerate(self._positions[symbol]):
                        if pos is position:
                            self._positions[symbol][idx] = position.with_trailing_update(new_highest, new_lowest)
                            break
        
        return closed
    
    # =========================================================================
    # Entry Signal Processing
    # =========================================================================
    
    def adjust_positions(
        self,
        target_qty: dict[str, float],
        current_prices: dict[str, float],
        timestamp: datetime,
        context: BacktestContext,
    ) -> list[Position]:
        """
        Adjust positions to match target quantities.
        
        Called after exit evaluation and researcher callbacks.
        
        Args:
            target_qty: {symbol: target_quantity} where positive=long, negative=short, 0=flat
            current_prices: {symbol: current_price} for entry pricing
            timestamp: Current timestamp
            context: Backtest context
            
        Returns:
            List of newly opened positions
        """
        new_positions = []
        
        for symbol, target in target_qty.items():
            current_positions = self._positions.get(symbol, [])
            
            # Calculate current net position
            current_net = sum(
                p.quantity if p.side == PositionSide.LONG else -p.quantity
                for p in current_positions
            )
            
            if target == current_net:
                continue  # Already at target
            
            price = current_prices.get(symbol)
            if price is None:
                continue  # No price available
            
            if target == 0:
                # Close all positions for this symbol
                for position in list(current_positions):
                    self.close_position(position, price, timestamp, "SIGNAL_EXIT")
            elif target > 0:
                # Target is long
                if current_net < target:
                    # Need to add long or reduce short
                    qty_to_add = target - current_net
                    if qty_to_add > 0:
                        pos = self.open_position(
                            symbol=symbol,
                            side=PositionSide.LONG,
                            quantity=qty_to_add,
                            entry_price=price,
                            entry_time=timestamp,
                            entry_condition="SIGNAL_ENTRY",
                        )
                        new_positions.append(pos)
            else:
                # Target is short
                if current_net > target:
                    # Need to add short or reduce long
                    # First close any long positions
                    for position in list(current_positions):
                        if position.side == PositionSide.LONG:
                            self.close_position(position, price, timestamp, "SIGNAL_EXIT")
                    
                    # Now current_net should be <= 0 (only shorts remain)
                    # Recalculate current_net after closing longs
                    current_positions = self._positions.get(symbol, [])
                    current_net = sum(
                        p.quantity if p.side == PositionSide.LONG else -p.quantity
                        for p in current_positions
                    )
                    
                    # Add short if needed
                    if current_net > target:
                        qty_to_add = current_net - target  # positive
                        if qty_to_add > 0:
                            pos = self.open_position(
                                symbol=symbol,
                                side=PositionSide.SHORT,
                                quantity=qty_to_add,
                                entry_price=price,
                                entry_time=timestamp,
                                entry_condition="SIGNAL_ENTRY",
                            )
                            new_positions.append(pos)
        
        return new_positions
    
    # =========================================================================
    # Query API (Researcher-Facing)
    # =========================================================================
    
    def get_positions(self, symbol: Optional[str] = None) -> list[Position]:
        """
        Get active positions.
        
        Args:
            symbol: If provided, filter by symbol. Otherwise return all.
            
        Returns:
            List of active Position objects (copies for safety)
        """
        if symbol:
            return list(self._positions.get(symbol, []))
        
        all_positions = []
        for positions in self._positions.values():
            all_positions.extend(positions)
        return all_positions
    
    def get_unrealized_pnl(self, symbol: Optional[str] = None) -> float:
        """
        Get total unrealized PnL.
        
        Args:
            symbol: If provided, filter by symbol.
            
        Returns:
            Total unrealized PnL
        """
        positions = self.get_positions(symbol)
        return sum(p.unrealized_pnl for p in positions)
    
    def get_realized_pnl(self, symbol: Optional[str] = None) -> float:
        """
        Get total realized PnL.
        
        Args:
            symbol: If provided, filter by symbol.
            
        Returns:
            Total realized PnL
        """
        if symbol:
            return sum(
                t.pnl for t in self._trade_log 
                if t.symbol == symbol
            )
        return self._realized_pnl
    
    def get_total_pnl(self, symbol: Optional[str] = None) -> float:
        """Get total PnL (realized + unrealized)."""
        return self.get_realized_pnl(symbol) + self.get_unrealized_pnl(symbol)
    
    def get_cash(self) -> float:
        """Get current cash balance."""
        return self._cash
    
    def get_equity(self) -> float:
        """Get total equity (cash + unrealized PnL)."""
        return self.equity
    
    def get_trade_log(self) -> list[TradeRecord]:
        """Get copy of trade log."""
        return list(self._trade_log)
    
    def get_equity_curve(self) -> list[tuple[datetime, float, float, float, float]]:
        """Get equity curve points."""
        return list(self._equity_curve)
    
    def record_equity_point(
        self, 
        timestamp: datetime, 
        equity: float, 
        unrealized: float, 
        realized: float, 
        cash: float
    ) -> None:
        """Record an equity curve point."""
        self._equity_curve.append((timestamp, equity, unrealized, realized, cash))
    
    # =========================================================================
    # Properties
    # =========================================================================
    
    @property
    def initial_cash(self) -> float:
        return self._initial_cash
    
    @property
    def cash(self) -> float:
        return self._cash
    
    @property
    def realized_pnl(self) -> float:
        return self._realized_pnl
    
    @property
    def trade_count(self) -> int:
        return len(self._trade_log)
    
    @property
    def equity(self) -> float:
        """Get total equity (cash + unrealized PnL). O(1) using running total."""
        return self._cash + self._unrealized_pnl
    
    @property
    def active_position_count(self) -> int:
        return sum(len(p) for p in self._positions.values())