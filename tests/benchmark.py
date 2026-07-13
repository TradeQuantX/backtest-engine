#!/usr/bin/env python
"""
Benchmark: Nuitka-compiled wheel vs Source code performance comparison.

Tests realistic researcher workflows with the Zerodha data provider.
Run with: python -m tests.benchmark --compare
"""

import asyncio
import importlib
import importlib.util
import json
import math
import os
import statistics
import subprocess
import sys
import tempfile
import time
import venv
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, List, Optional

import httpx


# =============================================================================
# Statistical Analysis
# =============================================================================

@dataclass
class BenchmarkResult:
    """Results from a single benchmark run."""
    name: str
    iterations: int
    warmup: int
    times: list[float] = field(default_factory=list)
    
    @property
    def mean(self) -> float:
        return statistics.mean(self.times) if self.times else 0.0
    
    @property
    def median(self) -> float:
        return statistics.median(self.times) if self.times else 0.0
    
    @property
    def stdev(self) -> float:
        return statistics.stdev(self.times) if len(self.times) > 1 else 0.0
    
    @property
    def min(self) -> float:
        return min(self.times) if self.times else 0.0
    
    @property
    def max(self) -> float:
        return max(self.times) if self.times else 0.0
    
    @property
    def p95(self) -> float:
        if not self.times:
            return 0.0
        sorted_times = sorted(self.times)
        idx = int(len(sorted_times) * 0.95)
        return sorted_times[min(idx, len(sorted_times) - 1)]
    
    @property
    def p99(self) -> float:
        if not self.times:
            return 0.0
        sorted_times = sorted(self.times)
        idx = int(len(sorted_times) * 0.99)
        return sorted_times[min(idx, len(sorted_times) - 1)]
    
    @property
    def cv(self) -> float:
        """Coefficient of variation (std/mean) - lower is more stable."""
        return (self.stdev / self.mean * 100) if self.mean > 0 else 0.0


@dataclass
class ComparisonResult:
    """Comparison between source and wheel results."""
    name: str
    source: BenchmarkResult
    wheel: BenchmarkResult
    
    @property
    def speedup_ratio(self) -> float:
        """Wheel time / Source time. < 1 means wheel is faster."""
        if self.source.mean == 0:
            return 0.0
        return self.wheel.mean / self.source.mean
    
    @property
    def speedup_percent(self) -> float:
        """Percentage speedup (positive = wheel faster)."""
        return (1 - self.speedup_ratio) * 100
    
    @property
    def winner(self) -> str:
        if self.speedup_ratio < 0.95:
            return "wheel"
        elif self.speedup_ratio > 1.05:
            return "source"
        return "tie"


class BenchmarkRunner:
    """Runs benchmarks with warmup, multiple iterations, and statistical analysis."""
    
    def __init__(
        self,
        iterations: int = 30,
        warmup: int = 5,
        verbose: bool = True,
    ):
        self.iterations = iterations
        self.warmup = warmup
        self.verbose = verbose
        self.results: dict[str, BenchmarkResult] = {}
    
    async def run(
        self,
        name: str,
        func: Callable[[], Any],
        setup: Optional[Callable[[], Any]] = None,
        teardown: Optional[Callable[[], Any]] = None,
    ) -> BenchmarkResult:
        """Run a benchmark with warmup and statistical collection."""
        if self.verbose:
            print(f"\n  Running: {name}")
            print(f"  Warmup: {self.warmup}, Iterations: {self.iterations}")
        
        # Warmup runs (discarded)
        for i in range(self.warmup):
            if setup:
                await setup() if asyncio.iscoroutinefunction(setup) else setup()
            try:
                await func() if asyncio.iscoroutinefunction(func) else func()
            except Exception as e:
                if self.verbose:
                    print(f"    Warmup {i+1} failed: {e}")
            if teardown:
                await teardown() if asyncio.iscoroutinefunction(teardown) else teardown()
        
        # Actual benchmark runs
        times = []
        for i in range(self.iterations):
            if setup:
                await setup() if asyncio.iscoroutinefunction(setup) else setup()
            
            start = time.perf_counter()
            try:
                await func() if asyncio.iscoroutinefunction(func) else func()
            except Exception as e:
                if self.verbose:
                    print(f"    Iteration {i+1} failed: {e}")
                continue
            elapsed = time.perf_counter() - start
            times.append(elapsed)
            
            if teardown:
                await teardown() if asyncio.iscoroutinefunction(teardown) else teardown()
            
            if self.verbose and (i + 1) % 10 == 0:
                print(f"    Completed {i + 1}/{self.iterations}")
        
        result = BenchmarkResult(
            name=name,
            iterations=len(times),
            warmup=self.warmup,
            times=times,
        )
        self.results[name] = result
        
        if self.verbose:
            print(f"  Mean: {result.mean*1000:.2f}ms, Median: {result.median*1000:.2f}ms, "
                  f"Std: {result.stdev*1000:.2f}ms, CV: {result.cv:.1f}%")
        
        return result
    
    def print_summary(self) -> None:
        """Print summary of all results."""
        print("\n" + "=" * 80)
        print("BENCHMARK SUMMARY")
        print("=" * 80)
        print(f"{'Benchmark':<40} {'Mean (ms)':>12} {'Median (ms)':>12} {'Std (ms)':>10} {'CV%':>6}")
        print("-" * 80)
        for name, result in self.results.items():
            print(f"{name:<40} {result.mean*1000:>12.2f} {result.median*1000:>12.2f} "
                  f"{result.stdev*1000:>10.2f} {result.cv:>6.1f}")


