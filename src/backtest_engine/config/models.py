"""All runtime configuration models."""

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.types import SecretStr
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, Union, Optional, List
from backtest_engine.shared.types import Exchange, Segment, Interval, IST

# =============================================================================
# Base
# =============================================================================

class BaseConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", slots=True, validate_default=True)
    log_level: str = "INFO"
    data_dir: Path = Field(default=Path("~/.tradex/data").expanduser())
    cache_dir: Path = Field(default=Path("~/.tradex/cache").expanduser())

# =============================================================================
# Providers
# =============================================================================

class BaseProviderConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", slots=True, validate_default=True)
    name: str
    enabled: bool = True
    priority: int = 0
    api_key: SecretStr = ""
    api_secret: SecretStr = ""
    access_token: SecretStr = ""
    
    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: int) -> int:
        if v < 0: raise ValueError("Priority must be non-negative")
        return v

class ZerodhaConfig(BaseProviderConfig):
    name: str = "zerodha"
    redirect_url: str = "http://localhost:8080/callback"
    totp_secret: Optional[SecretStr] = None
    token_file: str = "~/.tradex/tokens/zerodha.json"
    rate_limit_per_second: float = 3.0
    rate_limit_per_minute: int = 100
    rate_limit_per_day: int = 10000
    base_url: str = "https://api.kite.trade"
    connect_timeout: float = 10.0
    read_timeout: float = 30.0
    
    @field_validator("rate_limit_per_second", "rate_limit_per_minute", "rate_limit_per_day")
    @classmethod
    def validate_rates(cls, v: float) -> float:
        if v <= 0: raise ValueError("Rate limits must be positive")
        return v

class DhanConfig(BaseProviderConfig):
    name: str = "dhan"
    client_id: str = ""
    access_token: SecretStr = ""
    static_ip: Optional[str] = None
    token_file: str = "~/.tradex/tokens/dhan.json"
    rate_limit_per_second: float = 5.0
    rate_limit_per_minute: int = 250
    rate_limit_per_day: int = 7000
    base_url: str = "https://api.dhan.co"
    sandbox: bool = False
    connect_timeout: float = 10.0
    read_timeout: float = 30.0
    
    @field_validator("rate_limit_per_second", "rate_limit_per_minute", "rate_limit_per_day")
    @classmethod
    def validate_rates(cls, v: float) -> float:
        if v <= 0: raise ValueError("Rate limits must be positive")
        return v

ProviderConfig = Union[ZerodhaConfig, DhanConfig, BaseProviderConfig]

# =============================================================================
# Data Provider
# =============================================================================

class DataProviderConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", slots=True, validate_default=True)
    
    default_provider: str = "zerodha"
    cache_enabled: bool = True
    cache_ttl_seconds: int = 3600
    instrument_cache_ttl_seconds: int = 86400
    storage_compression: str = "zstd"
    storage_partition_by: str = "month"
    storage_row_group_size: int = 1_000_000
    max_retries: int = 3
    retry_base_delay: float = 1.0
    retry_max_delay: float = 60.0
    retry_exponential_base: float = 2.0
    chunk_size_days: Dict[str, int] = Field(default_factory=lambda: {
        "minute": 30, "3minute": 60, "5minute": 90,
        "15minute": 180, "30minute": 360, "60minute": 720, "day": 2000
    })
    providers: Dict[str, ProviderConfig] = Field(default_factory=dict)
    
    @field_validator("storage_compression")
    @classmethod
    def validate_compression(cls, v: str) -> str:
        if v not in {"zstd", "snappy", "gzip", "lz4", "none"}:
            raise ValueError("Invalid compression")
        return v
    
    @field_validator("storage_partition_by")
    @classmethod
    def validate_partition(cls, v: str) -> str:
        if v not in {"day", "month", "year"}:
            raise ValueError("Invalid partition")
        return v
    
    def get_provider(self, name: str) -> ProviderConfig | None:
        return self.providers.get(name)
    
    def get_enabled_providers(self) -> List[ProviderConfig]:
        return sorted(
            [p for p in self.providers.values() if p.enabled],
            key=lambda p: p.priority, reverse=True
        )

# =============================================================================
# Engine
# =============================================================================

class BacktestConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", slots=True, validate_default=True)
    
    symbol: str
    exchange: Exchange = Exchange.NSE
    segment: Segment = Segment.EQ
    base_interval: Interval = Interval.MINUTE_1
    timeframes: List[Interval] = Field(default_factory=lambda: [Interval.MINUTE_1])
    from_date: datetime
    to_date: datetime
    strict_validation: bool = True
    
    @field_validator("from_date", "to_date", mode="before")
    @classmethod
    def parse_dt(cls, v: str | datetime) -> datetime:
        if isinstance(v, str):
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            if dt.tzinfo is None: dt = dt.replace(tzinfo=IST)
            return dt
        return v
    
    @field_validator("to_date")
    @classmethod
    def validate_range(cls, v: datetime, info) -> datetime:
        if "from_date" in info.data and v <= info.data["from_date"]:
            raise ValueError("to_date must be after from_date")
        return v
    
    @field_validator("timeframes")
    @classmethod
    def validate_tfs(cls, v: List[Interval]) -> List[Interval]:
        if not v: raise ValueError("At least one timeframe required")
        return v

class PositionManagerConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", slots=True)
    initial_cash: float = 1_000_000.0
    commission_per_share: float = 0.0
    commission_pct: float = 0.0
    slippage_pct: float = 0.0

class TradeLoggerConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", slots=True)
    base_dir: str = "backtest_results"
    strategy_name: str = "default"
    output_format: str = "csv"

class DataFeederConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", slots=True)
    cache_ttl_seconds: int = 3600
    chunk_size_days: int = 30
    provider_override: Optional[str] = None

class EngineConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", slots=True)
    backtest: BacktestConfig
    position_manager: PositionManagerConfig = Field(default_factory=PositionManagerConfig)
    trade_logger: TradeLoggerConfig = Field(default_factory=TradeLoggerConfig)
    data_feeder: DataFeederConfig = Field(default_factory=DataFeederConfig)