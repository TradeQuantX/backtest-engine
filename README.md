# TradeQuantX Backtest Engine

A high-performance, event-driven backtesting framework for quantitative research — compiled to C extensions via **Nuitka** for maximum execution speed.

## Overview

TradeQuantX Backtest Engine is designed for **quantitative researchers with minimal Python knowledge**. The interface is radically simple — install, configure, and run. The backend is exceptionally powerful — all core modules are compiled to optimized C extensions, delivering near-native performance for heavy research workloads.

### Key Features

- **Nuitka-compiled C extensions** — Core engine modules compiled to `.so` binaries (~2.2MB) for 10-50x speedup over interpreted Python
- **Zero-config configuration** — 3-tier priority: `TRADEX_*` env vars → `~/.tradex/config.yml` → `./config.yml`
- **Multi-broker support** — Zerodha (Kite Connect) and Dhan HQ providers built-in
- **High-performance data layer** — Polars + PyArrow for columnar analytics, async HTTP via httpx
- **Type-safe throughout** — Pydantic v2 models, full type hints, compiled stubs (`.pyi`)
- **Researcher-friendly API** — Single import: `from backtest_engine.data_provider import DataProviderClient`

## Installation

### From GitHub (Recommended for Researchers)

```bash
# Latest release
pip install git+https://github.com/USERNAME/REPO_NAME.git

# Specific version tag
pip install git+https://github.com/USERNAME/REPO_NAME.git@v0.1.0

# Development branch
pip install git+https://github.com/USERNAME/REPO_NAME.git@main
```

### From Pre-built Wheel (Fastest Install)

```bash
# Download from GitHub Releases
pip install backtest_engine-0.1.0-cp313-cp313-linux_x86_64.whl
```

### From Source (Development)

```bash
# Prerequisites: Python 3.11+, uv, gcc, python3-dev
git clone https://github.com/USERNAME/REPO_NAME.git
cd REPO_NAME

# Build wheel (uses Nuitka via pyproject.toml)
uv build --wheel --no-build-isolation --out-dir dist

# Install
pip install dist/backtest_engine-*.whl
```

## Quick Start

```python
from backtest_engine.data_provider import DataProviderClient, load_config

# Load config (auto-discovers ~/.tradex/config.yml or ./config.yml)
config = load_config()

# Create client
client = DataProviderClient(config)

# Fetch historical data
from backtest_engine.data_provider import HistoricalDataRequest, Exchange, Segment, Interval, InstrumentType

request = HistoricalDataRequest(
    exchange=Exchange.NSE,
    segment=Segment.EQUITY,
    symbol="RELIANCE",
    interval=Interval.DAY_1,
    instrument_type=InstrumentType.EQUITY,
    from_date="2024-01-01",
    to_date="2024-12-31",
)

response = client.get_historical_data(request)
print(response.data.head())  # Polars DataFrame
```

## Configuration

The engine uses a **3-tier configuration priority** (highest to lowest):

1. **Environment variables** — `TRADEX_*` prefix (e.g., `TRADEX_ZERODHA_API_KEY`)
2. **User config** — `~/.tradex/config.yml`
3. **Project config** — `./config.yml` (in current working directory)

### Example `~/.tradex/config.yml`

```yaml
zerodha:
  api_key: "your_api_key"
  api_secret: "your_api_secret"
  access_token: "your_access_token"  # Optional, auto-generated if not provided

dhan:
  client_id: "your_client_id"
  access_token: "your_access_token"

# Optional defaults
defaults:
  exchange: "NSE"
  segment: "EQUITY"
  interval: "DAY_1"
```

### Environment Variables

```bash
export TRADEX_ZERODHA_API_KEY="your_key"
export TRADEX_ZERODHA_API_SECRET="your_secret"
export TRADEX_DHAN_CLIENT_ID="your_id"
export TRADEX_DHAN_ACCESS_TOKEN="your_token"
```

## Local Build Steps

```bash
# Install dependencies
uv sync --dev

# Build Nuitka-compiled wheel
./build_nuitka_package.sh
# Or directly:
uv build --wheel --no-build-isolation --out-dir dist

# Verify
pip install dist/backtest_engine-*.whl
python -c "from backtest_engine.data_provider import DataProviderClient; print('OK')"
```

## CI/CD Pipeline

The project uses **GitHub Actions** for automated builds (`.github/workflows/build.yml`):

- **Trigger**: Push tag `v*` or manual dispatch
- **Platform**: Ubuntu latest, Python 3.13
- **Process**: Checkout → Setup Python → Install uv → System deps → Install Nuitka → Build wheel → Verify → Test import → Upload artifact → Create GitHub Release
- **Output**: `backtest_engine-<version>-cp313-cp313-linux_x86_64.whl` with compiled `.so` extension (~2.2MB)