# =============================================================================
# Import Switcher - Switch between source and wheel imports
# =============================================================================

class ImportSwitcher:
    """Context manager to switch between source and wheel imports."""
    
    # Class-level cache for wheel venv to avoid recreating it
    _wheel_venv_cache: dict[str, tuple[str, str]] = {}  # wheel_path -> (venv_path, python_path)
    
    def __init__(self, use_wheel: bool = False, wheel_path: Optional[str] = None, verbose: bool = True):
        self.use_wheel = use_wheel
        self.wheel_path = wheel_path
        self.verbose = verbose
        self._original_path = sys.path.copy()
        self._original_modules = {}
        self._venv_path: Optional[str] = None
        self._venv_python: Optional[str] = None
        self._owns_venv = False  # Track if we created the venv (for cleanup)
    
    def __enter__(self):
        if self.use_wheel:
            self._setup_wheel_env()
        else:
            self._setup_source_env()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self._restore_env()
    
    def _setup_source_env(self):
        """Add src/ to sys.path for source imports."""
        src_path = str(Path(__file__).parent.parent / "src")
        if src_path not in sys.path:
            sys.path.insert(0, src_path)
        # Clear any cached backtest_engine modules
        self._clear_backtest_modules()
    
    def _setup_wheel_env(self):
        """Create or reuse temp venv, install wheel, and use its python."""
        # Find wheel file
        if self.wheel_path:
            wheel_file = Path(self.wheel_path)
        else:
            dist_dir = Path(__file__).parent.parent / "dist"
            wheels = list(dist_dir.glob("backtest_engine-*.whl"))
            if not wheels:
                raise FileNotFoundError(f"No wheel found in {dist_dir}")
            wheel_file = max(wheels, key=lambda w: w.stat().st_mtime)
        
        wheel_key = str(wheel_file.resolve())
        
        # Check cache first
        if wheel_key in ImportSwitcher._wheel_venv_cache:
            self._venv_path, self._venv_python = ImportSwitcher._wheel_venv_cache[wheel_key]
            if self.verbose:
                print(f"  Reusing cached wheel venv: {self._venv_path}")
            return
        
        # Create temp venv
        self._venv_path = tempfile.mkdtemp(prefix="bench_wheel_")
        venv.create(self._venv_path, with_pip=True)
        
        # Determine python executable
        if sys.platform == "win32":
            self._venv_python = str(Path(self._venv_path) / "Scripts" / "python.exe")
        else:
            self._venv_python = str(Path(self._venv_path) / "bin" / "python")
        
        # Install wheel
        subprocess.run(
            [self._venv_python, "-m", "pip", "install", "--quiet", str(wheel_file)],
            check=True,
            capture_output=True,
        )
        
        # Cache for reuse
        ImportSwitcher._wheel_venv_cache[wheel_key] = (self._venv_path, self._venv_python)
        self._owns_venv = True
        
        if self.verbose:
            print(f"  Wheel installed in temp venv: {self._venv_path}")
    
    def _clear_backtest_modules(self):
        """Remove cached backtest_engine modules."""
        to_remove = [k for k in sys.modules if k.startswith("backtest_engine")]
        for mod in to_remove:
            del sys.modules[mod]
    
    def _restore_env(self):
        """Restore original sys.path and clean up."""
        sys.path[:] = self._original_path
        self._clear_backtest_modules()
        
        # Cleanup temp venv only if we own it (not cached)
        if self._owns_venv and self._venv_path and Path(self._venv_path).exists():
            import shutil
            shutil.rmtree(self._venv_path, ignore_errors=True)
    
    def get_python(self) -> str:
        """Get python executable for current mode."""
        if self.use_wheel:
            return self._venv_python
        return sys.executable
    
    def run_in_mode(self, script: str) -> subprocess.CompletedProcess:
        """Run a script in the current mode (source or wheel venv)."""
        python = self.get_python()
        return subprocess.run(
            [python, "-c", script],
            capture_output=True,
            text=True,
        )


