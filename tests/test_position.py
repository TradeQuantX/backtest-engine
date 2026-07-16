"""
Tests for Position data models.
"""

import pytest
from datetime import datetime
from uuid import uuid4

from backtest_engine.data_provider.interfaces.models import NormalizedOHLC
from backtest_engine.data_provider.utils import IST
from backtest_engine.engine.position import Position, PositionSide, TradeRecord, EquityPoint


class TestPosition:
    """Test Position dataclass."""
    
    def test_position_creation(self):
        """Test basic position creation."""
        pos = Position(
            position_id="test-123",
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="SMA_CROSS",
        )
        
        assert pos.position_id == "test-123"
        assert pos.symbol == "RELIANCE"
        assert pos.side == PositionSide.LONG
        assert pos.quantity == 100
        assert pos.entry_price == 2500.0
        assert pos.entry_condition == "SMA_CROSS"
        assert pos.highest_price == 2500.0  # Initialized to entry_price
        assert pos.lowest_price == 2500.0   # Initialized to entry_price
        assert pos.unrealized_pnl == 0.0
    
    def test_position_with_exit_params(self):
        """Test position with stop loss, trailing stop, take profit."""
        pos = Position(
            position_id="test-123",
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
    
    def test_position_with_custom_exit(self):
        """Test position with custom exit function."""
        def custom_exit(position, context):
            return position.unrealized_pnl < -1000
        
        pos = Position(
            position_id="test-123",
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="SMA_CROSS",
            custom_exit_fn=custom_exit,
        )
        
        assert pos.custom_exit_fn is not None
        assert pos.custom_exit_fn(pos, None) is False  # PnL is 0
    
    def test_position_immutability(self):
        """Test that Position is immutable (frozen dataclass)."""
        pos = Position(
            position_id="test-123",
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="SMA_CROSS",
        )
        
        with pytest.raises(Exception):  # Frozen dataclass raises FrozenInstanceError
            pos.quantity = 200
    
    def test_with_unrealized_pnl(self):
        """Test creating new position with updated unrealized PnL."""
        pos = Position(
            position_id="test-123",
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="SMA_CROSS",
        )
        
        new_pos = pos.with_unrealized_pnl(500.0)
        
        assert new_pos.unrealized_pnl == 500.0
        assert new_pos.position_id == pos.position_id
        assert new_pos.quantity == pos.quantity
        assert new_pos is not pos  # New instance
    
    def test_with_trailing_update(self):
        """Test creating new position with updated trailing prices."""
        pos = Position(
            position_id="test-123",
            symbol="RELIANCE",
            side=PositionSide.LONG,
            quantity=100,
            entry_price=2500.0,
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            entry_condition="SMA_CROSS",
            highest_price=2500.0,
            lowest_price=2500.0,
        )
        
        new_pos = pos.with_trailing_update(2550.0, 2490.0)
        
        assert new_pos.highest_price == 2550.0
        assert new_pos.lowest_price == 2490.0
        assert new_pos is not pos


class TestPositionSide:
    """Test PositionSide enum."""
    
    def test_long_value(self):
        assert PositionSide.LONG == "LONG"
    
    def test_short_value(self):
        assert PositionSide.SHORT == "SHORT"


class TestTradeRecord:
    """Test TradeRecord dataclass."""
    
    def test_trade_record_creation(self):
        """Test basic trade record creation."""
        trade = TradeRecord(
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            exit_time=datetime(2024, 1, 1, 10, 30, tzinfo=IST),
            entry_price=2500.0,
            exit_price=2550.0,
            symbol="RELIANCE",
            base_symbol="RELIANCE",
            quantity=100,
            position_status="BUY",
            entry_condition="SMA_CROSS",
            exit_condition="TAKE_PROFIT",
            pnl=5000.0,
            fees=10.0,
        )
        
        assert trade.pnl == 5000.0
        assert trade.fees == 10.0
        assert trade.position_status == "BUY"
    
    def test_to_csv_row(self):
        """Test CSV row conversion."""
        trade = TradeRecord(
            entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            exit_time=datetime(2024, 1, 1, 10, 30, tzinfo=IST),
            entry_price=2500.0,
            exit_price=2550.0,
            symbol="RELIANCE",
            base_symbol="RELIANCE",
            quantity=100,
            position_status="BUY",
            entry_condition="SMA_CROSS",
            exit_condition="TAKE_PROFIT",
            pnl=5000.0,
            fees=10.0,
        )
        
        row = trade.to_csv_row()
        
        assert len(row) == 12
        assert row[0] == "2024-01-01T09:15:00+05:30"
        assert row[1] == "2024-01-01T10:30:00+05:30"
        assert row[2] == "2500.0000"
        assert row[3] == "2550.0000"
        assert row[4] == "RELIANCE"
        assert row[5] == "RELIANCE"
        assert row[6] == "100.0000"
        assert row[7] == "BUY"
        assert row[8] == "SMA_CROSS"
        assert row[9] == "TAKE_PROFIT"
        assert row[10] == "5000.0000"
        assert row[11] == "10.0000"
    
    def test_csv_header(self):
        """Test CSV header matches user specification."""
        header = TradeRecord.csv_header()
        
        expected = [
            "Entry Time", "Exit Time", "Entry Price", "Exit Price",
            "Symbol", "Base Symbol", "Quantity", "PositionStatus",
            "Entry Condition", "Exit Condition", "PnL", "Fees"
        ]
        
        assert header == expected


class TestEquityPoint:
    """Test EquityPoint dataclass."""
    
    def test_equity_point_creation(self):
        """Test equity point creation."""
        point = EquityPoint(
            timestamp=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            equity=1005000.0,
            unrealized_pnl=5000.0,
            realized_pnl=0.0,
            cash=1000000.0,
        )
        
        assert point.equity == 1005000.0
        assert point.unrealized_pnl == 5000.0
        assert point.realized_pnl == 0.0
        assert point.cash == 1000000.0
    
    def test_to_csv_row(self):
        """Test CSV row conversion."""
        point = EquityPoint(
            timestamp=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            equity=1005000.0,
            unrealized_pnl=5000.0,
            realized_pnl=0.0,
            cash=1000000.0,
        )
        
        row = point.to_csv_row()
        
        assert len(row) == 5
        assert row[0] == "2024-01-01T09:15:00+05:30"
        assert row[1] == "1005000.0000"
        assert row[2] == "5000.0000"
        assert row[3] == "0.0000"
        assert row[4] == "1000000.0000"
    
    def test_csv_header(self):
        """Test CSV header."""
        header = EquityPoint.csv_header()
        
        assert header == ["Timestamp", "Equity", "Unrealized PnL", "Realized PnL", "Cash"]