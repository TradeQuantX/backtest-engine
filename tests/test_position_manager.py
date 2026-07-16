"""
Tests for PositionManager class.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock

from backtest_engine.data_provider.interfaces.models import NormalizedOHLC
from backtest_engine.data_provider.utils import IST
from backtest_engine.engine.position import Position, PositionSide, TradeRecord
from backtest_engine.engine.position_manager import PositionManager, ClosedPosition
from backtest_engine.engine.interfaces import BacktestContext


class TestPositionManager:
    """Test PositionManager core functionality."""
    
    @pytest.fixture
    def position_manager(self):
        """Create a PositionManager instance."""
        return PositionManager(
            initial_cash=1_000_000.0,
            commission_per_share=0.0,
            commission_pct=0.0,
            slippage_pct=0.0,
        )
    
    @pytest.fixture
    def sample_context(self):
        """Create a sample BacktestContext."""
        return MagicMock(spec=BacktestContext)
    
    def test_open_position_long(self, position_manager):
        """Test opening a long position."""
        pos = position_manager.open_position(
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="SMA_CROSS",
        )
        
        assert pos.symbol == "RELIANCE"
        assert pos.side == PositionSide.LONG
        assert pos.quantity == 100
        assert pos.entry_price == 2500.0
        assert pos.entry_condition == "SMA_CROSS"
        assert pos.position_id is not None
        
        positions = position_manager.get_positions("RELIANCE")
        assert len(positions) == 1
        assert positions[0] == pos
    
    def test_open_position_short(self, position_manager):
        """Test opening a short position."""
        pos = position_manager.open_position(
            symbol="RELIANCE",
            side=PositionSide.SHORT,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="SMA_CROSS",
        )
        
        assert pos.side == PositionSide.SHORT
        assert pos.quantity == 100
    
    def test_open_position_with_exit_params(self, position_manager):
        """Test opening position with stop loss, trailing stop, take profit."""
        pos = position_manager.open_position(
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="SMA_CROSS",
            stop_loss=2450.0,
            trailing_stop_pct=0.02,
            take_profit=2600.0,
        )
        
        assert pos.stop_loss == 2450.0
        assert pos.trailing_stop_pct == 0.02
        assert pos.take_profit == 2600.0
    
    def test_open_position_invalid_quantity(self, position_manager):
        """Test opening position with invalid quantity raises error."""
        with pytest.raises(ValueError, match="Quantity must be positive"):
            position_manager.open_position(
                symbol="RELIANCE",
                side=PositionSide.LONG,
                quantity=0,
                entry_price=2500.0,
                entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
                entry_condition="TEST",
            )
    
    def test_hedging_multiple_positions_same_symbol(self, position_manager):
        """Test hedging: multiple independent positions per symbol."""
        # Open long
        long_pos = position_manager.open_position(
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="LONG_ENTRY",
        )
        
        # Open short (hedging)
        short_pos = position_manager.open_position(
            symbol="RELIANCE",
            side=PositionSide.SHORT,
            quantity=50,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 16, tzinfo=IST),
            entry_condition="SHORT_ENTRY",
        )
        
        positions = position_manager.get_positions("RELIANCE")
        assert len(positions) == 2
        assert positions[0].side == PositionSide.LONG
        assert positions[1].side == PositionSide.SHORT
    
    def test_close_position_long(self, position_manager):
        """Test closing a long position."""
        pos = position_manager.open_position(
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="TEST",
        )
        
        trade = position_manager.close_position(
            position=pos,
            exit_price=2550.0,
            exit_time=datetime(2024, 1, 1, 10, 30, tzinfo=IST),
            exit_reason="TAKE_PROFIT",
        )
        
        assert trade.pnl == 5000.0  # (2550 - 2500) * 100
        assert trade.exit_price == 2550.0
        assert trade.exit_condition == "TAKE_PROFIT"
        assert trade.position_status == "LONG"
        
        # Position should be removed
        assert len(position_manager.get_positions("RELIANCE")) == 0
    
    def test_close_position_short(self, position_manager):
        """Test closing a short position."""
        pos = position_manager.open_position(
            symbol="RELIANCE",
            side=PositionSide.SHORT,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="TEST",
        )
        
        trade = position_manager.close_position(
            position=pos,
            exit_price=2450.0,
            exit_time=datetime(2024, 1, 1, 10, 30, tzinfo=IST),
            exit_reason="TAKE_PROFIT",
        )
        
        assert trade.pnl == 5000.0  # (2500 - 2450) * 100
        assert trade.position_status == "SHORT"
    
    def test_close_position_with_fees(self, position_manager):
        """Test closing position with commission and slippage."""
        pm = PositionManager(
            initial_cash=1_000_000.0,
            commission_per_share=1.0,
            commission_pct=0.001,  # 0.1%
            slippage_pct=0.0005,   # 0.05%
        )
        
        pos = pm.open_position(
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="TEST",
        )
        
        trade = pm.close_position(
            position=pos,
            exit_price=2550.0,
            exit_time=datetime(2024, 1, 1, 10, 30, tzinfo=IST),
            exit_reason="TAKE_PROFIT",
        )
        
        # Fees = 100 * 1.0 + 255000 * 0.001 + 255000 * 0.0005
        # = 100 + 255 + 127.5 = 482.5
        expected_fees = 100 + 255 + 127.5
        assert abs(trade.fees - expected_fees) < 0.01
        assert trade.pnl == 5000.0 - expected_fees
    
    def test_update_marks(self, position_manager):
        """Test updating unrealized PnL for positions."""
        pos = position_manager.open_position(
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="TEST",
        )
        
        ohlc = NormalizedOHLC(
            symbol="RELIANCE",
            exchange="NSE",
            segment="EQ",
            interval="1minute",
            timestamp=datetime(2024, 1, 1, 9, 16, tzinfo=IST),
            open=2510.0,
            high=2520.0,
            low=2505.0,
            close=2515.0,
            volume=100000,
        )
        
        position_manager.update_marks("RELIANCE", ohlc)
        
        positions = position_manager.get_positions("RELIANCE")
        assert positions[0].unrealized_pnl == 1500.0  # (2515 - 2500) * 100
    
    def test_update_marks_short(self, position_manager):
        """Test updating unrealized PnL for short position."""
        pos = position_manager.open_position(
            symbol="RELIANCE",
            side=PositionSide.SHORT,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="TEST",
        )
        
        ohlc = NormalizedOHLC(
            symbol="RELIANCE",
            exchange="NSE",
            segment="EQ",
            interval="1minute",
            timestamp=datetime(2024, 1, 1, 9, 16, tzinfo=IST),
            open=2490.0,
            high=2495.0,
            low=2480.0,
            close=2485.0,
            volume=100000,
        )
        
        position_manager.update_marks("RELIANCE", ohlc)
        
        positions = position_manager.get_positions("RELIANCE")
        assert positions[0].unrealized_pnl == 1500.0  # (2500 - 2485) * 100
    
    def test_evaluate_exits_stop_loss(self, position_manager, sample_context):
        """Test exit evaluation triggers stop loss."""
        pos = position_manager.open_position(
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="TEST",
            stop_loss=2450.0,
        )
        
        ohlc = NormalizedOHLC(
            symbol="RELIANCE",
            exchange="NSE",
            segment="EQ",
            interval="1minute",
            timestamp=datetime(2024, 1, 1, 9, 16, tzinfo=IST),
            open=2490.0,
            high=2500.0,
            low=2440.0,  # Below stop loss
            close=2460.0,
            volume=100000,
        )
        
        closed = position_manager.evaluate_exits("RELIANCE", ohlc, sample_context)
        
        assert len(closed) == 1
        assert closed[0].exit_reason == "STOP_LOSS"
        assert closed[0].exit_price == 2450.0
    
    def test_evaluate_exits_trailing_stop(self, position_manager, sample_context):
        """Test exit evaluation triggers trailing stop."""
        pos = position_manager.open_position(
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="TEST",
            trailing_stop_pct=0.02,
        )
        
        # First bar: price goes up, updates highest
        ohlc1 = NormalizedOHLC(
            symbol="RELIANCE",
            exchange="NSE",
            segment="EQ",
            interval="1minute",
            timestamp=datetime(2024, 1, 1, 9, 16, tzinfo=IST),
            open=2520.0,
            high=2550.0,
            low=2510.0,
            close=2530.0,
            volume=100000,
        )
        position_manager.evaluate_exits("RELIANCE", ohlc1, sample_context)
        
        # Second bar: price drops below trailing stop
        ohlc2 = NormalizedOHLC(
            symbol="RELIANCE",
            exchange="NSE",
            segment="EQ",
            interval="1minute",
            timestamp=datetime(2024, 1, 1, 9, 17, tzinfo=IST),
            open=2520.0,
            high=2530.0,
            low=2495.0,  # Below trailing stop (2550 * 0.98 = 2499)
            close=2500.0,
            volume=100000,
        )
        closed = position_manager.evaluate_exits("RELIANCE", ohlc2, sample_context)
        
        assert len(closed) == 1
        assert closed[0].exit_reason == "TRAILING_STOP"
        assert closed[0].exit_price == 2499.0
    
    def test_evaluate_exits_take_profit(self, position_manager, sample_context):
        """Test exit evaluation triggers take profit."""
        pos = position_manager.open_position(
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="TEST",
            take_profit=2600.0,
        )
        
        ohlc = NormalizedOHLC(
            symbol="RELIANCE",
            exchange="NSE",
            segment="EQ",
            interval="1minute",
            timestamp=datetime(2024, 1, 1, 9, 16, tzinfo=IST),
            open=2550.0,
            high=2610.0,  # Above take profit
            low=2540.0,
            close=2580.0,
            volume=100000,
        )
        
        closed = position_manager.evaluate_exits("RELIANCE", ohlc, sample_context)
        
        assert len(closed) == 1
        assert closed[0].exit_reason == "TAKE_PROFIT"
        assert closed[0].exit_price == 2600.0
    
    def test_evaluate_exits_custom_exit(self, position_manager, sample_context):
        """Test exit evaluation triggers custom exit."""
        def custom_exit(position, context):
            return position.unrealized_pnl < -500
        
        pos = position_manager.open_position(
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="TEST",
            custom_exit_fn=custom_exit,
        )
        
        ohlc = NormalizedOHLC(
            symbol="RELIANCE",
            exchange="NSE",
            segment="EQ",
            interval="1minute",
            timestamp=datetime(2024, 1, 1, 9, 16, tzinfo=IST),
            open=2490.0,
            high=2500.0,
            low=2480.0,
            close=2440.0,  # PnL = -6000
            volume=100000,
        )
        
        # Update marks first to set unrealized PnL
        position_manager.update_marks("RELIANCE", ohlc)
        
        closed = position_manager.evaluate_exits("RELIANCE", ohlc, sample_context)
        
        assert len(closed) == 1
        assert closed[0].exit_reason == "CUSTOM"
        assert closed[0].exit_price == 2440.0  # Close price
    
    def test_evaluate_exits_priority_order(self, position_manager, sample_context):
        """Test exit priority: SL > Trailing > TP > Custom."""
        pos = position_manager.open_position(
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="TEST",
            stop_loss=2450.0,
            trailing_stop_pct=0.02,
            take_profit=2600.0,
        )
        
        # Update highest_price for trailing stop
        positions = position_manager.get_positions("RELIANCE")
        positions[0] = positions[0].with_trailing_update(2550.0, 2500.0)
        
        # All would trigger, but SL has highest priority
        ohlc = NormalizedOHLC(
            symbol="RELIANCE",
            exchange="NSE",
            segment="EQ",
            interval="1minute",
            timestamp=datetime(2024, 1, 1, 9, 16, tzinfo=IST),
            open=2490.0,
            high=2610.0,  # Above TP
            low=2440.0,   # Below SL and trailing
            close=2580.0,
            volume=100000,
        )
        
        closed = position_manager.evaluate_exits("RELIANCE", ohlc, sample_context)
        
        assert len(closed) == 1
        assert closed[0].exit_reason == "STOP_LOSS"  # Highest priority
    
    def test_adjust_positions_long(self, position_manager, sample_context):
        """Test adjusting positions to target long quantity."""
        # Open initial long
        position_manager.open_position(
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=50,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="INITIAL",
        )
        
        # Adjust to target 100 long
        new_positions = position_manager.adjust_positions(
            target_qty={"RELIANCE": 100},
            current_prices={"RELIANCE": 2510.0},
            timestamp=datetime(2024, 1, 1, 9, 16, tzinfo=IST),
            context=sample_context,
        )
        
        assert len(new_positions) == 1
        assert new_positions[0].quantity == 50  # Added 50
        assert new_positions[0].side == PositionSide.LONG
        
        positions = position_manager.get_positions("RELIANCE")
        assert len(positions) == 2
        total_qty = sum(p.quantity for p in positions)
        assert total_qty == 100
    
    def test_adjust_positions_short(self, position_manager, sample_context):
        """Test adjusting positions to target short quantity."""
        # Open initial long
        position_manager.open_position(
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="INITIAL",
        )
        
        # Adjust to target -50 short (net -50)
        new_positions = position_manager.adjust_positions(
            target_qty={"RELIANCE": -50},
            current_prices={"RELIANCE": 2490.0},
            timestamp=datetime(2024, 1, 1, 9, 16, tzinfo=IST),
            context=sample_context,
        )
        
        assert len(new_positions) == 1
        assert new_positions[0].quantity == 50  # Newly opened short position
        assert new_positions[0].side == PositionSide.SHORT
        
        positions = position_manager.get_positions("RELIANCE")
        assert len(positions) == 1
        assert positions[0].side == PositionSide.SHORT
        assert positions[0].quantity == 50
    
    def test_adjust_positions_flat(self, position_manager, sample_context):
        """Test adjusting positions to flat (0)."""
        position_manager.open_position(
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="INITIAL",
        )
        
        new_positions = position_manager.adjust_positions(
            target_qty={"RELIANCE": 0},
            current_prices={"RELIANCE": 2510.0},
            timestamp=datetime(2024, 1, 1, 9, 16, tzinfo=IST),
            context=sample_context,
        )
        
        assert len(new_positions) == 0
        assert len(position_manager.get_positions("RELIANCE")) == 0
        assert position_manager.trade_count == 1
    
    def test_get_positions_all_symbols(self, position_manager):
        """Test getting positions for all symbols."""
        position_manager.open_position(
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="TEST",
        )
        position_manager.open_position(
            symbol="TCS",
            side=PositionSide.SHORT,
            quantity=50,
            entry_price=3500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="TEST",
        )
        
        all_positions = position_manager.get_positions()
        assert len(all_positions) == 2
    
    def test_get_unrealized_pnl(self, position_manager):
        """Test getting unrealized PnL."""
        position_manager.open_position(
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="TEST",
        )
        
        ohlc = NormalizedOHLC(
            symbol="RELIANCE",
            exchange="NSE",
            segment="EQ",
            interval="1minute",
            timestamp=datetime(2024, 1, 1, 9, 16, tzinfo=IST),
            open=2510.0,
            high=2520.0,
            low=2505.0,
            close=2515.0,
            volume=100000,
        )
        position_manager.update_marks("RELIANCE", ohlc)
        
        unrealized = position_manager.get_unrealized_pnl("RELIANCE")
        assert unrealized == 1500.0
    
    def test_get_realized_pnl(self, position_manager):
        """Test getting realized PnL."""
        pos = position_manager.open_position(
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="TEST",
        )
        
        position_manager.close_position(
            position=pos,
            exit_price=2550.0,
            exit_time=datetime(2024, 1, 1, 10, 30, tzinfo=IST),
            exit_reason="TAKE_PROFIT",
        )
        
        realized = position_manager.get_realized_pnl("RELIANCE")
        assert realized == 5000.0
    
    def test_get_equity(self, position_manager):
        """Test getting total equity."""
        equity = position_manager.get_equity()
        assert equity == 1_000_000.0  # Initial cash
        
        position_manager.open_position(
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="TEST",
        )
        
        ohlc = NormalizedOHLC(
            symbol="RELIANCE",
            exchange="NSE",
            segment="EQ",
            interval="1minute",
            timestamp=datetime(2024, 1, 1, 9, 16, tzinfo=IST),
            open=2510.0,
            high=2520.0,
            low=2505.0,
            close=2515.0,
            volume=100000,
        )
        position_manager.update_marks("RELIANCE", ohlc)
        
        equity = position_manager.get_equity()
        assert equity == 1_001_500.0  # Cash + unrealized
    
    def test_record_equity_point(self, position_manager):
        """Test recording equity curve point."""
        position_manager.record_equity_point(
            timestamp=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            equity=1_000_000.0,
            unrealized=0.0,
            realized=0.0,
            cash=1_000_000.0,
        )
        
        curve = position_manager.get_equity_curve()
        assert len(curve) == 1
        assert curve[0][1] == 1_000_000.0  # equity
    
    def test_properties(self, position_manager):
        """Test PositionManager properties."""
        assert position_manager.initial_cash == 1_000_000.0
        assert position_manager.cash == 1_000_000.0
        assert position_manager.realized_pnl == 0.0
        assert position_manager.trade_count == 0
        assert position_manager.active_position_count == 0
        
        position_manager.open_position(
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="TEST",
        )
        
        assert position_manager.active_position_count == 1