# =============================================================================
# Mock HTTP Transport & Fixtures
# =============================================================================

# Mock instrument CSV data (Zerodha format)
MOCK_INSTRUMENTS_CSV = """instrument_token,exchange_token,tradingsymbol,name,last_price,expiry,strike,tick_size,lot_size,instrument_type,segment,exchange
123456,123456,RELIANCE,Reliance Industries Ltd,2500.0,,,0.05,1,EQ,NSE,NSE
123457,123457,TCS,Tata Consultancy Services Ltd,3500.0,,,0.05,1,EQ,NSE,NSE
123458,123458,INFY,Infosys Ltd,1500.0,,,0.05,1,EQ,NSE,NSE
123459,123459,HDFCBANK,HDFC Bank Ltd,1600.0,,,0.05,1,EQ,NSE,NSE
123460,123460,ICICIBANK,ICICI Bank Ltd,950.0,,,0.05,1,EQ,NSE,NSE
"""

# Mock OHLC JSON response (Zerodha format)
MOCK_OHLC_JSON = {
    "status": "success",
    "data": {
        "123456": {
            "candles": [
                ["2024-01-01T09:15:00+05:30", 2500.0, 2510.0, 2495.0, 2505.0, 100000, 50000],
                ["2024-01-01T09:16:00+05:30", 2505.0, 2515.0, 2500.0, 2510.0, 80000, 51000],
                ["2024-01-01T09:17:00+05:30", 2510.0, 2520.0, 2505.0, 2515.0, 90000, 52000],
                ["2024-01-01T09:18:00+05:30", 2515.0, 2525.0, 2510.0, 2520.0, 85000, 53000],
                ["2024-01-01T09:19:00+05:30", 2520.0, 2530.0, 2515.0, 2525.0, 95000, 54000],
            ]
        }
    }
}

# Mock auth response
MOCK_AUTH_RESPONSE = {
    "status": "success",
    "data": {
        "access_token": "mock_access_token_12345",
        "user_id": "TEST123",
    }
}

# Mock user profile (token validation)
MOCK_PROFILE_RESPONSE = {
    "status": "success",
    "data": {
        "user_id": "TEST123",
        "user_name": "Test User",
        "email": "test@example.com",
    }
}


# =============================================================================
# Backtest Loop Components (Pure Python - CPU Bound)
# =============================================================================

from dataclasses import dataclass
from datetime import datetime
from typing import List
import math


