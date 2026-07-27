"""
Dynaconf configuration instance with validators.

Single source of truth for configuration loading.
"""

from pathlib import Path
from dynaconf import Dynaconf, Validator


def find_project_root() -> Path:
    """Find project root by looking for pyproject.toml or .git directory."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists() or (parent / ".git").exists():
            return parent
    # Fallback: assume standard layout
    return current.parent.parent.parent.parent


PROJECT_ROOT = find_project_root()
USER_CONFIG_DIR = Path.home() / ".tradex"

settings = Dynaconf(
    settings_files=[
        # User config (lowest priority)
        USER_CONFIG_DIR / "config.yaml",
        USER_CONFIG_DIR / ".secrets.yaml",
        # Project config (higher priority - overrides user)
        PROJECT_ROOT / "config.yaml",
        # Project secrets (highest priority)
        PROJECT_ROOT / ".secrets.yaml",
    ],
    environments=False,        # No layered environments
    envvar_prefix=False,       # No environment variables
    load_dotenv=False,         # No .env files
    merge_enabled=True,        # Deep merge nested dicts
    validators=[
        # Data Provider validators
        Validator("DATA_PROVIDER.DEFAULT_PROVIDER", is_in=["zerodha", "dhan"]),
        Validator("DATA_PROVIDER.STORAGE_COMPRESSION", is_in=["zstd", "snappy", "gzip", "lz4", "none"]),
        Validator("DATA_PROVIDER.STORAGE_PARTITION_BY", is_in=["day", "month", "year"]),
        Validator("DATA_PROVIDER.CACHE_TTL_SECONDS", gte=0),
        Validator("DATA_PROVIDER.MAX_RETRIES", gte=0),
        Validator("DATA_PROVIDER.RETRY_BASE_DELAY", gte=0),
        Validator("DATA_PROVIDER.RETRY_MAX_DELAY", gte=0),
        Validator("DATA_PROVIDER.RETRY_EXPONENTIAL_BASE", gt=1),
        
        # Provider secrets (conditional on enabled)
        Validator("DATA_PROVIDER.PROVIDERS.ZERODHA.API_KEY", must_exist=True,
                  when=Validator("DATA_PROVIDER.PROVIDERS.ZERODHA.ENABLED", eq=True)),
        Validator("DATA_PROVIDER.PROVIDERS.ZERODHA.API_SECRET", must_exist=True,
                  when=Validator("DATA_PROVIDER.PROVIDERS.ZERODHA.ENABLED", eq=True)),
        Validator("DATA_PROVIDER.PROVIDERS.DHAN.API_KEY", must_exist=True,
                  when=Validator("DATA_PROVIDER.PROVIDERS.DHAN.ENABLED", eq=True)),
        Validator("DATA_PROVIDER.PROVIDERS.DHAN.CLIENT_ID", must_exist=True,
                  when=Validator("DATA_PROVIDER.PROVIDERS.DHAN.ENABLED", eq=True)),
        Validator("DATA_PROVIDER.PROVIDERS.DHAN.ACCESS_TOKEN", must_exist=True,
                  when=Validator("DATA_PROVIDER.PROVIDERS.DHAN.ENABLED", eq=True)),
        
        # Engine validators
        Validator("BACKTEST.SYMBOL", must_exist=True),
        Validator("BACKTEST.FROM_DATE", must_exist=True),
        Validator("BACKTEST.TO_DATE", must_exist=True),
        Validator("BACKTEST.BASE_INTERVAL", is_in=[
            "1minute", "3minute", "5minute", "10minute", "15minute",
            "30minute", "60minute", "day", "week", "month"
        ]),
    ],
)

# Fail fast on invalid config
settings.validators.validate()