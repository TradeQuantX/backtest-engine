#!/usr/bin/env python
"""
Comprehensive Backtest Engine Usage Examples

This file demonstrates the recommended usage patterns for the TradeQuantX Backtest Engine.
It covers the researcher-facing API, configuration, callbacks, and best practices.

Run with: uv run python examples/comprehensive_usage.py
"""

import asyncio
from dataclasses import replace
from datetime import datetime
from typing import Optional

from backtest_engine.data_provider.interfaces.models import Exchange, Interval, Segment
from backtest_engine.data_provider.utils import IST
from backtest_engine.engine import (
    BacktestConfig,
    BacktestEngine,
    BacktestResult,
    CandleEvent,
    run_backtest,
)


# =============================================================================
# SECTION 1: Basic Configuration
# =============================================================================

def create_basic_config() -> BacktestConfig:
    """
    Create a basic backtest configuration.
    
    BacktestConfig is a frozen dataclass - all parameters are immutable.
    Use dataclasses.replace() to create modified copies.
    """
    return BacktestConfig(
        symbol="RELIANCE",
        exchange=Exchange.NSE,
        segment=Segment.EQ,
        base_interval=Interval.MINUTE_1,      # Smallest timeframe (drives the loop)
        timeframes=[
            Interval.MINUTE_1,                # Base timeframe
            Interval.MINUTE_5,                # Resampled from base
            Interval.MINUTE_15,               # Resampled from base
            Interval.DAY,                     # Resampled from base
        ],
        from_date=datetime(2024, 1, 1, tzinfo=IST),
        to_date=datetime(2024, 1, 31, tzinfo=IST),
        strict_validation=True,               # Raise on data issues
        preprocessor=None,                    # Optional feature engineering hook
    )


def create_config_with_preprocessor() -> BacktestConfig:
    """
    Create config with a custom preprocessor for feature engineering.
    
    The preprocessor runs on the base-interval Polars DataFrame BEFORE resampling.
    Use for vectorized indicators (SMA, EMA, RSI, etc.) on the base series.
    
    NOTE: This example uses a synthetic feeder to demonstrate the preprocessor.
    With real data, ensure the preprocessor handles missing columns gracefully.
    """
    import polars as pl
    
    class IndicatorPreprocessor:
        """Adds technical indicators to the base series."""
        
        def process(self, df: pl.DataFrame) -> pl.DataFrame:
            # Add indicators only if we have enough data
            if len(df) < 50:
                return df
            
            return df.with_columns([
                # Simple Moving Averages
                pl.col("close").rolling_mean(20).alias("sma_20"),
                pl.col("close").rolling_mean(50).alias("sma_50"),
                # Exponential Moving Average
                pl.col("close").ewm_mean(span=20).alias("ema_20"),
                # RSI (14-period) - simplified
                pl.col("close").diff().clip(lower_bound=0).rolling_mean(14).alias("rsi_up"),
                pl.col("close").diff().clip(upper_bound=0).abs().rolling_mean(14).alias("rsi_down"),
            ]).with_columns(
                (100 - 100 / (1 + pl.col("rsi_up") / pl.col("rsi_down"))).alias("rsi_14")
            )
    
    base_config = create_basic_config()
    return replace(base_config, preprocessor=IndicatorPreprocessor())


# =============================================================================
# SECTION 2: Callback Patterns
# =============================================================================

class StrategyState:
    """
    Example strategy state container.
    
    Since callbacks are stateless functions, use a class or closure
    to maintain strategy state across bars.
    """
    def __init__(self):
        self.position = 0
        self.entry_price = 0.0
        self.trades = []
        self.sma_20_values = []
        self.sma_50_values = []
    
    def on_candle(self, event: CandleEvent, context) -> None:
        """Process a single closed candle."""
        ohlc = event.ohlc
        tf = event.timeframe
        
        # Only process base timeframe for signal generation
        if tf != Interval.MINUTE_1:
            return
        
        # Example: SMA crossover strategy (requires preprocessor)
        # Check if indicators are available (added by preprocessor)
        sma_20 = getattr(ohlc, 'sma_20', None)
        sma_50 = getattr(ohlc, 'sma_50', None)
        
        if sma_20 is not None and sma_50 is not None:
            self.sma_20_values.append(sma_20)
            self.sma_50_values.append(sma_50)
            
            if len(self.sma_20_values) >= 2:
                # Golden cross: SMA20 crosses above SMA50
                if (self.sma_20_values[-2] <= self.sma_50_values[-2] and 
                    self.sma_20_values[-1] > self.sma_50_values[-1]):
                    self._enter_long(ohlc.close, event.timestamp)
                
                # Death cross: SMA20 crosses below SMA50
                elif (self.sma_20_values[-2] >= self.sma_50_values[-2] and 
                      self.sma_20_values[-1] < self.sma_50_values[-1]):
                    self._exit_long(ohlc.close, event.timestamp)


