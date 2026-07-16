#!/usr/bin/env python
"""
Comprehensive Backtest Engine Usage Examples

This file demonstrates the recommended usage patterns for the TradeQuantX Backtest Engine.
It covers the researcher-facing API, configuration, callbacks, position management,
and best practices.

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
from backtest_engine.engine.position import Position, PositionSide, PositionRequest, TradeRecord
from backtest_engine.engine.position_manager import PositionManager


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
    
    def _enter_long(self, price: float, timestamp: datetime) -> None:
        """Signal to enter long position."""
        self.position = 1
        self.entry_price = price
        self.trades.append({
            "action": "BUY",
            "price": price,
            "time": timestamp,
        })
        print(f"  [SIGNAL] BUY at {price:.2f} on {timestamp}")
    
    def _exit_long(self, price: float, timestamp: datetime) -> None:
        """Signal to exit long position."""
        if self.position > 0:
            pnl = (price - self.entry_price) * 100  # Assuming 100 shares
            self.trades.append({
                "action": "SELL",
                "price": price,
                "time": timestamp,
                "pnl": pnl,
            })
            print(f"  [SIGNAL] SELL at {price:.2f} on {timestamp} | PnL: {pnl:.2f}")
            self.position = 0


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
# SECTION 3: Position Management API (NEW - Recommended Patterns)
# =============================================================================

class PositionManagementStrategy:
    """
    Demonstrates the new Position Manager API for managing multiple positions.
    
    Key features:
    - Hedging mode: multiple independent positions per symbol (LONG + SHORT simultaneously)
    - Exit evaluation on every base-timeframe tick (SL, TS, TP, Custom)
    - Priority-based exit resolution: SL > TS > TP > Custom
    - Query API for researchers: get_positions(), get_unrealized_pnl(), get_realized_pnl()
    - Trade logging integration with unique run directories
    """
    
    def __init__(self):
        self.position_manager: Optional[PositionManager] = None
        self.trades_log = []
    
    def on_candle(self, event: CandleEvent, context) -> None:
        """Main callback - demonstrates position management patterns."""
        # Only process base timeframe for position management
        if event.timeframe != Interval.MINUTE_1:
            return
        
        # Access position manager from context (injected by engine)
        pm = context.position_manager
        if pm is None:
            return
        
        symbol = event.ohlc.symbol
        current_price = event.ohlc.close
        timestamp = event.timestamp
        
        # =====================================================================
        # PATTERN 1: Query current positions (Researcher API)
        # =====================================================================
        positions = pm.get_positions(symbol)
        print(f"\n  [POSITIONS] {symbol}: {len(positions)} active position(s)")
        
        for pos in positions:
            print(f"    {pos.side.value} | Qty: {pos.quantity} | "
                  f"Entry: {pos.entry_price:.2f} | "
                  f"Unrealized PnL: {pos.unrealized_pnl:.2f} | "
                  f"Entry: {pos.entry_condition}")
        
        # =====================================================================
        # PATTERN 2: Get portfolio metrics
        # =====================================================================
        unrealized = pm.get_unrealized_pnl(symbol)
        realized = pm.get_realized_pnl(symbol)
        equity = pm.get_equity()
        cash = pm.get_cash()
        
        print(f"  [METRICS] Unrealized: {unrealized:.2f} | "
              f"Realized: {realized:.2f} | "
              f"Equity: {equity:.2f} | Cash: {cash:.2f}")
        
        # =====================================================================
        # PATTERN 3: Open new position using PositionRequest (RECOMMENDED)
        # =====================================================================
        # Use PositionRequest dataclass instead of 11 positional parameters
        # This is the preferred API for opening positions
        
        # Example: Enter LONG on golden cross
        if self._should_enter_long(event):
            request = PositionRequest(
                symbol=symbol,
                side=PositionSide.LONG,
                quantity=100,
                entry_price=current_price,
                entry_time=timestamp,
                entry_condition="GOLDEN_CROSS_SMA_20_50",
                stop_loss=current_price * 0.98,           # 2% stop loss
                trailing_stop_pct=0.02,                    # 2% trailing stop
                take_profit=current_price * 1.05,          # 5% take profit
                # custom_exit_fn=my_custom_exit,           # Optional custom exit
            )
            position = pm.open_position_from_request(request)
            print(f"  [OPEN] LONG {position.quantity} {symbol} @ {position.entry_price:.2f} "
                  f"(SL: {position.stop_loss:.2f}, TS: {position.trailing_stop_pct*100:.1f}%, "
                  f"TP: {position.take_profit:.2f})")
        
        # Example: Enter SHORT on death cross
        elif self._should_enter_short(event):
            request = PositionRequest(
                symbol=symbol,
                side=PositionSide.SHORT,
                quantity=100,
                entry_price=current_price,
                entry_time=timestamp,
                entry_condition="DEATH_CROSS_SMA_20_50",
                stop_loss=current_price * 1.02,            # 2% stop loss (above entry for short)
                trailing_stop_pct=0.02,                    # 2% trailing stop
                take_profit=current_price * 0.95,          # 5% take profit (below entry for short)
            )
            position = pm.open_position_from_request(request)
            print(f"  [OPEN] SHORT {position.quantity} {symbol} @ {position.entry_price:.2f} "
                  f"(SL: {position.stop_loss:.2f}, TS: {position.trailing_stop_pct*100:.1f}%, "
                  f"TP: {position.take_profit:.2f})")
        
        # =====================================================================
        # PATTERN 4: Hedge - hold LONG and SHORT simultaneously
        # =====================================================================
        # The PositionManager supports hedging mode natively.
        # Multiple positions per symbol are stored independently.
        # 
        # Example: If we have a LONG and want to add a SHORT hedge:
        # if self._should_hedge(event):
        #     hedge_request = PositionRequest(
        #         symbol=symbol,
        #         side=PositionSide.SHORT,
        #         quantity=50,  # Partial hedge
        #         entry_price=current_price,
        #         entry_time=timestamp,
        #         entry_condition="HEDGE",
        #         stop_loss=current_price * 1.03,
        #     )
        #     pm.open_position_from_request(hedge_request)
        
        # =====================================================================
        # PATTERN 5: Access trade log and equity curve
        # =====================================================================
        trade_log = pm.get_trade_log()
        equity_curve = pm.get_equity_curve()
        
        if trade_log:
            last_trade = trade_log[-1]
            print(f"  [LAST TRADE] {last_trade.position_status} | "
                  f"PnL: {last_trade.pnl:.2f} | Fees: {last_trade.fees:.2f} | "
                  f"Exit: {last_trade.exit_condition}")
    
    def _should_enter_long(self, event: CandleEvent) -> bool:
        """Example entry logic - replace with your strategy."""
        ohlc = event.ohlc
        sma_20 = getattr(ohlc, 'sma_20', None)
        sma_50 = getattr(ohlc, 'sma_50', None)
        
        if sma_20 is None or sma_50 is None:
            return False
        
        # Simple golden cross detection (would need state tracking in real strategy)
        return False  # Placeholder
    
    def _should_enter_short(self, event: CandleEvent) -> bool:
        """Example entry logic - replace with your strategy."""
        return False  # Placeholder


# =============================================================================
# SECTION 4: Signal Callback Pattern (Target Quantity API)
# =============================================================================

def signal_callback_example(event: CandleEvent, context) -> dict[str, float]:
    """
    Signal callback returning target quantities per symbol.
    
    This is the RECOMMENDED pattern for systematic strategies:
    - Return dict of {symbol: target_quantity}
    - Positive = long target, Negative = short target, 0/absent = flat
    - Engine automatically adjusts positions to match targets
    - Exit-before-entry enforced on every base timeframe tick
    
    Called on BASE timeframe events only.
    """
    if event.timeframe != Interval.MINUTE_1:
        return {}
    
    pm = context.position_manager
    if pm is None:
        return {}
    
    symbol = event.ohlc.symbol
    current_price = event.ohlc.close
    
    # Example: Mean reversion signal
    # In practice, compute your signal here
    signal = 0  # -1, 0, or 1
    
    # Get current net position
    positions = pm.get_positions(symbol)
    current_net = sum(
        p.quantity if p.side == PositionSide.LONG else -p.quantity
        for p in positions
    )
    
    # Target: 100 shares long if signal=1, -100 if signal=-1, 0 if signal=0
    target_qty = signal * 100
    
    # Only return if target differs from current
    if target_qty != current_net:
        return {symbol: target_qty}
    
    return {}


# =============================================================================
# SECTION 5: Using BacktestEngine Class (Recommended for Complex Strategies)
# =============================================================================

async def run_with_engine_class() -> BacktestResult:
    """
    Run backtest using the BacktestEngine class directly.
    
    This is the RECOMMENDED approach for complex strategies because:
    - Full control over preparation and execution phases
    - Can register multiple callbacks (on_ohlc_candle + on_signal)
    - Access to prepared events and results
    - Supports async context manager for resource cleanup
    """
    config = create_basic_config()
    strategy = PositionManagementStrategy()
    
    # Create engine with fluent API
    engine = (
        BacktestEngine(config)
        .on_ohlc_candle(strategy.on_candle)      # Register monitoring callback
        .on_signal(signal_callback_example)      # Register signal callback (target qty)
    )
    
    # Prepare: fetch data, validate, normalize, resample, merge
    # This is async and does all the heavy lifting
    await engine.prepare()
    
    print(f"Prepared {len(engine.events)} events across "
          f"{len(config.timeframes)} timeframes")
    
    # Run: deterministic sync loop over prepared events
    result = engine.run()
    
    print(f"Completed: {result.events_processed} events in {result.duration_seconds:.3f}s")
    print(f"Run directory: {result.run_dir}")
    print(f"Trade log: {result.trade_log_path}")
    print(f"Equity curve: {result.equity_curve_path}")
    
    # Access position manager after run for final analysis
    pm = engine.position_manager
    if pm:
        print(f"\nFinal Equity: {pm.get_equity():.2f}")
        print(f"Total Trades: {pm.trade_count}")
        print(f"Realized PnL: {pm.get_realized_pnl():.2f}")
        print(f"Unrealized PnL: {pm.get_unrealized_pnl():.2f}")
    
    return result


async def run_with_custom_feeder() -> BacktestResult:
    """
    Run backtest with a custom data feeder.
    
    Useful for:
    - Testing with synthetic data
    - Using alternative data sources (MongoDB, TimescaleDB)
    - Replaying specific scenarios
    """
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
# SECTION 6: Using run_backtest() Convenience Function (Recommended for Scripts)
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
    print(f"Run directory: {result.run_dir}")
    return result


async def run_with_preprocessor() -> BacktestResult:
    """Run backtest with feature engineering preprocessor."""
    config = create_config_with_preprocessor()
    
    result = await run_backtest(config, simple_callback)
    return result


# =============================================================================
# SECTION 7: Advanced Patterns
# =============================================================================

async def run_multi_symbol_simulation() -> dict[str, BacktestResult]:
    """
    Simulate multi-symbol backtest by running sequentially.
    
    Note: True multi-symbol support requires future engine enhancements.
    This pattern runs independent backtests per symbol.
    Uses synthetic feeder to avoid data availability issues.
    """
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
        result = await run_backtest(config, simple_callback)
        results.append(({"fast": fast, "slow": slow}, result))
    
    return results


async def run_walk_forward_analysis() -> list[BacktestResult]:
    """
    Run walk-forward analysis (rolling window backtests).
    
    Splits data into training/testing windows for robust validation.
    Uses synthetic feeder to avoid market hours gap issues.
    """
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
        engine = BacktestEngine(config).on_ohlc_candle(simple_callback)
        await engine.prepare(feeder=SyntheticFeeder(base_price=2500.0))
        result = engine.run()
        results.append(result)
        
        current_start += timedelta(days=step_days)
    
    return results


# =============================================================================
# SECTION 8: Position Management Best Practices & Common Workflows
# =============================================================================

"""
POSITION MANAGEMENT BEST PRACTICES
==================================

