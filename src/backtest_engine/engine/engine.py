"""
BacktestEngine — single researcher-facing orchestrator class.

Hides feeder, ingestor, and loop internals. Provides fluent API:
    engine = BacktestEngine(config).on_ohlc_candle(callback)
    await engine.prepare()
    result = engine.run()
"""

from typing import TYPE_CHECKING

from backtest_engine.engine.defaults import (
    create_default_feeder,
    create_default_position_manager,
    create_default_trade_logger,
)
from backtest_engine.engine.ingestor import DataIngestor
from backtest_engine.engine.interfaces import (
    BacktestConfig,
    BacktestContext,
    BacktestResult,
    CandleCallback,
    CandleEvent,
    DataFeeder,
    SignalCallback,
    TargetQuantity,
)
from backtest_engine.engine.loop import ExecutionLoop
from backtest_engine.engine.position_manager import PositionManager
from backtest_engine.engine.trade_logger import TradeLogger

if TYPE_CHECKING:
    from backtest_engine.engine.ingestor import DataIngestor


class BacktestEngine:
    """
    Single entry point for researchers to run backtests.
    
    Encapsulates the full pipeline:
    - DataFeeder (async, cached, chunked, retried)
    - DataIngestor (validate, normalize, preprocess, resample, merge)
    - ExecutionLoop (deterministic, sync, virtual-time)
    - PositionManager (hedging positions, exit evaluation, query API)
    - TradeLogger (unique run directories, CSV trade logs, equity curve)
    
    Usage:
        config = BacktestConfig(...)
        engine = BacktestEngine(config).on_ohlc_candle(my_callback)
        await engine.prepare()
        result = engine.run()
    
    Or use the convenience function:
        result = await run_backtest(config, my_callback)
    """
    
    def __init__(self, config: BacktestConfig):
        """
        Initialize the engine with a configuration.
        
        Args:
            config: BacktestConfig with all parameters (symbol, dates, timeframes, etc.)
        """
        self._config = config
        self._callbacks: list[CandleCallback] = []
        self._signal_callbacks: list[SignalCallback] = []
        self._feeder: DataFeeder | None = None
        self._ingestor: DataIngestor | None = None
        self._events: list[CandleEvent] | None = None
        self._result: BacktestResult | None = None
        self._prepared = False
        
        # Position management
        self._position_manager: PositionManager | None = None
        self._trade_logger: TradeLogger | None = None
    
    def on_ohlc_candle(self, callback: CandleCallback) -> "BacktestEngine":
        """
        Register a callback for closed candle events.
        
        Fluent API — returns self for chaining.
        Multiple callbacks can be registered; all will be invoked per event.
        
        Args:
            callback: Function accepting CandleEvent and BacktestContext
            
        Returns:
            Self for method chaining
        """
        self._callbacks.append(callback)
        return self
    
    def on_signal(self, callback: SignalCallback) -> "BacktestEngine":
        """
        Register a signal callback that returns target quantities.
        
        Signal callbacks are invoked on BASE timeframe events and return
        a TargetQuantity dict of {symbol: target_quantity} where:
        - positive = long target
        - negative = short target
        - 0/absent = flat
        
        Fluent API — returns self for chaining.
        
        Args:
            callback: Function accepting CandleEvent and BacktestContext, returning TargetQuantity
            
        Returns:
            Self for method chaining
        """
        self._signal_callbacks.append(callback)
        return self
    
    async def prepare(
        self,
        feeder: DataFeeder | None = None,
        ingestor: "DataIngestor | None" = None,
        position_manager: PositionManager | None = None,
        trade_logger: TradeLogger | None = None,
    ) -> "BacktestEngine":
        """
        Async preparation phase: fetch, validate, normalize, preprocess, resample, merge.
        
        This is where all I/O and heavy computation happens. The actual run()
        is a fast, deterministic sync loop over the prepared events.
        
        Args:
            feeder: Optional custom DataFeeder (default: ParquetDataFeeder via factory)
            ingestor: Optional custom DataIngestor (default: new instance)
            position_manager: Optional custom PositionManager (default: factory)
            trade_logger: Optional custom TradeLogger (default: factory)
            
        Returns:
            Self for chaining
            
        Raises:
            DataNotFoundError: No data available
            ValidationError: Data validation failed
            InsufficientDataError: Not enough data for resampling
        """
        self._feeder = feeder or create_default_feeder()
        self._ingestor = ingestor or DataIngestor()
        
        # Full ingestion pipeline
        self._events = await self._ingestor.ingest(self._feeder, self._config)
        self._prepared = True
        
        # Initialize position manager and trade logger
        self._position_manager = position_manager or create_default_position_manager()
        self._trade_logger = trade_logger or create_default_trade_logger(
            base_dir="backtest_results",
            strategy_name=self._config.symbol,
            initial_cash=self._position_manager.initial_cash
        )
        
        return self
    
    def run(self) -> BacktestResult:
        """
        Execute the deterministic sync loop over prepared events with position management.
        
        Must call prepare() first. This method is synchronous, single-threaded,
        and fully deterministic — same input always produces same callback sequence.
        
        Returns:
            BacktestResult with events_processed, duration_seconds, and trade logging paths
            
        Raises:
            RuntimeError: If prepare() not called first
            Any exception from callbacks (fail-fast)
        """
        if self._events is None:
            raise RuntimeError("Must call prepare() before run()")
        
        if not self._callbacks:
            from loguru import logger
            logger.warning("No callbacks registered — running with no-op")
        
        # Build initial context with total_bars known upfront
        context = BacktestContext(
            symbol=self._config.symbol,
            exchange=self._config.exchange,
            segment=self._config.segment,
            base_interval=self._config.base_interval,
            timeframes=self._config.timeframes,
            total_bars=len(self._events),
            current_bar_index=0,
            progress_pct=0.0,
            position_manager=self._position_manager,
            trade_logger=self._trade_logger,
            current_prices={},
        )
        
        # Execute deterministic loop with position management
        self._result = ExecutionLoop.run(
            self._events, 
            self._callbacks, 
            self._signal_callbacks,
            context,
            self._position_manager,
            self._trade_logger,
            self._config.base_interval,
        )
        
        return self._result
    
    @property
    def result(self) -> BacktestResult | None:
        """Get the result of the last run(), or None if not run yet."""
        return self._result
    
    @property
    def config(self) -> BacktestConfig:
        """Get the backtest configuration."""
        return self._config
    
    @property
    def events(self) -> list[CandleEvent] | None:
        """Get the prepared events (after prepare(), before/after run())."""
        return self._events
    
    @property
    def position_manager(self) -> PositionManager | None:
        """Get the position manager (after prepare())."""
        return self._position_manager
    
    @property
    def trade_logger(self) -> TradeLogger | None:
        """Get the trade logger (after prepare())."""
        return self._trade_logger
    
    async def close(self) -> None:
        """Clean up resources (close feeder connections)."""
        if self._feeder and hasattr(self._feeder, "close"):
            await self._feeder.close()
    
    async def __aenter__(self) -> "BacktestEngine":
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()