def simple_callback(event: CandleEvent, context) -> None:
    """Simple callback for basic logging/monitoring."""
    ohlc = event.ohlc
    print(f"[{event.timestamp.strftime('%H:%M')}] {event.timeframe.value:>8} | "
          f"O={ohlc.open:>8.2f} H={ohlc.high:>8.2f} L={ohlc.low:>8.2f} "
          f"C={ohlc.close:>8.2f} V={ohlc.volume:>10}")


def multi_timeframe_callback(event: CandleEvent, context) -> None:
    """Callback that handles multiple timeframes differently."""
    if event.timeframe == Interval.MINUTE_1:
        # High-frequency logic (e.g., scalping signals)
        pass
    elif event.timeframe == Interval.MINUTE_5:
        # Medium-term logic (e.g., trend confirmation)
        pass
    elif event.timeframe == Interval.DAY:
        # Daily logic (e.g., position sizing, risk management)
        pass


# =============================================================================
# SECTION 3: Using BacktestEngine Class (Recommended for Complex Strategies)
# =============================================================================

async def run_with_engine_class() -> BacktestResult:
    """
    Run backtest using the BacktestEngine class directly.
    
    This is the RECOMMENDED approach for complex strategies because:
    - Full control over preparation and execution phases
    - Can register multiple callbacks
    - Access to prepared events and results
    - Supports async context manager for resource cleanup
    """
    config = create_basic_config()
    state = StrategyState()
    
    # Create engine with fluent API
    engine = (
        BacktestEngine(config)
        .on_ohlc_candle(state.on_candle)      # Register strategy callback
        .on_ohlc_candle(simple_callback)      # Can register multiple callbacks
    )
    
    # Prepare: fetch data, validate, normalize, resample, merge
    # This is async and does all the heavy lifting
    await engine.prepare()
    
    print(f"Prepared {len(engine.events)} events across "
          f"{len(config.timeframes)} timeframes")
    
    # Run: deterministic sync loop over prepared events
    result = engine.run()
    
    print(f"Completed: {result.events_processed} events in {result.duration_seconds:.3f}s")
    print(f"Strategy trades: {len(state.trades)}")
    
    return result


async def run_with_custom_feeder() -> BacktestResult:
    """
    Run backtest with a custom data feeder.
    
    Useful for:
    - Testing with synthetic data
    - Using alternative data sources (MongoDB, TimescaleDB)
    - Replaying specific scenarios
    """
    from backtest_engine.engine.feeder import DataFeeder
    from backtest_engine.data_provider.interfaces.models import NormalizedOHLC
    
    class SyntheticFeeder:
        """Generates synthetic OHLC data for testing."""
        
        def __init__(self, base_price: float = 100.0, volatility: float = 0.01):
            self.base_price = base_price
            self.volatility = volatility
        
        async def fetch_base_series(self, config: BacktestConfig) -> list[NormalizedOHLC]:
            import random
            from datetime import timedelta
            
            bars = []
            current_price = self.base_price
            current_time = config.from_date
            
            while current_time < config.to_date:
                # Random walk with valid OHLC
                change = random.gauss(0, self.volatility)
                current_price *= (1 + change)
                
                # Generate valid OHLC: high >= max(open, close), low <= min(open, close)
                open_price = current_price * (1 + random.gauss(0, 0.002))
                close = current_price
                high = max(open_price, close) * (1 + abs(random.gauss(0, 0.005)))
                low = min(open_price, close) * (1 - abs(random.gauss(0, 0.005)))
                
                bars.append(NormalizedOHLC(
                    symbol=config.symbol,
                    exchange=config.exchange,
                    segment=config.segment,
                    interval=config.base_interval,
                    timestamp=current_time,
                    open=open_price,
                    high=high,
                    low=low,
                    close=close,
                    volume=random.randint(10000, 100000),
                ))
                
                current_time += timedelta(minutes=1)
            
            return bars
    
    config = create_basic_config()
    engine = BacktestEngine(config).on_ohlc_candle(simple_callback)
    
    # Pass custom feeder to prepare()
    await engine.prepare(feeder=SyntheticFeeder(base_price=2500.0))
    return engine.run()