1. USE PositionRequest FOR OPENING POSITIONS
   - Clean, typed API with validation
   - Avoids 11-parameter function calls
   - Self-documenting with named fields
   
   Example:
       request = PositionRequest(
           symbol="RELIANCE",
           side=PositionSide.LONG,
           quantity=100,
           entry_price=2500.0,
           entry_time=timestamp,
           entry_condition="MY_STRATEGY",
           stop_loss=2450.0,
           trailing_stop_pct=0.02,
           take_profit=2625.0,
       )
       position = pm.open_position_from_request(request)

2. QUERY API FOR RESEARCHERS (Read-Only)
   - get_positions(symbol=None) -> List[Position]
   - get_unrealized_pnl(symbol=None) -> float
   - get_realized_pnl(symbol=None) -> float
   - get_equity() -> float
   - get_cash() -> float
   - get_trade_log() -> List[TradeRecord]
   - get_equity_curve() -> List[EquityPoint]
   
   These are O(1) or O(n) where n = positions, not bars.

3. HEDGING MODE IS NATIVE
   - Multiple independent positions per symbol supported
   - LONG and SHORT can coexist
   - Each position has its own SL, TS, TP, custom exit
   - Net position = sum(LONG quantities) - sum(SHORT quantities)

4. EXIT PRIORITY IS ENFORCED AT ARCHITECTURE LEVEL
   On every base timeframe tick, exits are evaluated in order:
   1. Stop Loss (highest - capital protection)
   2. Trailing Stop (protects profits)
   3. Take Profit (locks gains)
   4. Custom Exit (lowest - researcher logic)
   
   This prevents SL/TP conflict in same bar.

