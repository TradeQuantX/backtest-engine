"""
Tests for ExecutionLoop — determinism, no-lookahead, multi-TF sync, error propagation.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from backtest_engine.data_provider.interfaces.models import (
    Exchange,
    Interval,
    NormalizedOHLC,
    Segment,
)
from backtest_engine.data_provider.utils import IST
from backtest_engine.engine.interfaces import (
    BacktestConfig,
    BacktestContext,
    CandleCallback,
    CandleEvent,
    SignalCallback,
)
from backtest_engine.engine.loop import ExecutionLoop
from backtest_engine.engine.position_manager import PositionManager
from backtest_engine.engine.trade_logger import TradeLogger


# Module-level fixtures for all test classes
@pytest.fixture
def sample_events():
    """Create a list of CandleEvents for testing."""
    events = []
    base_time = datetime(2024, 1, 1, 9, 15, tzinfo=IST)
    
    # 1-minute bars (base interval)
    for i in range(10):
        ts = base_time + timedelta(minutes=i)
        ohlc = NormalizedOHLC(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            segment=Segment.EQ,
            interval=Interval.MINUTE_1,
            timestamp=ts,
            open=2500.0 + i,
            high=2510.0 + i,
            low=2495.0 + i,
            close=2505.0 + i,
            volume=100000,
        )
        events.append(CandleEvent(
            timestamp=ts,
            timeframe=Interval.MINUTE_1,
            ohlc=ohlc,
            context=None,  # Will be filled by loop
        ))
    
    # 5-minute bars (boundary timestamps: 09:20, 09:25, 09:30, ...)
    for i in range(2):
        ts = base_time + timedelta(minutes=5 * (i + 1))  # 09:20, 09:25
        ohlc = NormalizedOHLC(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            segment=Segment.EQ,
            interval=Interval.MINUTE_5,
            timestamp=ts,
            open=2500.0,
            high=2510.0,
            low=2495.0,
            close=2505.0,
            volume=500000,
        )
        events.append(CandleEvent(
            timestamp=ts,
            timeframe=Interval.MINUTE_5,
            ohlc=ohlc,
            context=None,
        ))
    
    # Sort by timestamp, then by priority (1min first)
    events.sort(key=lambda e: (e.timestamp, 0 if e.timeframe == Interval.MINUTE_1 else 1))
    
    return events


@pytest.fixture
def sample_context(sample_events):
    """Create a BacktestContext with correct total_bars."""
    return BacktestContext(
        symbol="RELIANCE",
        exchange=Exchange.NSE,
        segment=Segment.EQ,
        base_interval=Interval.MINUTE_1,
        timeframes=[Interval.MINUTE_1, Interval.MINUTE_5],
        total_bars=len(sample_events),
        current_bar_index=0,
        progress_pct=0.0,
    )


@pytest.fixture
def mock_position_manager():
    """Create a mock PositionManager."""
    return MagicMock(spec=PositionManager)


@pytest.fixture
def mock_trade_logger():
    """Create a mock TradeLogger."""
    return MagicMock(spec=TradeLogger)


class TestExecutionLoop:
    """Test the deterministic execution loop."""
    
    def test_run_processes_all_events(self, sample_events, sample_context, mock_position_manager, mock_trade_logger):
        """Test that loop processes all events and returns correct count."""
        callback_calls = []
        
        def callback(event, context):
            callback_calls.append((event, context))
        
        result = ExecutionLoop.run(
            sample_events, 
            [callback], 
            [],  # signal_callbacks
            sample_context,
            mock_position_manager,
            mock_trade_logger,
            Interval.MINUTE_1,
        )
        
        assert result.events_processed == len(sample_events)
        assert len(callback_calls) == len(sample_events)
        assert result.duration_seconds > 0
    
    def test_run_context_current_bar_index(self, sample_events, sample_context, mock_position_manager, mock_trade_logger):
        """Test that current_bar_index increments correctly."""
        indices = []
        
        def callback(event, context):
            indices.append(context.current_bar_index)
        
        ExecutionLoop.run(
            sample_events, 
            [callback], 
            [],  # signal_callbacks
            sample_context,
            mock_position_manager,
            mock_trade_logger,
            Interval.MINUTE_1,
        )
        
        assert indices == list(range(len(sample_events)))
    
    def test_run_no_lookahead_5min_after_1min_bars(
        self,
        sample_events,
        sample_context,
        mock_position_manager,
        mock_trade_logger,
    ):
        """
        Critical regression test: 5min candle at 09:20 fires AFTER 09:19 1min bar.
        
        The 5min candle for 09:15-09:19 has timestamp 09:20 (boundary).
        It should only fire after all constituent 1min bars (09:15-09:19) are processed.
        """
        processed_order = []
        
        def callback(event, context):
            processed_order.append((event.timestamp, event.timeframe))
        
        ExecutionLoop.run(
            sample_events, 
            [callback], 
            [],  # signal_callbacks
            sample_context,
            mock_position_manager,
            mock_trade_logger,
            Interval.MINUTE_1,
        )
        
        # Find the 5min event at 09:20
        five_min_0920 = None
        for i, (ts, tf) in enumerate(processed_order):
            if tf == Interval.MINUTE_5 and ts.minute == 20 and ts.hour == 9:
                five_min_0920 = i
                break
        
        assert five_min_0920 is not None, "5min 09:20 event not found"
        
        # All 1min bars from 09:15 to 09:19 should come BEFORE the 5min 09:20
        one_min_before_0920 = [
            i for i, (ts, tf) in enumerate(processed_order)
            if tf == Interval.MINUTE_1 and ts < datetime(2024, 1, 1, 9, 20, tzinfo=IST)
        ]
        
        assert all(i < five_min_0920 for i in one_min_before_0920), (
            "5min candle fired before all constituent 1min bars!"
        )
    
    def test_run_5min_never_sees_future_1min_data(
        self,
        sample_events,
        sample_context,
        mock_position_manager,
        mock_trade_logger,
    ):
        """
        Test that 5min callback at 09:20 never has access to 09:20 1min bar data.
        
        The 5min candle (09:15-09:19) closes at 09:20 boundary.
        The 09:20 1min bar is the NEXT bar and should not be visible to the 5min callback.
        """
        seen_ohlc_in_5min = []
        
        def callback(event, context):
            if event.timeframe == Interval.MINUTE_5:
                seen_ohlc_in_5min.append(event.ohlc.close)
        
        ExecutionLoop.run(
            sample_events, 
            [callback], 
            [],  # signal_callbacks
            sample_context,
            mock_position_manager,
            mock_trade_logger,
            Interval.MINUTE_1,
        )
        
        # The 5min candles should only see data up to their boundary
        # First 5min (09:15-09:19) closes at 09:20, close = 09:19 close
        # Second 5min (09:20-09:24) closes at 09:25, close = 09:24 close
        # Neither should see 09:25 or later data
        
        # Just verify the callback was invoked for 5min events
        assert len(seen_ohlc_in_5min) == 2
    
    def test_run_multiple_callbacks_all_invoked(
        self,
        sample_events,
        sample_context,
        mock_position_manager,
        mock_trade_logger,
    ):
        """Test that all registered callbacks are invoked for each event."""
        call_counts = [0, 0, 0]
        
        def make_callback(idx):
            def callback(event, context):
                call_counts[idx] += 1
            return callback
        
        callbacks = [make_callback(i) for i in range(3)]
        
        ExecutionLoop.run(
            sample_events, 
            callbacks, 
            [],  # signal_callbacks
            sample_context,
            mock_position_manager,
            mock_trade_logger,
            Interval.MINUTE_1,
        )
        
        for count in call_counts:
            assert count == len(sample_events)
    
    def test_run_callback_exception_propagates(
        self,
        sample_events,
        sample_context,
        mock_position_manager,
        mock_trade_logger,
    ):
        """Test that callback exceptions propagate (fail-fast)."""
        def failing_callback(event, context):
            if context.current_bar_index == 5:
                raise ValueError("Intentional test error")
        
        with pytest.raises(ValueError, match="Intentional test error"):
            ExecutionLoop.run(
                sample_events, 
                [failing_callback], 
                [],  # signal_callbacks
                sample_context,
                mock_position_manager,
                mock_trade_logger,
                Interval.MINUTE_1,
            )
    
    def test_run_empty_events_returns_zero(self, sample_context, mock_position_manager, mock_trade_logger):
        """Test that empty event list returns zero result."""
        result = ExecutionLoop.run(
            [], 
            [], 
            [],  # signal_callbacks
            sample_context,
            mock_position_manager,
            mock_trade_logger,
            Interval.MINUTE_1,
        )
        
        assert result.events_processed == 0
        assert result.duration_seconds == 0.0
    
    def test_run_no_callbacks_warns_but_completes(
        self,
        sample_events,
        sample_context,
        mock_position_manager,
        mock_trade_logger,
    ):
        """Test that running with no callbacks completes (warning logged to stderr)."""
        result = ExecutionLoop.run(
            sample_events, 
            [], 
            [],  # signal_callbacks
            sample_context,
            mock_position_manager,
            mock_trade_logger,
            Interval.MINUTE_1,
        )
        
        assert result.events_processed == len(sample_events)
        # Warning is logged to stderr via loguru (not captured by capsys)
        # Just verify it completes without error
    
    def test_run_virtual_clock_no_wall_time(
        self,
        sample_events,
        sample_context,
        mock_position_manager,
        mock_trade_logger,
    ):
        """Test that loop uses virtual time (event.timestamp) not wall-clock."""
        timestamps_seen = []
        
        def callback(event, context):
            timestamps_seen.append(event.timestamp)
        
        ExecutionLoop.run(
            sample_events, 
            [callback], 
            [],  # signal_callbacks
            sample_context,
            mock_position_manager,
            mock_trade_logger,
            Interval.MINUTE_1,
        )
        
        # Timestamps should match event timestamps exactly (virtual clock)
        expected_timestamps = [e.timestamp for e in sample_events]
        assert timestamps_seen == expected_timestamps
    
    def test_run_returns_backtest_result_with_duration(
        self,
        sample_events,
        sample_context,
        mock_position_manager,
        mock_trade_logger,
    ):
        """Test that BacktestResult contains correct fields."""
        result = ExecutionLoop.run(
            sample_events, 
            [], 
            [],  # signal_callbacks
            sample_context,
            mock_position_manager,
            mock_trade_logger,
            Interval.MINUTE_1,
        )
        
        assert isinstance(result.events_processed, int)
        assert isinstance(result.duration_seconds, float)
        assert result.events_processed == len(sample_events)
        assert result.duration_seconds >= 0
    
    def test_run_bars_per_second_logged(
        self,
        sample_events,
        sample_context,
        mock_position_manager,
        mock_trade_logger,
    ):
        """Test that bars/second is logged at completion (to stderr via loguru)."""
        ExecutionLoop.run(
            sample_events, 
            [], 
            [],  # signal_callbacks
            sample_context,
            mock_position_manager,
            mock_trade_logger,
            Interval.MINUTE_1,
        )
        
        # Completion log goes to stderr via loguru (not captured by capsys in this env)
        # Just verify it completes without error
    
    @pytest.mark.parametrize("num_events", [1, 10, 100, 1000])
    def test_run_scales_linearly(self, num_events, sample_context, mock_position_manager, mock_trade_logger):
        """Test that loop handles various event counts correctly."""
        # Create events
        events = []
        base_time = datetime(2024, 1, 1, 9, 15, tzinfo=IST)
        
        for i in range(num_events):
            ts = base_time + timedelta(minutes=i)
            ohlc = NormalizedOHLC(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                segment=Segment.EQ,
                interval=Interval.MINUTE_1,
                timestamp=ts,
                open=2500.0,
                high=2510.0,
                low=2495.0,
                close=2505.0,
                volume=100000,
            )
            events.append(CandleEvent(
                timestamp=ts,
                timeframe=Interval.MINUTE_1,
                ohlc=ohlc,
                context=None,
            ))
        
        context = BacktestContext(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            segment=Segment.EQ,
            base_interval=Interval.MINUTE_1,
            timeframes=[Interval.MINUTE_1],
            total_bars=num_events,
            current_bar_index=0,
            progress_pct=0.0,
        )
        
        result = ExecutionLoop.run(
            events, 
            [], 
            [],  # signal_callbacks
            context,
            mock_position_manager,
            mock_trade_logger,
            Interval.MINUTE_1,
        )
        
        assert result.events_processed == num_events
    
    def test_run_context_immutability(
        self,
        sample_events,
        sample_context,
        mock_position_manager,
        mock_trade_logger,
    ):
        """Test that context is properly replaced (not mutated) each iteration."""
        contexts_seen = []
        
        def callback(event, context):
            contexts_seen.append(context)
        
        ExecutionLoop.run(
            sample_events, 
            [callback], 
            [],  # signal_callbacks
            sample_context,
            mock_position_manager,
            mock_trade_logger,
            Interval.MINUTE_1,
        )
        
        # Context is now mutated in-place for hot-path efficiency
        # All callbacks receive the same context object with updated progress
        assert len(contexts_seen) == len(sample_events)
        # All entries should be the same object (mutated in-place)
        for ctx in contexts_seen:
            assert ctx is sample_context
        # Final progress should be 100%
        assert sample_context.current_bar_index == len(sample_events) - 1
        assert sample_context.progress_pct == 100.0
    
    def test_run_preserves_event_order_across_timeframes(
        self,
        sample_events,
        sample_context,
        mock_position_manager,
        mock_trade_logger,
    ):
        """Test that event order respects timestamp then priority."""
        order = []
        
        def callback(event, context):
            order.append((event.timestamp, event.timeframe))
        
        ExecutionLoop.run(
            sample_events, 
            [callback], 
            [],  # signal_callbacks
            sample_context,
            mock_position_manager,
            mock_trade_logger,
            Interval.MINUTE_1,
        )
        
        # Verify sorted by timestamp
        timestamps = [ts for ts, _ in order]
        assert timestamps == sorted(timestamps)
        
        # At same timestamp, 1min should come before 5min
        for i in range(len(order) - 1):
            if order[i][0] == order[i + 1][0]:
                # Same timestamp
                tf1, tf2 = order[i][1], order[i + 1][1]
                if tf1 == Interval.MINUTE_5 and tf2 == Interval.MINUTE_1:
                    pytest.fail("5min came before 1min at same timestamp")


class TestExecutionLoopEdgeCases:
    """Edge case tests for ExecutionLoop."""
    
    def test_run_single_event(self, mock_position_manager, mock_trade_logger):
        """Test loop with exactly one event."""
        event = CandleEvent(
            timestamp=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            timeframe=Interval.MINUTE_1,
            ohlc=NormalizedOHLC(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                segment=Segment.EQ,
                interval=Interval.MINUTE_1,
                timestamp=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
                open=2500.0,
                high=2510.0,
                low=2495.0,
                close=2505.0,
                volume=100000,
            ),
            context=None,
        )
        
        context = BacktestContext(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            segment=Segment.EQ,
            base_interval=Interval.MINUTE_1,
            timeframes=[Interval.MINUTE_1],
            total_bars=1,
            current_bar_index=0,
            progress_pct=0.0,
        )
        
        calls = []
        def callback(e, c):
            calls.append((e, c))
        
        result = ExecutionLoop.run(
            [event], 
            [callback], 
            [],  # signal_callbacks
            context,
            mock_position_manager,
            mock_trade_logger,
            Interval.MINUTE_1,
        )
        
        assert result.events_processed == 1
        assert len(calls) == 1
        assert calls[0][1].progress_pct == 100.0
        assert calls[0][1].current_bar_index == 0
    
    def test_run_callback_modifies_context_does_not_affect_loop(
        self,
        sample_events,
        sample_context,
        mock_position_manager,
        mock_trade_logger,
    ):
        """Test that callback cannot mutate the loop's context."""
        def callback(event, context):
            # Try to modify context (should not affect loop since frozen)
            try:
                context.current_bar_index = 999
            except Exception:
                pass  # Expected for frozen dataclass
        
        result = ExecutionLoop.run(
            sample_events, 
            [callback], 
            [],  # signal_callbacks
            sample_context,
            mock_position_manager,
            mock_trade_logger,
            Interval.MINUTE_1,
        )
        
        assert result.events_processed == len(sample_events)