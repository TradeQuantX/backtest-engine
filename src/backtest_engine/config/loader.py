"""High-level config loading."""

from typing import Optional
from .config import settings
from .models import DataProviderConfig, BacktestConfig, EngineConfig, ProviderConfig, ZerodhaConfig, DhanConfig, BaseProviderConfig


def load_data_provider_config() -> DataProviderConfig:
    """Load data provider configuration from YAML files."""
    raw = settings.get("DATA_PROVIDER", {})
    providers_raw = raw.pop("providers", {})
    providers = {}
    
    for name, data in providers_raw.items():
        if not data.get("enabled", True):
            continue
        provider_type = data.get("type", name)
        # Remove 'type' field before passing to constructor
        data_copy = {k: v for k, v in data.items() if k != "type"}
        if provider_type == "zerodha":
            providers[name] = ZerodhaConfig(**data_copy)
        elif provider_type == "dhan":
            providers[name] = DhanConfig(**data_copy)
        else:
            providers[name] = BaseProviderConfig(**data_copy)
    
    raw["providers"] = providers
    return DataProviderConfig(**raw)


def load_backtest_config() -> BacktestConfig:
    """Load backtest configuration from YAML files."""
    return BacktestConfig(**settings.get("BACKTEST", {}))


def load_engine_config() -> EngineConfig:
    """Load complete engine configuration from YAML files."""
    backtest_config = load_backtest_config()
    engine_raw = settings.get("ENGINE", {})
    engine_raw["backtest"] = backtest_config
    return EngineConfig(**engine_raw)