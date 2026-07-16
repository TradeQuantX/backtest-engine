"""
Default implementations and factories for the backtest engine.

Provides concrete implementations for protocols to avoid hard dependencies
in the core engine module.
"""

from pathlib import Path
from backtest_engine.engine.feeder import ParquetDataFeeder
from backtest_engine.engine.interfaces import DataFeeder, Preprocessor
from backtest_engine.engine.position_manager import PositionManager
from backtest_engine.engine.trade_logger import TradeLogger
import polars as pl


class NoOpPreprocessor:
    """Default no-op preprocessor that returns the DataFrame unchanged."""
    
    def process(self, base_df: pl.DataFrame) -> pl.DataFrame:
        return base_df


# Singleton instance for default preprocessor
_DEFAULT_PREPROCESSOR = NoOpPreprocessor()


def create_default_feeder() -> DataFeeder:
    """
    Factory function to create the default data feeder.
    
    Returns:
        ParquetDataFeeder instance wrapping DataProviderClient
    """
    return ParquetDataFeeder()


def get_default_preprocessor() -> Preprocessor:
    """Get the default no-op preprocessor."""
    return _DEFAULT_PREPROCESSOR


def create_default_position_manager(
    initial_cash: float = 1_000_000.0,
    commission_per_share: float = 0.0,
    commission_pct: float = 0.0,
    slippage_pct: float = 0.0,
) -> PositionManager:
    """
    Factory function to create the default position manager.
    
    Args:
        initial_cash: Starting cash balance
        commission_per_share: Fixed commission per share/contract
        commission_pct: Percentage commission (e.g., 0.001 = 0.1%)
        slippage_pct: Slippage percentage per trade
        
    Returns:
        PositionManager instance with default settings
    """
    return PositionManager(
        initial_cash=initial_cash,
        commission_per_share=commission_per_share,
        commission_pct=commission_pct,
        slippage_pct=slippage_pct,
    )


def create_default_trade_logger(
    base_dir: Path | str,
    strategy_name: str,
    initial_cash: float = 1_000_000.0,
) -> TradeLogger:
    """
    Factory function to create the default trade logger.
    
    Args:
        base_dir: Base directory for backtest runs
        strategy_name: Strategy name for directory naming
        initial_cash: Initial cash for equity calculation
        
    Returns:
        TradeLogger instance
    """
    return TradeLogger(
        base_dir=Path(base_dir),
        strategy_name=strategy_name,
        initial_cash=initial_cash,
    )