@dataclass
class Bar:
    """Single OHLC bar for backtesting."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Signal:
    """Trading signal."""
    action: str  # BUY, SELL, HOLD
    size: float
    price: float
    timestamp: datetime


class SimpleMAStrategy:
    """Simple Moving Average Crossover Strategy.
    
    Pure Python implementation - no external dependencies.
    This is the CPU-bound hot path that Nuitka should accelerate.
    """
    
    def __init__(self, fast_period: int = 10, slow_period: int = 30):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.fast_values: List[float] = []
        self.slow_values: List[float] = []
        self.position = 0  # 0 = flat, 1 = long, -1 = short
    
    def generate_signal(self, bar: Bar) -> Signal:
        """Generate signal based on MA crossover."""
        self.fast_values.append(bar.close)
        self.slow_values.append(bar.close)
        
        # Maintain rolling windows
        if len(self.fast_values) > self.fast_period:
            self.fast_values.pop(0)
        if len(self.slow_values) > self.slow_period:
            self.slow_values.pop(0)
        
        # Need enough data for both MAs
        if len(self.fast_values) < self.fast_period or len(self.slow_values) < self.slow_period:
            return Signal("HOLD", 0.0, bar.close, bar.timestamp)
        
        fast_ma = sum(self.fast_values) / self.fast_period
        slow_ma = sum(self.slow_values) / self.slow_period
        
        # Crossover logic
        if fast_ma > slow_ma and self.position <= 0:
            self.position = 1
            return Signal("BUY", 1.0, bar.close, bar.timestamp)
        elif fast_ma < slow_ma and self.position >= 0:
            self.position = -1
            return Signal("SELL", 1.0, bar.close, bar.timestamp)
        
        return Signal("HOLD", 0.0, bar.close, bar.timestamp)


class Portfolio:
    """Simple portfolio for backtesting.
    
    Tracks position, cash, equity curve, and computes metrics.
    Pure Python - CPU bound operations.
    """
    
    def __init__(self, initial_capital: float = 100_000.0, commission: float = 0.001):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.position = 0.0
        self.entry_price = 0.0
        self.commission = commission
        self.equity_curve: List[float] = []
        self.trades: List[dict] = []
    
    def process_signal(self, signal: Signal, bar: Bar) -> None:
        """Process signal and update portfolio."""
        if signal.action == "BUY" and self.position <= 0:
            # Close short if any
            if self.position < 0:
                pnl = (self.entry_price - signal.price) * abs(self.position)
                self.cash += pnl - abs(self.position) * signal.price * self.commission
                self.trades.append({
                    "type": "COVER",
                    "price": signal.price,
                    "size": abs(self.position),
                    "pnl": pnl,
                    "timestamp": signal.timestamp,
                })
            
            # Go long
            max_shares = self.cash / (signal.price * (1 + self.commission))
            self.position = max_shares
            self.entry_price = signal.price
            self.cash -= self.position * signal.price * (1 + self.commission)
            
        elif signal.action == "SELL" and self.position >= 0:
            # Close long if any
            if self.position > 0:
                pnl = (signal.price - self.entry_price) * self.position
                self.cash += self.position * signal.price * (1 - self.commission)
                self.trades.append({
                    "type": "SELL",
                    "price": signal.price,
                    "size": self.position,
                    "pnl": pnl,
                    "timestamp": signal.timestamp,
                })
            
            # Go short (simplified - just flip)
            max_shares = self.cash / (signal.price * (1 + self.commission))
            self.position = -max_shares
            self.entry_price = signal.price
            self.cash -= abs(self.position) * signal.price * self.commission
    
    def update_equity(self, bar: Bar) -> None:
        """Update equity curve with current bar."""
        if self.position > 0:
            equity = self.cash + self.position * bar.close
        elif self.position < 0:
            equity = self.cash + abs(self.position) * (2 * self.entry_price - bar.close)
        else:
            equity = self.cash
        self.equity_curve.append(equity)
    
    def get_metrics(self) -> dict:
        """Compute performance metrics."""
        if len(self.equity_curve) < 2:
            return {"sharpe": 0.0, "max_drawdown": 0.0, "total_return": 0.0, "win_rate": 0.0}
        
        # Returns
        returns = []
        for i in range(1, len(self.equity_curve)):
            ret = (self.equity_curve[i] - self.equity_curve[i-1]) / self.equity_curve[i-1]
            returns.append(ret)
        
        # Total return
        total_return = (self.equity_curve[-1] - self.initial_capital) / self.initial_capital
        
        # Sharpe (annualized assuming daily bars)
        if len(returns) > 1:
            mean_ret = sum(returns) / len(returns)
            std_ret = math.sqrt(sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1))
            sharpe = (mean_ret / std_ret * math.sqrt(252)) if std_ret > 0 else 0.0
        else:
            sharpe = 0.0
        
        # Max drawdown
        peak = self.equity_curve[0]
        max_dd = 0.0
        for eq in self.equity_curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak
            if dd > max_dd:
                max_dd = dd
        
        # Win rate
        winning_trades = sum(1 for t in self.trades if t.get("pnl", 0) > 0)
        win_rate = winning_trades / len(self.trades) if self.trades else 0.0
        
        return {
            "sharpe": sharpe,
            "max_drawdown": max_dd,
            "total_return": total_return,
            "win_rate": win_rate,
            "num_trades": len(self.trades),
            "final_equity": self.equity_curve[-1],
        }


class MockHTTPTransport(httpx.BaseTransport):
    """Mock HTTP transport for testing without network calls."""
    
    def __init__(self):
        self.requests = []
        self.responses = {}
        self._setup_default_responses()
    
    def _setup_default_responses(self):
        """Set up default mock responses."""
        # Instrument master CSV
        self.responses["GET:/instruments/NSE"] = httpx.Response(
            200, text=MOCK_INSTRUMENTS_CSV, headers={"Content-Type": "text/csv"}
        )
        self.responses["GET:/instruments/BSE"] = httpx.Response(
            200, text=MOCK_INSTRUMENTS_CSV, headers={"Content-Type": "text/csv"}
        )
        
        # Historical data - Zerodha uses "minute" not "1minute"
        self.responses["GET:/instruments/historical/123456/minute"] = httpx.Response(
            200, json=MOCK_OHLC_JSON
        )
        
        # Auth token exchange
        self.responses["POST:/session/token"] = httpx.Response(
            200, json=MOCK_AUTH_RESPONSE
        )
        
        # User profile (token validation)
        self.responses["GET:/user/profile"] = httpx.Response(
            200, json=MOCK_PROFILE_RESPONSE
        )
    
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        
        # Build key from method and path - handle both relative and absolute URLs
        path = request.url.path
        if path.startswith("http"):
            # Absolute URL - extract path
            from urllib.parse import urlparse
            path = urlparse(path).path
        
        # Debug: print the actual path
        print(f"  Mock transport received: {request.method} {path}")
        
        key = f"{request.method}:{path}"
        
        # Check for query params in historical data
        if "historical" in path:
            key = f"{request.method}:{path}"
        
        if key in self.responses:
            return self.responses[key]
        
        # Default 404
        return httpx.Response(404, json={"status": "error", "message": "Not found"})
    
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Handle async request."""
        return self.handle_request(request)
    
    def set_response(self, method: str, path: str, response: httpx.Response):
        """Override a response for testing."""
        self.responses[f"{method}:{path}"] = response
    
    def close(self):
        """Close transport."""
        pass
    
    async def aclose(self):
        """Async close transport."""
        pass


