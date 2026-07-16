"""
Deterministic Execution Loop — the hot path of the backtest engine.

Single-threaded, synchronous, virtual-time-only dispatcher.
Walks a pre-merged, sorted list of CandleEvents and invokes callbacks.
No async, no wall-clock, no RNG — fully deterministic and Nuitka-friendly.
"""

import time
from typing import TYPE_CHECKING

from loguru import logger

from backtest_engine.engine.interfaces import (
    BacktestContext,
    BacktestResult,
    CandleCallback,
    CandleEvent,
)

if TYPE_CHECKING:
    from backtest_engine.engine.interfaces import BacktestConfig


class ExecutionLoop:
    """
    Deterministic execution loop for event-driven backtesting.
    
    Design principles:
    - Single-threaded, synchronous — no async overhead in hot path
    - Virtual clock only — event.timestamp drives time, not wall-clock
    - Pre-merged event list — total_bars known upfront for progress tracking
    - Fail-fast on callback errors — never swallow exceptions
    - Structured logging — INFO for lifecycle, DEBUG for per-bar, WARNING for anomalies
    - Nuitka-compatible — pure Python, no dynamic dispatch in loop
    
    The loop is a thin dispatcher; all heavy lifting (resampling, validation)
    happens in the DataIngestor BEFORE the loop starts.
    """
    
    @staticmethod
    def run(
        events: list[CandleEvent],
        callbacks: list[CandleCallback],
        context: BacktestContext,
    ) -> BacktestResult:
        """
        Execute the deterministic loop over prepared events.
        
        Args:
            events: Pre-merged, sorted list of CandleEvent (timestamp order)
            callbacks: Registered researcher callbacks (on_ohlc_candle)
            context: Initial BacktestContext with total_bars = len(events)
            
        Returns:
            BacktestResult with events_processed and duration_seconds
            
        Raises:
            Any exception raised by callbacks — fail-fast for determinism
        """
        if not events:
            logger.warning("ExecutionLoop.run called with empty event list")
            return BacktestResult(events_processed=0, duration_seconds=0.0)
        
        if not callbacks:
            logger.warning("ExecutionLoop.run called with no callbacks registered")
        
        total_events = len(events)
        logger.info(
            "Starting execution loop",
            total_events=total_events,
            symbol=context.symbol,
            timeframes=[tf.value for tf in context.timeframes],
        )
        
        start_time = time.perf_counter()
        
        try:
            for idx, event in enumerate(events):
                # Update virtual clock & progress context
                updated_context = context.with_progress(idx)
                
                # Structured debug logging every N bars
                if idx % 1000 == 0:
                    logger.debug(
                        "Processing bar",
                        index=idx,
                        total=total_events,
                        progress_pct=updated_context.progress_pct,
                        timestamp=event.timestamp.isoformat(),
                        timeframe=event.timeframe.value,
                    )
                
                # Invoke all registered callbacks with event and context separately
                for callback in callbacks:
                    try:
                        callback(event, updated_context)
                    except Exception as e:
                        logger.exception(
                            "Callback raised exception",
                            event_timestamp=event.timestamp.isoformat(),
                            event_timeframe=event.timeframe.value,
                            error=str(e),
                        )
                        raise  # Fail-fast — never swallow
        
        finally:
            duration = time.perf_counter() - start_time
            logger.info(
                "Execution loop completed",
                events_processed=total_events,
                duration_seconds=duration,
                bars_per_second=total_events / duration if duration > 0 else 0,
            )
        
        return BacktestResult(
            events_processed=total_events,
            duration_seconds=duration,
        )