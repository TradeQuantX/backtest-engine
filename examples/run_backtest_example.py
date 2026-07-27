#!/usr/bin/env python
"""
Minimal backtest example — prints candle counts per timeframe.

Run with: uv run python examples/run_backtest_example.py
"""

import asyncio
from datetime import datetime

from backtest_engine.config import load_backtest_config
from backtest_engine.shared.types import Exchange, Interval, Segment
from backtest_engine.data_provider.utils import IST
from backtest_engine.engine import BacktestConfig, run_backtest


async def main():
    """Run a simple backtest and count candles per timeframe."""
    counts: dict[str, int] = {}
    
    def on_candle(event, context):
        tf = event.timeframe.value
        counts[tf] = counts.get(tf, 0) + 1
        
        # Print first few candles for verification
        if counts[tf] <= 3:
            ohlc = event.ohlc
            print(
                f"  [{event.timestamp.strftime('%H:%M')}] "
                f"{tf:>8} | O={ohlc.open:>8.2f} H={ohlc.high:>8.2f} "
                f"L={ohlc.low:>8.2f} C={ohlc.close:>8.2f} V={ohlc.volume:>10}"
            )
    
    # Load config from config.yaml/.secrets.yaml
    config = load_backtest_config()
    
    print("Running backtest...")
    print(f"Symbol: {config.symbol} | Exchange: {config.exchange.value} | Segment: {config.segment.value}")
    print(f"Base interval: {config.base_interval.value}")
    print(f"Timeframes: {[tf.value for tf in config.timeframes]}")
    print(f"Date range: {config.from_date.date()} to {config.to_date.date()}")
    print()
    
    result = await run_backtest(config, on_candle)
    
    print()
    print("=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print(f"Total events processed: {result.events_processed}")
    print(f"Duration: {result.duration_seconds:.3f}s")
    print(f"Throughput: {result.events_processed / result.duration_seconds:,.0f} bars/sec")
    print()
    print("Candle counts per timeframe:")
    for tf, count in sorted(counts.items()):
        print(f"  {tf:>10}: {count:>6}")
    
    # Verify 5min count ≈ floor(1min_count / 5) for contiguous data
    if "1minute" in counts and "5minute" in counts:
        expected_5min = counts["1minute"] // 5
        actual_5min = counts["5minute"]
        print()
        print(f"Verification: 5min count ({actual_5min}) ≈ 1min count // 5 ({expected_5min})")
        if abs(actual_5min - expected_5min) <= 1:
            print("  ✓ PASS: Multi-timeframe alignment correct")
        else:
            print(f"  ✗ FAIL: Difference = {abs(actual_5min - expected_5min)}")


if __name__ == "__main__":
    asyncio.run(main())