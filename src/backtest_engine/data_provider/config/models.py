"""
Configuration models for the data provider layer.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    """Base provider configuration."""
    name: str
    enabled: bool = True
    priority: int = 0  # Higher = preferred
    api_key: str = ""
    api_secret: str = ""
    access_token: str = ""
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ZerodhaConfig(ProviderConfig):
    """Zerodha Kite Connect configuration."""
    name: str = "zerodha"
    redirect_url: str = "http://localhost:8080/callback"
    totp_secret: Optional[str] = None
    token_file: str = "~/.tradex/tokens/zerodha.json"
    rate_limit_per_second: float = 3.0
    rate_limit_per_minute: int = 100
    rate_limit_per_day: int = 10000
    base_url: str = "https://api.kite.trade"
    connect_timeout: float = 10.0
    read_timeout: float = 30.0


@dataclass(frozen=True, slots=True)
class DhanConfig(ProviderConfig):
    """DhanHQ configuration."""
    name: str = "dhan"
    client_id: str = ""
    access_token: str = ""
    static_ip: Optional[str] = None
    token_file: str = "~/.tradex/tokens/dhan.json"
    rate_limit_per_second: float = 5.0
    rate_limit_per_minute: int = 250
    rate_limit_per_day: int = 7000
    base_url: str = "https://api.dhan.co"
    sandbox: bool = False
    connect_timeout: float = 10.0
    read_timeout: float = 30.0


@dataclass(frozen=True, slots=True)
class DataProviderConfig:
    """Main data provider configuration."""
    # Global settings
    default_provider: str = "zerodha"
    data_dir: str = "~/.tradex/data"
    cache_dir: str = "~/.tradex/cache"
    log_level: str = "INFO"
    
    # Provider configurations
    providers: dict[str, ProviderConfig] = field(default_factory=dict)
    
    # Cache settings
    cache_enabled: bool = True
    cache_ttl_seconds: int = 3600  # 1 hour
    instrument_cache_ttl_seconds: int = 86400  # 24 hours
    
    # Storage settings
    storage_compression: str = "zstd"
    storage_row_group_size: int = 1_000_000
    storage_partition_by: str = "month"
    
    # Retry settings
    max_retries: int = 3
    retry_base_delay: float = 1.0
    retry_max_delay: float = 60.0
    retry_exponential_base: float = 2.0
    
    # Chunking settings
    chunk_size_days: dict[str, int] = field(default_factory=lambda: {
        "minute": 30,
        "3minute": 60,
        "5minute": 90,
        "15minute": 180,
        "30minute": 360,
        "60minute": 720,
        "day": 2000,
    })
    
    def get_provider_config(self, name: str) -> Optional[ProviderConfig]:
        """Get provider configuration by name."""
        return self.providers.get(name)
    
    def get_enabled_providers(self) -> list[ProviderConfig]:
        """Get list of enabled providers sorted by priority."""
        return sorted(
            [p for p in self.providers.values() if p.enabled],
            key=lambda p: p.priority,
            reverse=True,
        )
    
    def resolve_path(self, path: str) -> Path:
        """Resolve tilde and environment variables in path."""
        return Path(path).expanduser().resolve()