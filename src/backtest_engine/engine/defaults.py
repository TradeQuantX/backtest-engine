"""
Default implementations and factories for the backtest engine.

Provides concrete implementations for protocols to avoid hard dependencies
in the core engine module.
"""

from backtest_engine.engine.feeder import ParquetDataFeeder
from backtest_engine.engine.interfaces import DataFeeder, Preprocessor
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