5. GAP PROTECTION IS BUILT-IN
   - If price gaps beyond SL/TP/TS, exit at open price
   - No lookahead bias - uses OHLC of current bar
   - Applies to all exit types

6. SIGNAL CALLBACKS FOR SYSTEMATIC STRATEGIES
   - Return TargetQuantity dict {symbol: target_qty}
   - Positive = long, Negative = short, 0 = flat
   - Engine handles position adjustment automatically
   - Called AFTER exit evaluation, BEFORE equity recording

7. TRADE LOGGING IS AUTOMATIC
   - Unique run directories: {strategy}_{timestamp}_{uuid}/
   - Files: trade_log.csv, equity_curve.csv, summary.json
   - CSV schema matches user specification exactly
   - No manual logging needed

COMMON WORKFLOWS
================

WORKFLOW 1: Simple Signal-Based Strategy
----------------------------------------
    async def my_signal(event, context):
        # Compute signal
        signal = compute_my_signal(event.ohlc)
        target = 100 if signal > 0 else (-100 if signal < 0 else 0)
        return {event.ohlc.symbol: target}
    
    result = await run_backtest(config, on_signal=my_signal)

WORKFLOW 2: Manual Position Management
--------------------------------------
    def my_callback(event, context):
        pm = context.position_manager
        if event.timeframe != config.base_interval:
            return
        
        # Query positions
        positions = pm.get_positions(event.ohlc.symbol)
        
        # Open position via PositionRequest
        if should_enter(event):
            request = PositionRequest(...)
            pm.open_position_from_request(request)
        
        # Positions auto-managed (exits evaluated every base tick)