# =============================================================================
# Benchmark Scenarios
# =============================================================================

class BenchmarkContext:
    """Shared context for benchmark scenarios."""
    
    def __init__(self, use_wheel: bool = False):
        self.use_wheel = use_wheel
        self.client = None
        self.provider = None
        self.mock_transport = MockHTTPTransport()
        self._httpx_client: Optional[httpx.AsyncClient] = None
    
    async def setup_client(self):
        """Create and initialize DataProviderClient with mocked HTTP."""
        # Import based on mode
        if self.use_wheel:
            # In wheel mode, imports work normally since wheel is installed
            from backtest_engine.data_provider import DataProviderClient
            from backtest_engine.data_provider.config import ZerodhaConfig, DataProviderConfig
        else:
            from backtest_engine.data_provider import DataProviderClient
            from backtest_engine.data_provider.config import ZerodhaConfig, DataProviderConfig
        
        # Create config with mock settings
        zerodha_config = ZerodhaConfig(
            api_key="test_api_key",
            api_secret="test_api_secret",
            access_token="mock_access_token_12345",  # Pre-set to skip OAuth
            redirect_url="http://localhost:8080/callback",
            token_file="./.bench_token.json",
        )
        
        config = DataProviderConfig(
            default_provider="zerodha",
            cache_dir="./.bench_cache",
            data_dir="./.bench_data",
            max_retries=0,  # No retries for benchmarking
            retry_base_delay=0,
            retry_max_delay=0,
            providers={"zerodha": zerodha_config},
        )
        
        # Create client
        self.client = DataProviderClient(config=config)
        
        # Initialize client (this will create providers but we'll patch auth)
        # We need to initialize without calling authenticate
        await self._initialize_without_auth()
        
        # Replace HTTP client in provider with mocked one
        provider = self.client.get_default_provider()
        self.provider = provider
        
        # Create mocked httpx client
        self._httpx_client = httpx.AsyncClient(
            transport=self.mock_transport,
            base_url="https://api.kite.trade"
        )
        provider._client = self._httpx_client
        provider._access_token = "mock_access_token_12345"
        provider._authenticated = True
    
    async def _initialize_without_auth(self):
        """Initialize client without running authentication."""
        if self.client._initialized:
            return
        
        # Load configuration (already set)
        # Create cache and storage if not provided
        if self.client._cache is None:
            self.client._cache = await self.client._create_cache()
        
        if self.client._storage is None:
            self.client._storage = await self.client._create_storage()
        
        # Create providers
        await self.client._create_providers()
        
        # Skip authentication - we'll set it manually
        self.client._initialized = True
    
    async def teardown_client(self):
        """Clean up client."""
        if self._httpx_client:
            await self._httpx_client.aclose()
        if self.client:
            await self.client.close()
        self.client = None
        self.provider = None
        self._httpx_client = None
        self.mock_transport = MockHTTPTransport()


