"""
Default configurations for the data provider layer.
"""

from backtest_engine.data_provider.config.models import (
    DataProviderConfig,
    DhanConfig,
    ProviderConfig,
    ZerodhaConfig,
)


DEFAULT_CONFIG = DataProviderConfig()

DEFAULT_PROVIDERS = {
    "zerodha": ZerodhaConfig(
        name="zerodha",
        enabled=False,
        priority=10,
        api_key="",
        api_secret="",
        access_token="",
        redirect_url="http://localhost:8080/callback",
        totp_secret=None,
        token_file="~/.tradex/tokens/zerodha.json",
        rate_limit_per_second=3.0,
        rate_limit_per_minute=100,
        rate_limit_per_day=10000,
        connect_timeout=10.0,
        read_timeout=30.0,
    ),
    "dhan": DhanConfig(
        name="dhan",
        enabled=False,
        priority=20,
        api_key="",
        api_secret="",
        access_token="",
        client_id="",
        static_ip=None,
        token_file="~/.tradex/tokens/dhan.json",
        rate_limit_per_second=5.0,
        rate_limit_per_minute=250,
        rate_limit_per_day=7000,
        connect_timeout=10.0,
        read_timeout=30.0,
    ),
}


def get_default_config() -> DataProviderConfig:
    """Get default configuration."""
    return DEFAULT_CONFIG


def get_default_providers() -> dict[str, ProviderConfig]:
    """Get default provider configurations."""
    return DEFAULT_PROVIDERS.copy()