WORKFLOW 3: Hybrid (Signal + Manual)
------------------------------------
    engine = (BacktestEngine(config)
        .on_ohlc_candle(monitor_callback)      # For logging/analysis
        .on_signal(signal_callback))           # For position management
    
    await engine.prepare()
    result = engine.run()

WORKFLOW 4: Custom Exit Functions
---------------------------------
    def my_custom_exit(position: Position, context: BacktestContext) -> bool:
        # Access position state and context
        if position.unrealized_pnl > 1000:  # Profit target
            return True
        if context.progress_pct > 95:       # End of day exit
            return True
        return False
    
    request = PositionRequest(
        ...,
        custom_exit_fn=my_custom_exit,
    )

WORKFLOW 5: Post-Backtest Analysis
----------------------------------
    pm = engine.position_manager
    
    # Trade analysis
    trades = pm.get_trade_log()
    for trade in trades:
        print(f"{trade.position_status} | {trade.pnl:.2f} | {trade.exit_condition}")
    
    # Equity curve
    equity = pm.get_equity_curve()
    for ts, eq, unrl, rlz, cash in equity:
        print(f"{ts} | Equity: {eq:.2f}")
    
    # Summary stats
    print(f"Total trades: {pm.trade_count}")
    print(f"Win rate: {sum(1 for t in trades if t.pnl > 0) / len(trades) * 100:.1f}%")
    print(f"Total PnL: {pm.get_realized_pnl():.2f}")
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
    
    # Example 6: Parameter sweep
    print("\n6. PARAMETER SWEEP")
    print("-" * 40)
    await run_parameter_sweep()
    
    # Example 7: Walk-forward analysis
    print("\n7. WALK-FORWARD ANALYSIS")
    print("-" * 40)
    await run_walk_forward_analysis()
    
    print("\n" + "=" * 70)
    print("ALL EXAMPLES COMPLETED SUCCESSFULLY")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())