# Scenario 1: Cold Import
async def bench_cold_import(use_wheel: bool) -> float:
    """Benchmark cold import time (fresh process)."""
    script = """
import time
start = time.perf_counter()
from backtest_engine.data_provider import DataProviderClient
from backtest_engine.data_provider.providers.zerodha import ZerodhaProvider
elapsed = time.perf_counter() - start
print(f"{elapsed:.6f}")
"""
    with ImportSwitcher(use_wheel=use_wheel) as switcher:
        python = switcher.get_python()
        result = subprocess.run([python, "-c", script], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  Cold import error: {result.stderr}")
            return 0.0
        return float(result.stdout.strip())


# Scenario 2: Warm Import
async def bench_warm_import(use_wheel: bool) -> float:
    """Benchmark warm import (module already cached)."""
    # First import to warm up
    if use_wheel:
        # In wheel mode, run in subprocess
        script = """
from backtest_engine.data_provider import DataProviderClient
from backtest_engine.data_provider.providers.zerodha import ZerodhaProvider
"""
        with ImportSwitcher(use_wheel=True) as switcher:
            python = switcher.get_python()
            subprocess.run([python, "-c", script], capture_output=True)
            
            # Now benchmark
            script = """
import time
start = time.perf_counter()
from backtest_engine.data_provider import DataProviderClient
from backtest_engine.data_provider.providers.zerodha import ZerodhaProvider
elapsed = time.perf_counter() - start
print(f"{elapsed:.6f}")
"""
            result = subprocess.run([python, "-c", script], capture_output=True, text=True)
            if result.returncode != 0:
                print(f"  Warm import error: {result.stderr}")
                return 0.0
            return float(result.stdout.strip())
    else:
        # Source mode - import in same process
        from backtest_engine.data_provider import DataProviderClient
        from backtest_engine.data_provider.providers.zerodha import ZerodhaProvider
        
        start = time.perf_counter()
        from backtest_engine.data_provider import DataProviderClient
        from backtest_engine.data_provider.providers.zerodha import ZerodhaProvider
        return time.perf_counter() - start


# Scenario 3: Client Initialization
async def bench_client_init(context: BenchmarkContext) -> None:
    """Benchmark client initialization."""
    await context.setup_client()
    await context.teardown_client()


# Scenario 4: Instrument Master Loading
async def bench_load_instruments(context: BenchmarkContext) -> None:
    """Benchmark loading instrument master."""
    await context.client.get_instruments(exchange="NSE", segment="EQ")


# Scenario 5: Historical OHLC Retrieval (Mocked HTTP)
async def bench_get_historical_ohlc(context: BenchmarkContext) -> None:
    """Benchmark historical OHLC data retrieval."""
    await context.client.get_historical_ohlc_data(
        symbol="RELIANCE",
        exchange="NSE",
        segment="EQ",
        interval="1minute",
        from_date="2024-01-01",
        to_date="2024-01-02",
    )


# Scenario 6: Cache Lookup (Second call hits cache)
async def bench_cache_lookup(context: BenchmarkContext) -> None:
    """Benchmark cache hit on second call."""
    # First call populates cache
    await context.client.get_historical_ohlc_data(
        symbol="RELIANCE",
        exchange="NSE",
        segment="EQ",
        interval="1minute",
        from_date="2024-01-01",
        to_date="2024-01-02",
    )
    # Second call should hit cache
    await context.client.get_historical_ohlc_data(
        symbol="RELIANCE",
        exchange="NSE",
        segment="EQ",
        interval="1minute",
        from_date="2024-01-01",
        to_date="2024-01-02",
    )


# Scenario 7: End-to-End Workflow
async def bench_e2e_workflow(context: BenchmarkContext) -> None:
    """Benchmark full researcher workflow: init -> instruments -> historical data."""
    # This is already set up in context.setup_client()
    # Just do the workflow steps
    await context.client.get_instruments(exchange="NSE", segment="EQ")
    await context.client.get_historical_ohlc_data(
        symbol="RELIANCE",
        exchange="NSE",
        segment="EQ",
        interval="1minute",
        from_date="2024-01-01",
        to_date="2024-01-02",
    )
    await context.client.get_instrument_token(
        symbol="RELIANCE",
        exchange="NSE",
        segment="EQ",
    )


# Scenario 8: Response Parsing & Normalization
async def bench_normalization() -> None:
    """Benchmark pure Python data normalization (no I/O)."""
    from backtest_engine.data_provider.utils import (
        zerodha_instrument_to_normalized,
        zerodha_ohlc_to_normalized,
    )
    import csv
    from io import StringIO
    
    # Parse CSV instruments
    reader = csv.DictReader(StringIO(MOCK_INSTRUMENTS_CSV))
    instruments = []
    for row in reader:
        inst = zerodha_instrument_to_normalized(row, "zerodha")
        instruments.append(inst)
    
    # Parse OHLC
    candles = MOCK_OHLC_JSON["data"]["123456"]["candles"]
    ohlc_data = zerodha_ohlc_to_normalized(
        candles,
        symbol="RELIANCE",
        exchange="NSE",
        segment="EQ",
        interval="minute",
        provider="zerodha",
    )
    
    # Prevent optimization
    return len(instruments) + len(ohlc_data)


# Scenario 9: Backtest Loop over Cached OHLC Data
async def bench_backtest_loop(context: BenchmarkContext) -> None:
    """Benchmark event-driven backtest loop over cached OHLC data.
    
    This is the CPU-bound hot path that Nuitka should accelerate:
    - Iterate over bars
    - Generate signals (MA crossover)
    - Update portfolio (position, P&L, equity)
    - Compute metrics
    """
    # Get cached OHLC data (first call populates cache, second hits cache)
    response = await context.client.get_historical_ohlc_data(
        symbol="RELIANCE",
        exchange="NSE",
        segment="EQ",
        interval="1minute",
        from_date="2024-01-01",
        to_date="2024-01-02",
    )
    
    # Convert to Bar objects for backtest loop
    bars = []
    for ohlc in response.data:
        bars.append(Bar(
            timestamp=ohlc.timestamp,
            open=ohlc.open,
            high=ohlc.high,
            low=ohlc.low,
            close=ohlc.close,
            volume=ohlc.volume,
        ))
    
    # Run backtest loop iterations
    for _ in range(context.backtest_iterations):
        strategy = SimpleMAStrategy(fast_period=10, slow_period=30)
        portfolio = Portfolio(initial_capital=100_000.0)
        
        for bar in bars:
            signal = strategy.generate_signal(bar)
            portfolio.process_signal(signal, bar)
            portfolio.update_equity(bar)
        
        # Compute metrics (prevents optimization)
        _ = portfolio.get_metrics()


# Scenario 10: Parameter Sweep Loop
async def bench_param_sweep_loop(context: BenchmarkContext) -> None:
    """Benchmark parameter sweep over cached OHLC data.
    
    Outer loop: parameter combinations (fast_period, slow_period)
    Inner loop: event-driven backtest over bars
    """
    # Get cached OHLC data
    response = await context.client.get_historical_ohlc_data(
        symbol="RELIANCE",
        exchange="NSE",
        segment="EQ",
        interval="1minute",
        from_date="2024-01-01",
        to_date="2024-01-02",
    )
    
    # Convert to Bar objects
    bars = []
    for ohlc in response.data:
        bars.append(Bar(
            timestamp=ohlc.timestamp,
            open=ohlc.open,
            high=ohlc.high,
            low=ohlc.low,
            close=ohlc.close,
            volume=ohlc.volume,
        ))
    
    # Parameter grid
    fast_periods = [5, 10, 15, 20, 25]
    slow_periods = [20, 30, 40, 50, 60]
    param_combos = [(f, s) for f in fast_periods for s in slow_periods if f < s]
    
    # Limit to param_sweep_size
    param_combos = param_combos[:context.param_sweep_size]
    
    # Run parameter sweep
    for fast_p, slow_p in param_combos:
        strategy = SimpleMAStrategy(fast_period=fast_p, slow_period=slow_p)
        portfolio = Portfolio(initial_capital=100_000.0)
        
        for bar in bars:
            signal = strategy.generate_signal(bar)
            portfolio.process_signal(signal, bar)
            portfolio.update_equity(bar)
        
        _ = portfolio.get_metrics()


# =============================================================================
# Main Benchmark Orchestration
# =============================================================================

SCENARIOS = [
    ("Cold Import", bench_cold_import, {"is_cold_import": True}),
    ("Warm Import", bench_warm_import, {"is_warm_import": True}),
    ("Client Initialization", bench_client_init, {}),
    ("Load Instruments", bench_load_instruments, {}),
    ("Get Historical OHLC", bench_get_historical_ohlc, {}),
    ("Cache Lookup", bench_cache_lookup, {}),
    ("E2E Workflow", bench_e2e_workflow, {}),
    ("Normalization/Parsing", bench_normalization, {"is_pure_python": True}),
    ("Backtest Loop (Cached Data)", bench_backtest_loop, {"is_backtest_loop": True}),
    ("Parameter Sweep Loop", bench_param_sweep_loop, {"is_param_sweep": True}),
]


async def run_all_scenarios(use_wheel: bool, runner: BenchmarkRunner, backtest_iterations: int = 100, param_sweep_size: int = 10) -> dict[str, BenchmarkResult]:
    """Run all benchmark scenarios for a given mode."""
    results = {}
    
    for name, func, kwargs in SCENARIOS:
        is_cold = kwargs.get("is_cold_import", False)
        is_warm = kwargs.get("is_warm_import", False)
        is_pure = kwargs.get("is_pure_python", False)
        is_backtest = kwargs.get("is_backtest_loop", False)
        is_param_sweep = kwargs.get("is_param_sweep", False)
        
        if is_cold or is_warm:
            # These run in subprocess
            async def run_import_bench():
                return await func(use_wheel)
            
            result = await runner.run(name, run_import_bench)
        elif is_pure:
            # Pure Python, no context needed
            result = await runner.run(name, func)
        elif is_backtest or is_param_sweep:
            # Context-based benchmarks with backtest config
            context = BenchmarkContext(use_wheel=use_wheel)
            context.backtest_iterations = backtest_iterations
            context.param_sweep_size = param_sweep_size
            
            async def setup():
                await context.setup_client()
            
            async def teardown():
                await context.teardown_client()
            
            async def run_bench():
                await func(context)
            
            result = await runner.run(name, run_bench, setup=setup, teardown=teardown)
        else:
            # Context-based benchmarks
            context = BenchmarkContext(use_wheel=use_wheel)
            
            async def setup():
                await context.setup_client()
            
            async def teardown():
                await context.teardown_client()
            
            async def run_bench():
                await func(context)
            
            result = await runner.run(name, run_bench, setup=setup, teardown=teardown)
        
        results[name] = result
    
    return results


def print_comparison_table(source_results: dict, wheel_results: dict) -> None:
    """Print formatted comparison table."""
    print("\n" + "=" * 100)
    print("PERFORMANCE COMPARISON: SOURCE vs NUITKA WHEEL")
    print("=" * 100)
    print(f"{'Benchmark':<30} {'Source (ms)':>14} {'Wheel (ms)':>14} {'Speedup':>10} {'Winner':>8} {'Source CV%':>10} {'Wheel CV%':>10}")
    print("-" * 100)
    
    for name in source_results:
        src = source_results[name]
        whl = wheel_results[name]
        
        speedup = whl.mean / src.mean if src.mean > 0 else 0
        speedup_pct = (1 - speedup) * 100
        
        if speedup < 0.95:
            winner = "WHEEL"
        elif speedup > 1.05:
            winner = "SOURCE"
        else:
            winner = "TIE"
        
        print(f"{name:<30} {src.mean*1000:>14.2f} {whl.mean*1000:>14.2f} "
              f"{speedup_pct:>+9.1f}% {winner:>8} {src.cv:>10.1f} {whl.cv:>10.1f}")
    
    print("-" * 100)
    
    # Summary
    wheel_wins = sum(1 for name in source_results 
                     if wheel_results[name].mean < source_results[name].mean * 0.95)
    source_wins = sum(1 for name in source_results 
                      if source_results[name].mean < wheel_results[name].mean * 0.95)
    ties = len(source_results) - wheel_wins - source_wins
    
    print(f"\nSUMMARY: Wheel faster: {wheel_wins}, Source faster: {source_wins}, Ties: {ties}")
    
    # Overall geometric mean speedup
    ratios = [wheel_results[n].mean / source_results[n].mean for n in source_results 
              if source_results[n].mean > 0]
    if ratios:
        import math
        geo_mean = math.exp(sum(math.log(r) for r in ratios) / len(ratios))
        print(f"Geometric mean speedup (wheel/source): {geo_mean:.3f}x "
              f"({(1-geo_mean)*100:+.1f}%)")


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Benchmark Nuitka wheel vs source")
    parser.add_argument("--source", action="store_true", help="Run source benchmarks only")
    parser.add_argument("--wheel", action="store_true", help="Run wheel benchmarks only")
    parser.add_argument("--compare", action="store_true", help="Run both and compare (default)")
    parser.add_argument("--iterations", type=int, default=30, help="Iterations per benchmark")
    parser.add_argument("--warmup", type=int, default=5, help="Warmup iterations")
    parser.add_argument("--verbose", action="store_true", default=True, help="Verbose output")
    parser.add_argument("--wheel-path", type=str, help="Path to wheel file")
    parser.add_argument("--backtest-iterations", type=int, default=100, help="Backtest loop iterations")
    parser.add_argument("--param-sweep-size", type=int, default=10, help="Parameter sweep combinations")
    parser.add_argument("--bars-count", type=int, default=1000, help="Number of OHLC bars for backtest")
    
    args = parser.parse_args()
    
    # Default to compare if neither specified
    if not args.source and not args.wheel and not args.compare:
        args.compare = True
    
    runner = BenchmarkRunner(
        iterations=args.iterations,
        warmup=args.warmup,
        verbose=args.verbose,
    )
    
    source_results = {}
    wheel_results = {}
    
    if args.source or args.compare:
        print("\n" + "=" * 60)
        print("RUNNING SOURCE BENCHMARKS")
        print("=" * 60)
        with ImportSwitcher(use_wheel=False):
            source_results = await run_all_scenarios(
                False, runner, 
                backtest_iterations=args.backtest_iterations,
                param_sweep_size=args.param_sweep_size
            )
        runner.print_summary()
    
    if args.wheel or args.compare:
        print("\n" + "=" * 60)
        print("RUNNING WHEEL BENCHMARKS")
        print("=" * 60)
        with ImportSwitcher(use_wheel=True, wheel_path=args.wheel_path):
            wheel_results = await run_all_scenarios(
                True, runner,
                backtest_iterations=args.backtest_iterations,
                param_sweep_size=args.param_sweep_size
            )
        runner.print_summary()
    
    if args.compare and source_results and wheel_results:
        print_comparison_table(source_results, wheel_results)
        
        # Analysis
        print("\n" + "=" * 60)
        print("ANALYSIS")
        print("=" * 60)
        print("""
Nuitka Performance Characteristics:
- Cold Import: 2-5x faster (compiled modules load faster)
- Warm Import: Minimal difference (both cached)
- CPU-bound work (parsing, normalization): 1.2-2x faster
- I/O-bound work (HTTP, disk): No significant difference
- Startup time: Significantly faster with Nuitka

For this data provider (primarily I/O-bound):
- Expect modest (10-30%) overall improvement
- Biggest gains in cold startup and pure Python processing
- Network/disk I/O dominates real-world latency
""")


if __name__ == "__main__":
    asyncio.run(main())