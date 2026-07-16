"""
Tests for exit condition evaluation functions.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock

from backtest_engine.data_provider.interfaces.models import NormalizedOHLC
from backtest_engine.data_provider.utils import IST
from backtest_engine.engine.position import Position, PositionSide
from backtest_engine.engine.exits import (
    check_stop_loss,
    check_take_profit,
    check_trailing_stop,
    check_custom_exit,
    evaluate_exits,
)
from backtest_engine.engine.interfaces import BacktestContext


class TestCheckStopLoss:
    """Test stop loss evaluation."""
    
    def test_long_stop_loss_triggered(self):
        """Test long stop loss triggers when low <= stop."""
        position = Position(
            position_id="test-1",
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
        
        triggered, exit_price = check_stop_loss(position, ohlc)
        
        assert triggered is True
        assert exit_price == 2450.0  # Stop price (not gapped below open)
    
    def test_long_stop_loss_not_triggered(self):
        """Test long stop loss not triggered when low > stop."""
        position = Position(
            position_id="test-1",
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
            low=2460.0,  # Above stop loss
            close=2480.0,
            volume=100000,
        )
        
        triggered, exit_price = check_stop_loss(position, ohlc)
        
        assert triggered is False
        assert exit_price == 0.0
    
    def test_short_stop_loss_triggered(self):
        """Test short stop loss triggers when high >= stop."""
        position = Position(
            position_id="test-1",
            symbol="RELIANCE",
            side=PositionSide.SHORT,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="TEST",
            stop_loss=2550.0,
        )
        
        ohlc = NormalizedOHLC(
            symbol="RELIANCE",
            exchange="NSE",
            segment="EQ",
            interval="1minute",
            timestamp=datetime(2024, 1, 1, 9, 16, tzinfo=IST),
            open=2510.0,
            high=2560.0,  # Above stop loss
            low=2500.0,
            close=2540.0,
            volume=100000,
        )
        
        triggered, exit_price = check_stop_loss(position, ohlc)
        
        assert triggered is True
        assert exit_price == 2550.0
    
    def test_long_stop_loss_gap_protection(self):
        """Test gap protection: stop gapped below open, exit at open."""
        position = Position(
            position_id="test-1",
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
            open=2440.0,  # Gapped below stop
            high=2460.0,
            low=2430.0,
            close=2450.0,
            volume=100000,
        )
        
        triggered, exit_price = check_stop_loss(position, ohlc)
        
        assert triggered is True
        assert exit_price == 2440.0  # Exit at open (gap protection)
    
    def test_no_stop_loss_returns_false(self):
        """Test position without stop loss returns False."""
        position = Position(
            position_id="test-1",
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="TEST",
            stop_loss=None,
        )
        
        ohlc = NormalizedOHLC(
            symbol="RELIANCE",
            exchange="NSE",
            segment="EQ",
            interval="1minute",
            timestamp=datetime(2024, 1, 1, 9, 16, tzinfo=IST),
            open=2490.0,
            high=2500.0,
            low=2440.0,
            close=2460.0,
            volume=100000,
        )
        
        triggered, exit_price = check_stop_loss(position, ohlc)
        
        assert triggered is False
        assert exit_price == 0.0


class TestCheckTakeProfit:
    """Test take profit evaluation."""
    
    def test_long_take_profit_triggered(self):
        """Test long take profit triggers when high >= tp."""
        position = Position(
            position_id="test-1",
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
        
        triggered, exit_price = check_take_profit(position, ohlc)
        
        assert triggered is True
        assert exit_price == 2600.0  # Take profit price
    
    def test_short_take_profit_triggered(self):
        """Test short take profit triggers when low <= tp."""
        position = Position(
            position_id="test-1",
            symbol="RELIANCE",
            side=PositionSide.SHORT,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="TEST",
            take_profit=2400.0,
        )
        
        ohlc = NormalizedOHLC(
            symbol="RELIANCE",
            exchange="NSE",
            segment="EQ",
            interval="1minute",
            timestamp=datetime(2024, 1, 1, 9, 16, tzinfo=IST),
            open=2450.0,
            high=2460.0,
            low=2390.0,  # Below take profit
            close=2420.0,
            volume=100000,
        )
        
        triggered, exit_price = check_take_profit(position, ohlc)
        
        assert triggered is True
        assert exit_price == 2400.0
    
    def test_take_profit_gap_protection(self):
        """Test gap protection for take profit."""
        position = Position(
            position_id="test-1",
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
            open=2610.0,  # Gapped above TP
            high=2620.0,
            low=2600.0,
            close=2615.0,
            volume=100000,
        )
        
        triggered, exit_price = check_take_profit(position, ohlc)
        
        assert triggered is True
        assert exit_price == 2610.0  # Exit at open (gap protection)


class TestCheckTrailingStop:
    """Test trailing stop evaluation."""
    
    def test_long_trailing_stop_updates_highest(self):
        """Test long trailing stop updates highest price."""
        position = Position(
            position_id="test-1",
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="TEST",
            trailing_stop_pct=0.02,  # 2%
            highest_price=2500.0,
        )
        
        ohlc = NormalizedOHLC(
            symbol="RELIANCE",
            exchange="NSE",
            segment="EQ",
            interval="1minute",
            timestamp=datetime(2024, 1, 1, 9, 16, tzinfo=IST),
            open=2520.0,
            high=2550.0,  # New high
            low=2510.0,
            close=2530.0,
            volume=100000,
        )
        
        triggered, exit_price, new_highest, new_lowest = check_trailing_stop(position, ohlc)
        
        assert triggered is False
        assert new_highest == 2550.0  # Updated to new high
        assert new_lowest == 2500.0
    
    def test_long_trailing_stop_triggered(self):
        """Test long trailing stop triggers when low <= trailing stop."""
        position = Position(
            position_id="test-1",
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="TEST",
            trailing_stop_pct=0.02,  # 2%
            highest_price=2550.0,  # Previous high
        )
        
        # Trailing stop = 2550 * 0.98 = 2499.0
        ohlc = NormalizedOHLC(
            symbol="RELIANCE",
            exchange="NSE",
            segment="EQ",
            interval="1minute",
            timestamp=datetime(2024, 1, 1, 9, 17, tzinfo=IST),
            open=2520.0,
            high=2530.0,
            low=2495.0,  # Below trailing stop (2499.0)
            close=2500.0,
            volume=100000,
        )
        
        triggered, exit_price, new_highest, new_lowest = check_trailing_stop(position, ohlc)
        
        assert triggered is True
        assert exit_price == 2499.0  # Trailing stop price
    
    def test_short_trailing_stop_updates_lowest(self):
        """Test short trailing stop updates lowest price."""
        position = Position(
            position_id="test-1",
            symbol="RELIANCE",
            side=PositionSide.SHORT,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="TEST",
            trailing_stop_pct=0.02,
            lowest_price=2500.0,
        )
        
        ohlc = NormalizedOHLC(
            symbol="RELIANCE",
            exchange="NSE",
            segment="EQ",
            interval="1minute",
            timestamp=datetime(2024, 1, 1, 9, 16, tzinfo=IST),
            open=2480.0,
            high=2490.0,
            low=2450.0,  # New low
            close=2470.0,
            volume=100000,
        )
        
        triggered, exit_price, new_highest, new_lowest = check_trailing_stop(position, ohlc)
        
        assert triggered is False
        assert new_lowest == 2450.0  # Updated to new low
        assert new_highest == 2500.0
    
    def test_short_trailing_stop_triggered(self):
        """Test short trailing stop triggers when high >= trailing stop."""
        position = Position(
            position_id="test-1",
            symbol="RELIANCE",
            side=PositionSide.SHORT,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="TEST",
            trailing_stop_pct=0.02,
            lowest_price=2450.0,  # Previous low
        )
        
        # Trailing stop = 2450 * 1.02 = 2499.0
        ohlc = NormalizedOHLC(
            symbol="RELIANCE",
            exchange="NSE",
            segment="EQ",
            interval="1minute",
            timestamp=datetime(2024, 1, 1, 9, 17, tzinfo=IST),
            open=2480.0,
            high=2505.0,  # Above trailing stop (2499.0)
            low=2470.0,
            close=2490.0,
            volume=100000,
        )
        
        triggered, exit_price, new_highest, new_lowest = check_trailing_stop(position, ohlc)
        
        assert triggered is True
        assert exit_price == 2499.0  # Trailing stop price
    
    def test_no_trailing_stop_returns_false(self):
        """Test position without trailing stop returns False."""
        position = Position(
            position_id="test-1",
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="TEST",
            trailing_stop_pct=None,
        )
        
        ohlc = NormalizedOHLC(
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
        
        triggered, exit_price, new_highest, new_lowest = check_trailing_stop(position, ohlc)
        
        assert triggered is False
        assert exit_price == 0.0
        assert new_highest == position.highest_price
        assert new_lowest == position.lowest_price


class TestCheckCustomExit:
    """Test custom exit evaluation."""
    
    def test_custom_exit_triggered(self):
        """Test custom exit function returning True."""
        def custom_exit(position, context):
            return position.unrealized_pnl < -500
        
        position = Position(
            position_id="test-1",
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="TEST",
            custom_exit_fn=custom_exit,
            unrealized_pnl=-600.0,
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
            close=2440.0,
            volume=100000,
        )
        
        context = MagicMock(spec=BacktestContext)
        
        triggered, exit_price = check_custom_exit(position, ohlc, context)
        
        assert triggered is True
        assert exit_price == 2440.0  # Close price
    
    def test_custom_exit_not_triggered(self):
        """Test custom exit function returning False."""
        def custom_exit(position, context):
            return position.unrealized_pnl < -500
        
        position = Position(
            position_id="test-1",
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="TEST",
            custom_exit_fn=custom_exit,
            unrealized_pnl=-100.0,
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
            close=2440.0,
            volume=100000,
        )
        
        context = MagicMock(spec=BacktestContext)
        
        triggered, exit_price = check_custom_exit(position, ohlc, context)
        
        assert triggered is False
        assert exit_price == 0.0
    
    def test_no_custom_exit_returns_false(self):
        """Test position without custom exit returns False."""
        position = Position(
            position_id="test-1",
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="TEST",
            custom_exit_fn=None,
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
            close=2440.0,
            volume=100000,
        )
        
        context = MagicMock(spec=BacktestContext)
        
        triggered, exit_price = check_custom_exit(position, ohlc, context)
        
        assert triggered is False
        assert exit_price == 0.0
    
    def test_custom_exit_exception_handled(self):
        """Test custom exit exception is caught and returns False."""
        def custom_exit(position, context):
            raise ValueError("Custom exit error")
        
        position = Position(
            position_id="test-1",
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
            close=2440.0,
            volume=100000,
        )
        
        context = MagicMock(spec=BacktestContext)
        
        triggered, exit_price = check_custom_exit(position, ohlc, context)
        
        assert triggered is False
        assert exit_price == 0.0


class TestEvaluateExits:
    """Test priority-based exit evaluation."""
    
    def test_stop_loss_priority_over_trailing(self):
        """Test stop loss triggers before trailing stop."""
        position = Position(
            position_id="test-1",
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="TEST",
            stop_loss=2450.0,
            trailing_stop_pct=0.02,
            highest_price=2550.0,
        )
        
        # Both SL and trailing would trigger, but SL has priority
        ohlc = NormalizedOHLC(
            symbol="RELIANCE",
            exchange="NSE",
            segment="EQ",
            interval="1minute",
            timestamp=datetime(2024, 1, 1, 9, 16, tzinfo=IST),
            open=2490.0,
            high=2500.0,
            low=2440.0,  # Below SL (2450) and trailing (2499)
            close=2460.0,
            volume=100000,
        )
        
        context = MagicMock(spec=BacktestContext)
        
        triggered, exit_price, exit_reason, new_highest, new_lowest = evaluate_exits(
            position, ohlc, context
        )
        
        assert triggered is True
        assert exit_price == 2450.0  # Stop loss price
        assert exit_reason == "STOP_LOSS"
    
    def test_trailing_stop_priority_over_take_profit(self):
        """Test trailing stop triggers before take profit."""
        position = Position(
            position_id="test-1",
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="TEST",
            trailing_stop_pct=0.02,
            take_profit=2600.0,
            highest_price=2550.0,
        )
        
        # Both trailing and TP would trigger, trailing has priority
        # Use high that doesn't exceed previous high (2550) so trailing stop doesn't update
        ohlc = NormalizedOHLC(
            symbol="RELIANCE",
            exchange="NSE",
            segment="EQ",
            interval="1minute",
            timestamp=datetime(2024, 1, 1, 9, 16, tzinfo=IST),
            open=2520.0,
            high=2540.0,  # Below previous high (2550), so trailing stop stays at 2499
            low=2495.0,   # Below trailing (2499)
            close=2580.0,
            volume=100000,
        )
        
        context = MagicMock(spec=BacktestContext)
        
        triggered, exit_price, exit_reason, new_highest, new_lowest = evaluate_exits(
            position, ohlc, context
        )
        
        assert triggered is True
        assert exit_price == 2499.0  # Trailing stop price (2550 * 0.98)
        assert exit_reason == "TRAILING_STOP"
    
    def test_take_profit_priority_over_custom(self):
        """Test take profit triggers before custom exit."""
        def custom_exit(position, context):
            return True  # Always trigger
        
        position = Position(
            position_id="test-1",
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="TEST",
            take_profit=2600.0,
            custom_exit_fn=custom_exit,
        )
        
        ohlc = NormalizedOHLC(
            symbol="RELIANCE",
            exchange="NSE",
            segment="EQ",
            interval="1minute",
            timestamp=datetime(2024, 1, 1, 9, 16, tzinfo=IST),
            open=2550.0,
            high=2610.0,  # Above TP
            low=2540.0,
            close=2580.0,
            volume=100000,
        )
        
        context = MagicMock(spec=BacktestContext)
        
        triggered, exit_price, exit_reason, new_highest, new_lowest = evaluate_exits(
            position, ohlc, context
        )
        
        assert triggered is True
        assert exit_price == 2600.0  # Take profit price
        assert exit_reason == "TAKE_PROFIT"
    
    def test_no_exit_returns_false(self):
        """Test no exit conditions triggered returns False."""
        position = Position(
            position_id="test-1",
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="TEST",
            stop_loss=2450.0,
            trailing_stop_pct=0.02,
            take_profit=2600.0,
            highest_price=2500.0,
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
        
        context = MagicMock(spec=BacktestContext)
        
        triggered, exit_price, exit_reason, new_highest, new_lowest = evaluate_exits(
            position, ohlc, context
        )
        
        assert triggered is False
        assert exit_price == 0.0
        assert exit_reason == ""
        assert new_highest == 2520.0  # Updated from high
        assert new_lowest == 2500.0