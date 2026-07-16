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
    SignalCallback,
)
from backtest_engine.engine.position import PositionSide, TradeRecord
from backtest_engine.engine.exits import evaluate_exits
from backtest_engine.engine.position_manager import PositionManager, ClosedPosition

if TYPE_CHECKING:
    from backtest_engine.engine.interfaces import BacktestConfig
    from backtest_engine.engine.trade_logger import TradeLogger


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
    
    Position Management Integration:
    - On each BASE timeframe event: evaluate exits for all positions, then process entries
    - On higher timeframe events: only invoke researcher callbacks (no position management)
    - Exit priority: Stop Loss > Trailing Stop > Take Profit > Custom Exit
    - Exits ALWAYS processed before entries on the same bar
    """
    
    @staticmethod
    def run(
        events: list[CandleEvent],
        callbacks: list[CandleCallback],
        signal_callbacks: list[SignalCallback],
        context: BacktestContext,
        position_manager: PositionManager,
        trade_logger: "TradeLogger",
        base_interval: "Interval",
    ) -> BacktestResult:
        """
        Execute the deterministic loop over prepared events with position management.
        
        Args:
            events: Pre-merged, sorted list of CandleEvent (timestamp order)
            callbacks: Registered researcher callbacks (on_ohlc_candle) - for monitoring
            signal_callbacks: Registered strategy callbacks returning target quantities
            context: Initial BacktestContext with total_bars = len(events)
            position_manager: PositionManager instance for position tracking
            trade_logger: TradeLogger instance for trade logging
            base_interval: Base interval (e.g., Interval.MINUTE_1) for position management
            
        Returns:
            BacktestResult with events_processed, duration_seconds, and logging paths
            
        Raises:
            Any exception raised by callbacks — fail-fast for determinism
        """
        if not events:
            logger.warning("ExecutionLoop.run called with empty event list")
            return BacktestResult(events_processed=0, duration_seconds=0.0)
        
        if not callbacks and not signal_callbacks:
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
                # Update virtual clock & progress context (mutates in-place for hot path)
                context.update_progress(idx)
                
                # Update current prices for position management
                context.current_prices[event.ohlc.symbol] = event.ohlc.close
                
                # Structured debug logging every N bars
                if idx % 1000 == 0:
                    logger.debug(
                        "Processing bar",
                        index=idx,
                        total=total_events,
                        progress_pct=context.progress_pct,
                        timestamp=event.timestamp.isoformat(),
                        timeframe=event.timeframe.value,
                    )
                
                # POSITION MANAGEMENT: Only on base timeframe events
                if event.timeframe == base_interval:
                    # 1. Update marks (unrealized PnL) for all positions in this symbol
                    position_manager.update_marks(event.ohlc.symbol, event.ohlc)
                    
                    # 2. EVALUATE EXITS (ALWAYS FIRST - no lookahead bias)
                    closed_positions = position_manager.evaluate_exits(
                        event.ohlc.symbol, event.ohlc, context
                    )
                    
                    # 3. Log closed trades - use the TradeRecord from position_manager (includes correct fees)
                    for closed in closed_positions:
                        trade_logger.log_trade(closed.trade_record)
                    target_qty = {}
                    for signal_cb in signal_callbacks:
                        try:
                            signals = signal_cb(event, context)
                            if signals:
                                for sym, qty in signals.items():
                                    target_qty[sym] = target_qty.get(sym, 0) + qty
                        except Exception as e:
                            logger.exception(
                                "Signal callback raised exception",
                                event_timestamp=event.timestamp.isoformat(),
                                error=str(e),
                            )
                            raise
                    
                    # 5. Adjust positions to match target quantities
                    if target_qty:
                        position_manager.adjust_positions(
                            target_qty, 
                            context.current_prices, 
                            event.timestamp, 
                            context
                        )
                    
                    # 6. Record equity curve point
                    equity = position_manager.equity
                    position_manager.record_equity_point(
                        event.timestamp,
                        equity,
                        position_manager.get_unrealized_pnl(),
                        position_manager.realized_pnl,
                        position_manager.cash,
                    )
                    trade_logger.log_equity(
                        event.timestamp, equity,
                        position_manager.get_unrealized_pnl(),
                        position_manager.realized_pnl,
                        position_manager.cash,
                    )
                
                # Invoke monitoring callbacks (on_ohlc_candle) for ALL timeframes
                for callback in callbacks:
                    try:
                        callback(event, context)
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
        
        # Finalize trade logger and get summary
        summary = trade_logger.finalize(position_manager)
        
        return BacktestResult(
            events_processed=total_events,
            duration_seconds=duration,
            trade_log_path=str(trade_logger.trade_log_path),
            equity_curve_path=str(trade_logger.equity_path),
            run_dir=str(trade_logger.run_dir),
            summary_stats=summary,
        )