# =============================================================================
# SECTION 4: Using run_backtest() Convenience Function (Recommended for Scripts)
# =============================================================================

async def run_with_convenience_function() -> BacktestResult:
    """
    Run backtest using the run_backtest() convenience function.
    
    This is the RECOMMENDED approach for simple scripts and quick experiments:
    - Single function call
    - Automatic engine creation, preparation, and execution
    - Clean one-liner API
    """
    config = create_basic_config()
    
    # One-liner: config + callback = result
    result = await run_backtest(config, simple_callback)
    
    print(f"Completed: {result.events_processed} events in {result.duration_seconds:.3f}s")
    return result


async def run_with_preprocessor() -> BacktestResult:
    """Run backtest with feature engineering preprocessor."""
    config = create_config_with_preprocessor()
    
    result = await run_backtest(config, simple_callback)
    return result


# =============================================================================
# SECTION 5: Advanced Patterns
# =============================================================================

async def run_multi_symbol_simulation() -> dict[str, BacktestResult]:
    """
    Simulate multi-symbol backtest by running sequentially.
    
    Note: True multi-symbol support requires future engine enhancements.
    This pattern runs independent backtests per symbol.
    Uses synthetic feeder to avoid data availability issues.
    """
    from backtest_engine.engine.feeder import DataFeeder
    from backtest_engine.data_provider.interfaces.models import NormalizedOHLC
    import random
    from datetime import timedelta
    
    class SyntheticFeeder:
        """Generates synthetic OHLC data for testing."""
        
        def __init__(self, base_price: float = 100.0, volatility: float = 0.01):
            self.base_price = base_price
            self.volatility = volatility
        
        async def fetch_base_series(self, config: BacktestConfig) -> list[NormalizedOHLC]:
            bars = []
            current_price = self.base_price
            current_time = config.from_date
            
            while current_time < config.to_date:
                # Random walk with valid OHLC
                change = random.gauss(0, self.volatility)
                current_price *= (1 + change)
                
                open_price = current_price * (1 + random.gauss(0, 0.002))
                close = current_price
                high = max(open_price, close) * (1 + abs(random.gauss(0, 0.005)))
                low = min(open_price, close) * (1 - abs(random.gauss(0, 0.005)))
                
                bars.append(NormalizedOHLC(
                    symbol=config.symbol,
                    exchange=config.exchange,
                    segment=config.segment,
                    interval=config.base_interval,
                    timestamp=current_time,
                    open=open_price,
                    high=high,
                    low=low,
                    close=close,
                    volume=random.randint(10000, 100000),
                ))
                
                current_time += timedelta(minutes=1)
            
            return bars
    
    symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK"]
    results = {}
    
    for symbol in symbols:
        config = replace(
            create_basic_config(),
            symbol=symbol,
        )
        
        print(f"\nRunning backtest for {symbol}...")
        engine = BacktestEngine(config).on_ohlc_candle(simple_callback)
        await engine.prepare(feeder=SyntheticFeeder(base_price=2500.0))
        result = engine.run()
        results[symbol] = result
    
    return results