# =============================================================================
# Convenience Function
# =============================================================================

async def run_backtest(
    config: BacktestConfig,
    *callbacks: CandleCallback,
    feeder: DataFeeder | None = None,
    position_manager: PositionManager | None = None,
    trade_logger: TradeLogger | None = None,
) -> BacktestResult:
    """
    One-liner convenience function for researchers.
    
    Combines engine creation, callback registration, preparation, and execution.
    
    Args:
        config: BacktestConfig with all parameters
        *callbacks: One or more callback functions for closed candle events
        feeder: Optional custom DataFeeder
        position_manager: Optional custom PositionManager
        trade_logger: Optional custom TradeLogger
        
    Returns:
        BacktestResult after execution completes
        
    Example:
        config = BacktestConfig(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            segment=Segment.EQ,
            base_interval=Interval.MINUTE_1,
            timeframes=[Interval.MINUTE_1, Interval.MINUTE_5, Interval.DAY],
            from_date=datetime(2024, 1, 1, tzinfo=IST),
            to_date=datetime(2024, 1, 31, tzinfo=IST),
        )
        
        def on_candle(event, context):
            print(f"{event.timestamp} {event.timeframe.value} "
                  f"O={event.ohlc.open} H={event.ohlc.high} "
                  f"L={event.ohlc.low} C={event.ohlc.close}")
        
        result = await run_backtest(config, on_candle)
        print(f"Processed {result.events_processed} events in {result.duration_seconds:.2f}s")
    """
    engine = BacktestEngine(config)
    for cb in callbacks:
        engine.on_ohlc_candle(cb)
    await engine.prepare(feeder)
    return engine.run()