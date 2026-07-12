"""
Providers package for data provider layer.
"""

from backtest_engine.data_provider.providers.base import BaseProvider
from backtest_engine.data_provider.providers.registry import ProviderRegistry, register_provider

# Import provider implementations to trigger registration
from backtest_engine.data_provider.providers.zerodha import ZerodhaProvider
from backtest_engine.data_provider.providers.dhan import DhanProvider

__all__ = [
    "BaseProvider",
    "ProviderRegistry",
    "register_provider",
    "ZerodhaProvider",
    "DhanProvider",
]