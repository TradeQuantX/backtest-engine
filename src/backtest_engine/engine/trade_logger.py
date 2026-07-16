"""
Trade logging system for backtest results.

Creates uniquely named run directories and writes structured CSV logs.
"""

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from backtest_engine.engine.position import TradeRecord


class TradeLogger:
    """
    Handles trade logging to uniquely named run directories.
    
    Directory naming: {strategy_name}_{run_number:04d}/
    Files: trade_log.csv, equity_curve.csv, summary.json
    """
    
    TRADE_LOG_HEADERS = [
        "Entry Time", "Exit Time", "Entry Price", "Exit Price",
        "Symbol", "Base Symbol", "Quantity", "PositionStatus",
        "Entry Condition", "Exit Condition", "PnL", "Fees"
    ]
    
    EQUITY_CURVE_HEADERS = [
        "Timestamp", "Equity", "Unrealized PnL", "Realized PnL", "Cash"
    ]
    
    def __init__(
        self,
        base_dir: Path,
        strategy_name: str,
        initial_cash: float = 100000.0,
    ):
        """
        Initialize the trade logger.
        
        Args:
            base_dir: Base directory for all backtest runs
            strategy_name: Strategy name for directory naming
            initial_cash: Initial cash for equity calculation
        """
        self._base_dir = Path(base_dir)
        self._strategy_name = strategy_name
        self._initial_cash = initial_cash
        
        # Create unique run directory
        self._run_dir = self._create_run_dir()
        self._trade_log_path = self._run_dir / "trade_log.csv"
        self._equity_path = self._run_dir / "equity_curve.csv"
        self._summary_path = self._run_dir / "summary.json"
        
        # Initialize CSV files with headers
        self._init_csv_files()
        
        # Track summary stats
        self._trade_count = 0
        self._winning_trades = 0
        self._losing_trades = 0
        self._total_pnl = 0.0
        self._total_fees = 0.0
        self._max_drawdown = 0.0
        self._peak_equity = initial_cash
    
    def _create_run_dir(self) -> Path:
        """Create unique run directory with timestamp + UUID to avoid race conditions."""
        self._base_dir.mkdir(parents=True, exist_ok=True)
        
        # Use timestamp + short UUID for uniqueness (no race condition)
        from datetime import datetime
        import uuid
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        run_dir = self._base_dir / f"{self._strategy_name}_{timestamp}_{unique_id}"
        run_dir.mkdir(parents=True, exist_ok=False)
        
        return run_dir
    
    def _init_csv_files(self) -> None:
        """Initialize CSV files with headers."""
        with open(self._trade_log_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(self.TRADE_LOG_HEADERS)
        
        with open(self._equity_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(self.EQUITY_CURVE_HEADERS)
    
    def log_trade(self, trade: TradeRecord) -> None:
        """
        Log a completed trade to CSV.
        
        Args:
            trade: TradeRecord to log
        """
        with open(self._trade_log_path, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                trade.entry_time.isoformat(),
                trade.exit_time.isoformat(),
                f"{trade.entry_price:.4f}",
                f"{trade.exit_price:.4f}",
                trade.symbol,
                trade.base_symbol,
                f"{trade.quantity:.4f}",
                trade.position_status,
                trade.entry_condition,
                trade.exit_condition,
                f"{trade.pnl:.2f}",
                f"{trade.fees:.2f}",
            ])
        
        # Update summary stats
        self._trade_count += 1
        self._total_pnl += trade.pnl
        self._total_fees += trade.fees
        if trade.pnl > 0:
            self._winning_trades += 1
        elif trade.pnl < 0:
            self._losing_trades += 1
    
    def log_equity(
        self,
        timestamp: datetime,
        equity: float,
        unrealized_pnl: float,
        realized_pnl: float,
        cash: float,
    ) -> None:
        """
        Log an equity curve point.
        
        Args:
            timestamp: Current timestamp
            equity: Total equity (cash + unrealized)
            unrealized_pnl: Current unrealized PnL
            realized_pnl: Cumulative realized PnL
            cash: Current cash balance
        """
        with open(self._equity_path, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                timestamp.isoformat(),
                f"{equity:.2f}",
                f"{unrealized_pnl:.2f}",
                f"{realized_pnl:.2f}",
                f"{cash:.2f}",
            ])
        
        # Update drawdown tracking
        if equity > self._peak_equity:
            self._peak_equity = equity
        drawdown = (self._peak_equity - equity) / self._peak_equity * 100
        if drawdown > self._max_drawdown:
            self._max_drawdown = drawdown
    
    def finalize(self, position_manager) -> dict:
        """
        Finalize logging and write summary.
        
        Args:
            position_manager: PositionManager for final stats
            
        Returns:
            Summary statistics dictionary
        """
        # Get trades from position manager (source of truth)
        trades = position_manager.get_trade_log()
        
        # Calculate final metrics from actual trades
        self._trade_count = len(trades)
        self._winning_trades = sum(1 for t in trades if t.pnl > 0)
        self._losing_trades = sum(1 for t in trades if t.pnl < 0)
        self._total_pnl = sum(t.pnl for t in trades)
        self._total_fees = sum(t.fees for t in trades)
        
        win_rate = (
            self._winning_trades / self._trade_count * 100 
            if self._trade_count > 0 else 0.0
        )
        
        avg_win = 0.0
        avg_loss = 0.0
        if self._winning_trades > 0:
            wins = [t.pnl for t in trades if t.pnl > 0]
            avg_win = sum(wins) / len(wins)
        if self._losing_trades > 0:
            losses = [t.pnl for t in trades if t.pnl < 0]
            avg_loss = sum(losses) / len(losses)
        
        profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
        
        final_equity = position_manager.equity
        total_return = (final_equity - self._initial_cash) / self._initial_cash * 100
        
        summary = {
            "strategy_name": self._strategy_name,
            "run_directory": str(self._run_dir),
            "initial_cash": self._initial_cash,
            "final_equity": final_equity,
            "total_return_pct": total_return,
            "total_trades": self._trade_count,
            "winning_trades": self._winning_trades,
            "losing_trades": self._losing_trades,
            "win_rate_pct": win_rate,
            "total_pnl": self._total_pnl,
            "total_fees": self._total_fees,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "max_drawdown_pct": self._max_drawdown,
            "timestamp": datetime.now().isoformat(),
        }
        
        with open(self._summary_path, "w") as f:
            json.dump(summary, f, indent=2)
        
        return summary
    
    @property
    def run_dir(self) -> Path:
        """Get the run directory path."""
        return self._run_dir
    
    @property
    def trade_log_path(self) -> Path:
        """Get the trade log CSV path."""
        return self._trade_log_path
    
    @property
    def equity_path(self) -> Path:
        """Get the equity curve CSV path."""
        return self._equity_path
    
    @property
    def summary_path(self) -> Path:
        """Get the summary JSON path."""
        return self._summary_path
    
    @staticmethod
    def create_run_dir(base_dir: Path, strategy_name: str) -> Path:
        """
        Static method to create a run directory.
        
        Args:
            base_dir: Base directory
            strategy_name: Strategy name
            
        Returns:
            Created run directory path
        """
        base_dir = Path(base_dir)
        base_dir.mkdir(parents=True, exist_ok=True)
        
        # Use timestamp + short UUID for uniqueness (no race condition)
        from datetime import datetime
        import uuid
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        run_dir = base_dir / f"{strategy_name}_{timestamp}_{unique_id}"
        run_dir.mkdir(parents=True, exist_ok=False)
        
        return run_dir