async def run_parameter_sweep() -> list[tuple[dict, BacktestResult]]:
    """
    Run parameter sweep (e.g., different SMA periods).
    
    Useful for strategy optimization and robustness testing.
    """
    from dataclasses import replace
    
    sma_periods = [(10, 30), (20, 50), (50, 200)]
    results = []
    
    for fast, slow in sma_periods:
        config = replace(
            create_basic_config(),
            # In real usage, pass parameters via preprocessor or config
        )
        
        print(f"\nTesting SMA({fast}, {slow})...")
        result = await run_backtest(config, on_ohlc_candle=simple_callback)
        results.append(({"fast": fast, "slow": slow}, result))
    
    return results


async def run_walk_forward_analysis() -> list[BacktestResult]:
    """
    Run walk-forward analysis (rolling window backtests).
    
    Splits data into training/testing windows for robust validation.
    """
    from datetime import timedelta
    
    window_days = 30
    step_days = 15
    start = datetime(2024, 1, 1, tzinfo=IST)
    end = datetime(2024, 6, 30, tzinfo=IST)
    
    results = []
    current_start = start
    
    while current_start + timedelta(days=window_days) <= end:
        window_end = current_start + timedelta(days=window_days)
        
        config = replace(
            create_basic_config(),
            from_date=current_start,
            to_date=window_end,
        )
        
        print(f"\nWindow: {current_start.date()} to {window_end.date()}")
        result = await run_backtest(config, on_ohlc_candle=simple_callback)
        results.append(result)
        
        current_start += timedelta(days=step_days)
    
    return results


# =============================================================================
# SECTION 6: Best Practices Summary
# =============================================================================

"""
BEST PRACTICES FOR RESEARCHERS
==============================

1. USE BacktestConfig FOR ALL PARAMETERS
   - Single frozen dataclass, type-safe, serializable
   - Use dataclasses.replace() for modifications
   - Never pass parameters as individual function arguments

2. PREFER run_backtest() FOR SIMPLE SCRIPTS
   - One-liner: await run_backtest(config, callback)
   - Automatic resource management
   - Clean and readable

3. USE BacktestEngine CLASS FOR COMPLEX STRATEGIES
   - Multiple callbacks: engine.on_ohlc_candle(cb1).on_ohlc_candle(cb2)
   - Access to prepared events: engine.events
   - Custom feeders: await engine.prepare(feeder=custom_feeder)
   - Context manager: async with BacktestEngine(config) as engine:

4. CALLBACK DESIGN
   - Keep callbacks fast (no I/O, no blocking)
   - Use closures or classes for state management
   - Handle multiple timeframes via event.timeframe
   - Access progress via event.context.progress_pct

5. DATA HANDLING
   - Base interval drives the loop (smallest timeframe)
   - Higher timeframes are resampled from base (no lookahead)
   - Preprocessor runs on base series BEFORE resampling
   - All timestamps are IST (Asia/Kolkata)

6. RESOURCE MANAGEMENT
   - Use async context manager or explicit await engine.close()
   - Feeder connections are closed automatically
   - No manual cleanup needed in most cases

7. TESTING
   - Use SyntheticFeeder for unit tests
   - Mock DataProviderClient for integration tests
   - Determinism: same input → identical callback sequence
"""


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

async def main():
    """Run all examples sequentially."""
    print("=" * 70)
    print("TRADEQUANTX BACKTEST ENGINE - COMPREHENSIVE USAGE EXAMPLES")
    print("=" * 70)
    
    # Example 1: Basic usage with convenience function
    print("\n1. BASIC USAGE (run_backtest)")
    print("-" * 40)
    await run_with_convenience_function()
    
    # Example 2: Using BacktestEngine class
    print("\n2. BACKTESTENGINE CLASS")
    print("-" * 40)
    await run_with_engine_class()
    
    # Example 3: With preprocessor
    print("\n3. WITH PREPROCESSOR (Feature Engineering)")
    print("-" * 40)
    await run_with_preprocessor()
    
    # Example 4: Custom feeder (synthetic data)
    print("\n4. CUSTOM FEEDER (Synthetic Data)")
    print("-" * 40)
    await run_with_custom_feeder()
    
    # Example 5: Multi-symbol (sequential)
    print("\n5. MULTI-SYMBOL SIMULATION")
    print("-" * 40)
    await run_multi_symbol_simulation()
    
    print("\n" + "=" * 70)
    print("ALL EXAMPLES COMPLETED SUCCESSFULLY")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())