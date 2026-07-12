# Configuration Module

## Location
`src/backtest_engine/data_provider/config/`

## Components
- `models.py` - Dataclass configs with Pydantic validation
- `loader.py` - `ConfigLoader` (3-tier priority loading)

## Config Models
```python
@dataclass
class DataProviderConfig:
    providers: Dict[str, ProviderConfig]
    storage: StorageConfig
    cache: CacheConfig
    logging: LoggingConfig

@dataclass
class ProviderConfig:
    enabled: bool = True
    rate_limit_per_second: int
    rate_limit_per_minute: int
    rate_limit_per_day: int
    base_url: str = ""
    sandbox: bool = False
    token_file: str = ""
    redirect_url: str = ""
    totp_secret: str = ""

@dataclass
class ZerodhaConfig(ProviderConfig):
    api_key: str
    api_secret: str

@dataclass
class DhanConfig(ProviderConfig):
    client_id: str
    access_token: str  # 24hr JWT
```

## ConfigLoader - 3-Tier Priority
1. **Environment Variables** (highest): `TRADEX_PROVIDERS_ZERODHA_API_KEY`, `TRADEX_STORAGE_BASE_PATH`, etc.
2. **User Config**: `~/.tradex/config.yml`
3. **Project Config**: `./config.yml` (lowest)

### Deep Merge
- Dicts merged recursively
- Lists replaced (not merged)
- Env vars parsed with `TRADEX_` prefix, `__` for nesting

```python
loader = ConfigLoader()
config = loader.load()  # Auto-discovers config files
# Or explicit:
config = loader.load(config_path="~/.tradex/config.yml")
```

### Env Var Examples
```bash
export TRADEX_PROVIDERS_ZERODHA_API_KEY="your_key"
export TRADEX_PROVIDERS_ZERODHA_API_SECRET="your_secret"
export TRADEX_PROVIDERS_DHAN_ACCESS_TOKEN="eyJhbGciOiJ..."
export TRADEX_STORAGE_BASE_PATH="~/data"
export TRADEX_CACHE_MEMORY_MAX_SIZE="2000"
```

## Config File Example
```yaml
providers:
  zerodha:
    enabled: true
    api_key: "your_api_key"
    api_secret: "your_api_secret"
    redirect_url: "http://127.0.0.1:8080"
    token_file: "~/.tradex/tokens/zerodha.enc"
    rate_limit_per_second: 3
    rate_limit_per_minute: 100
    rate_limit_per_day: 3000
  dhan:
    enabled: true
    client_id: "your_client_id"
    access_token: "eyJhbGciOiJIUzI1NiIs..."  # 24hr JWT
    rate_limit_per_second: 5
    rate_limit_per_minute: 300
    rate_limit_per_day: 7000

storage:
  base_path: "~/.tradex/data"
  partition_by: "month"
  compression: "snappy"

cache:
  memory_max_size: 1000
  disk_path: "~/.tradex/cache"
  disk_max_size_mb: 500

logging:
  level: "INFO"
  file: "~/.tradex/logs/data_provider.log"
```