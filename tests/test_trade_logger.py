"""
Tests for TradeLogger class.
"""

import pytest
import csv
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

from backtest_engine.data_provider.utils import IST
from backtest_engine.engine.position import Position, PositionSide, TradeRecord
from backtest_engine.engine.position_manager import PositionManager
from backtest_engine.engine.trade_logger import TradeLogger


class TestTradeLogger:
    """Test TradeLogger functionality."""
    
    @pytest.fixture
    def temp_dir(self, tmp_path):
        """Create a temporary directory for test runs."""
        return tmp_path
    
    @pytest.fixture
    def trade_logger(self, temp_dir):
        """Create a TradeLogger instance."""
        return TradeLogger(
            base_dir=temp_dir,
            strategy_name="test_strategy",
            initial_cash=1_000_000.0,
        )
    
    @pytest.fixture
    def position_manager(self):
        """Create a PositionManager with some trades."""
        pm = PositionManager(initial_cash=1_000_000.0)
        
        # Add some completed trades
        trade1 = TradeRecord(
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
        trade2 = TradeRecord(
            entry_time=datetime(2024, 1, 1, 11, 0, tzinfo=IST),
            exit_time=datetime(2024, 1, 1, 12, 0, tzinfo=IST),
            entry_price=2550.0,
            exit_price=2500.0,
            symbol="RELIANCE",
            base_symbol="RELIANCE",
            quantity=100,
            position_status="SELL",
            entry_condition="SHORT_SIGNAL",
            exit_condition="STOP_LOSS",
            pnl=-5000.0,
            fees=10.0,
        )
        trade3 = TradeRecord(
            entry_time=datetime(2024, 1, 1, 13, 0, tzinfo=IST),
            exit_time=datetime(2024, 1, 1, 14, 0, tzinfo=IST),
            entry_price=2500.0,
            exit_price=2520.0,
            symbol="RELIANCE",
            base_symbol="RELIANCE",
            quantity=50,
            position_status="BUY",
            entry_condition="SMA_CROSS",
            exit_condition="TRAILING_STOP",
            pnl=1000.0,
            fees=5.0,
        )
        
        pm._trade_log = [trade1, trade2, trade3]
        pm._realized_pnl = 1000.0
        pm._cash = 1_001_000.0
        
        return pm
    
    def test_run_directory_creation(self, temp_dir):
        """Test unique run directory creation with new naming pattern."""
        logger1 = TradeLogger(
            base_dir=temp_dir,
            strategy_name="test_strategy",
            initial_cash=1_000_000.0,
        )
        
        logger2 = TradeLogger(
            base_dir=temp_dir,
            strategy_name="test_strategy",
            initial_cash=1_000_000.0,
        )
        
        logger3 = TradeLogger(
            base_dir=temp_dir,
            strategy_name="test_strategy",
            initial_cash=1_000_000.0,
        )
        
        # All should exist and be unique
        assert logger1.run_dir.exists()
        assert logger2.run_dir.exists()
        assert logger3.run_dir.exists()
        assert logger1.run_dir != logger2.run_dir
        assert logger2.run_dir != logger3.run_dir
        assert logger1.run_dir != logger3.run_dir
        
        # Names should follow new pattern: strategy_YYYYMMDD_HHMMSS_uuid
        for logger in [logger1, logger2, logger3]:
            parts = logger.run_dir.name.split("_")
            assert parts[0] == "test"
            assert parts[1] == "strategy"
            assert len(parts) == 5  # test_strategy_YYYYMMDD_HHMMSS_uuid
            assert len(parts[2]) == 8  # YYYYMMDD
            assert len(parts[3]) == 6  # HHMMSS
            assert len(parts[4]) == 8  # UUID prefix
    
    def test_csv_files_created_with_headers(self, trade_logger):
        """Test CSV files are created with correct headers."""
        # Check trade_log.csv
        assert trade_logger.trade_log_path.exists()
        with open(trade_logger.trade_log_path, 'r') as f:
            reader = csv.reader(f)
            header = next(reader)
            assert header == TradeRecord.csv_header()
        
        # Check equity_curve.csv
        assert trade_logger.equity_path.exists()
        with open(trade_logger.equity_path, 'r') as f:
            reader = csv.reader(f)
            header = next(reader)
            assert header == EquityPoint.csv_header()
    
    def test_log_trade(self, trade_logger):
        """Test logging a trade to CSV."""
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
        
        trade_logger.log_trade(trade)
        
        # Read back and verify
        with open(trade_logger.trade_log_path, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)
        
        assert len(rows) == 2  # Header + 1 trade
        assert rows[1][0] == "2024-01-01T09:15:00+05:30"
        assert rows[1][1] == "2024-01-01T10:30:00+05:30"
        assert rows[1][2] == "2500.0000"
        assert rows[1][3] == "2550.0000"
        assert rows[1][4] == "RELIANCE"
        assert rows[1][5] == "RELIANCE"
        assert rows[1][6] == "100.0000"
        assert rows[1][7] == "BUY"
        assert rows[1][8] == "SMA_CROSS"
        assert rows[1][9] == "TAKE_PROFIT"
        assert rows[1][10] == "5000.00"
        assert rows[1][11] == "10.00"
    
    def test_log_multiple_trades_append(self, trade_logger):
        """Test multiple trades are appended to CSV."""
        trades = [
            TradeRecord(
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
            ),
            TradeRecord(
                entry_time=datetime(2024, 1, 1, 11, 0, tzinfo=IST),
                exit_time=datetime(2024, 1, 1, 12, 0, tzinfo=IST),
                entry_price=2550.0,
                exit_price=2500.0,
                symbol="RELIANCE",
                base_symbol="RELIANCE",
                quantity=100,
                position_status="SELL",
                entry_condition="SHORT_SIGNAL",
                exit_condition="STOP_LOSS",
                pnl=-5000.0,
                fees=10.0,
            ),
        ]
        
        for trade in trades:
            trade_logger.log_trade(trade)
        
        with open(trade_logger.trade_log_path, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)
        
        assert len(rows) == 3  # Header + 2 trades
    
    def test_log_equity(self, trade_logger):
        """Test logging equity curve point."""
        trade_logger.log_equity(
            timestamp=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            equity=1_000_000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            cash=1_000_000.0,
        )
        
        with open(trade_logger.equity_path, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)
        
        assert len(rows) == 2  # Header + 1 point
        assert rows[1][0] == "2024-01-01T09:15:00+05:30"
        assert rows[1][1] == "1000000.00"
        assert rows[1][2] == "0.00"
        assert rows[1][3] == "0.00"
        assert rows[1][4] == "1000000.00"
    
    def test_finalize_creates_summary(self, trade_logger, position_manager):
        """Test finalize creates summary.json with correct stats."""
        summary = trade_logger.finalize(position_manager)
        
        assert trade_logger.summary_path.exists()
        
        # Verify summary contents
        assert summary["strategy_name"] == "test_strategy"
        assert summary["initial_cash"] == 1_000_000.0
        assert summary["final_equity"] == 1_001_000.0
        assert summary["total_return_pct"] == 0.1
        assert summary["total_trades"] == 3
        assert summary["winning_trades"] == 2
        assert summary["losing_trades"] == 1
        assert summary["win_rate_pct"] == pytest.approx(66.67, rel=0.01)
        assert summary["total_pnl"] == 1000.0
        assert summary["total_fees"] == 25.0
        assert summary["avg_win"] == pytest.approx(3000.0, rel=0.01)
        assert summary["avg_loss"] == pytest.approx(-5000.0, rel=0.01)
        assert summary["profit_factor"] == pytest.approx(0.6, rel=0.01)
        assert summary["max_drawdown_pct"] == 0.0  # No drawdown in this test
    
    def test_drawdown_tracking(self, trade_logger):
        """Test max drawdown tracking."""
        # Log equity points with drawdown
        trade_logger.log_equity(
            timestamp=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            equity=1_000_000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            cash=1_000_000.0,
        )
        
        trade_logger.log_equity(
            timestamp=datetime(2024, 1, 1, 10, 0, tzinfo=IST),
            equity=1_050_000.0,  # New peak
            unrealized_pnl=50_000.0,
            realized_pnl=0.0,
            cash=1_000_000.0,
        )
        
        trade_logger.log_equity(
            timestamp=datetime(2024, 1, 1, 11, 0, tzinfo=IST),
            equity=1_020_000.0,  # Drawdown from peak
            unrealized_pnl=20_000.0,
            realized_pnl=0.0,
            cash=1_000_000.0,
        )
        
        # Peak was 1,050,000, current is 1,020,000
        # Drawdown = (1,050,000 - 1,020,000) / 1,050,000 * 100 = 2.857%
        pm = MagicMock()
        pm.equity = 1_020_000.0
        pm.get_trade_log.return_value = []
        pm.realized_pnl = 0.0
        pm.cash = 1_000_000.0
        
        summary = trade_logger.finalize(pm)
        
        assert summary["max_drawdown_pct"] == pytest.approx(2.857, rel=0.01)
    
    def test_static_create_run_dir(self, temp_dir):
        """Test static create_run_dir method with new naming pattern."""
        run_dir = TradeLogger.create_run_dir(temp_dir, "my_strategy")
        
        assert run_dir.exists()
        parts = run_dir.name.split("_")
        assert parts[0] == "my"
        assert parts[1] == "strategy"
        assert len(parts) == 5
        assert len(parts[2]) == 8  # YYYYMMDD
        assert len(parts[3]) == 6  # HHMMSS
        assert len(parts[4]) == 8  # UUID prefix
        
        run_dir2 = TradeLogger.create_run_dir(temp_dir, "my_strategy")
        assert run_dir2.exists()
        assert run_dir2 != run_dir
    
    def test_properties(self, trade_logger):
        """Test TradeLogger properties."""
        parts = trade_logger.run_dir.name.split("_")
        assert parts[0] == "test"
        assert parts[1] == "strategy"
        assert len(parts) == 5
        assert trade_logger.trade_log_path.name == "trade_log.csv"
        assert trade_logger.equity_path.name == "equity_curve.csv"
        assert trade_logger.summary_path.name == "summary.json"
    
    def test_empty_trade_log_summary(self, trade_logger):
        """Test summary with no trades."""
        pm = MagicMock()
        pm.equity = 1_000_000.0
        pm.get_trade_log.return_value = []
        pm.realized_pnl = 0.0
        pm.cash = 1_000_000.0
        
        summary = trade_logger.finalize(pm)
        
        assert summary["total_trades"] == 0
        assert summary["winning_trades"] == 0
        assert summary["losing_trades"] == 0
        assert summary["win_rate_pct"] == 0.0
        assert summary["avg_win"] == 0.0
        assert summary["avg_loss"] == 0.0
        assert summary["profit_factor"] == float('inf')
    
    def test_only_losing_trades(self, trade_logger):
        """Test summary with only losing trades."""
        pm = MagicMock()
        pm.equity = 990_000.0
        pm.get_trade_log.return_value = [
            TradeRecord(
                entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
                exit_time=datetime(2024, 1, 1, 10, 30, tzinfo=IST),
                entry_price=2500.0,
                exit_price=2450.0,
                symbol="RELIANCE",
                base_symbol="RELIANCE",
                quantity=100,
                position_status="BUY",
                entry_condition="TEST",
                exit_condition="STOP_LOSS",
                pnl=-5000.0,
                fees=10.0,
            ),
        ]
        pm.realized_pnl = -5000.0
        pm.cash = 990_000.0
        
        summary = trade_logger.finalize(pm)
        
        assert summary["winning_trades"] == 0
        assert summary["losing_trades"] == 1
        assert summary["win_rate_pct"] == 0.0
        assert summary["avg_win"] == 0.0
        assert summary["avg_loss"] == -5000.0
        assert summary["profit_factor"] == 0.0  # No wins
    
    def test_only_winning_trades(self, trade_logger):
        """Test summary with only winning trades."""
        pm = MagicMock()
        pm.equity = 1_010_000.0
        pm.get_trade_log.return_value = [
            TradeRecord(
                entry_time=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
                exit_time=datetime(2024, 1, 1, 10, 30, tzinfo=IST),
                entry_price=2500.0,
                exit_price=2550.0,
                symbol="RELIANCE",
                base_symbol="RELIANCE",
                quantity=100,
                position_status="BUY",
                entry_condition="TEST",
                exit_condition="TAKE_PROFIT",
                pnl=5000.0,
                fees=10.0,
            ),
        ]
        pm.realized_pnl = 5000.0
        pm.cash = 1_010_000.0
        
        summary = trade_logger.finalize(pm)
        
        assert summary["winning_trades"] == 1
        assert summary["losing_trades"] == 0
        assert summary["win_rate_pct"] == 100.0
        assert summary["avg_win"] == 5000.0
        assert summary["avg_loss"] == 0.0
        assert summary["profit_factor"] == float('inf')


# Need to import EquityPoint for the test
from backtest_engine.engine.position import EquityPoint