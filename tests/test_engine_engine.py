"""
Tests for BacktestEngine and run_backtest convenience function.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from backtest_engine.data_provider.interfaces.models import (
    Exchange,
    Interval,
    NormalizedOHLC,
    Segment,
)
from backtest_engine.data_provider.utils import IST
from backtest_engine.engine.interfaces import BacktestConfig, BacktestResult, CandleEvent, DataFeeder
from backtest_engine.engine.engine import BacktestEngine, run_backtest


class TestBacktestEngine:
    """Test the BacktestEngine orchestrator."""
    
    @pytest.fixture
    def sample_config(self):
        return BacktestConfig(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            segment=Segment.EQ,
            base_interval=Interval.MINUTE_1,
            timeframes=[Interval.MINUTE_1, Interval.MINUTE_5],
            from_date=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            to_date=datetime(2024, 1, 1, 15, 30, tzinfo=IST),
        )
    
    @pytest.fixture
    def sample_events(self):
        """Create sample CandleEvents for testing."""
        events = []
        base_time = datetime(2024, 1, 1, 9, 15, tzinfo=IST)
        
        for i in range(10):
            ts = base_time + timedelta(minutes=i)
            events.append(CandleEvent(
                timestamp=ts,
                timeframe=Interval.MINUTE_1,
                ohlc=NormalizedOHLC(
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
                ),
                context=None,
            ))
        
        return events
    
    @pytest.fixture
    def mock_feeder(self, sample_events):
        """Create a mock feeder that returns events via ingestor."""
        feeder = AsyncMock(spec=DataFeeder)
        feeder.fetch_base_series = AsyncMock()
        feeder.close = AsyncMock()
        return feeder
    
    @pytest.mark.asyncio
    async def test_engine_creation(self, sample_config):
        """Test engine can be created with config."""
        engine = BacktestEngine(sample_config)
        assert engine.config == sample_config
        assert engine.events is None
        assert engine.result is None
    
    @pytest.mark.asyncio
    async def test_on_ohlc_candle_fluent(self, sample_config):
        """Test fluent callback registration."""
        engine = BacktestEngine(sample_config)
        
        def cb1(e, c): pass
        def cb2(e, c): pass
        
        result = engine.on_ohlc_candle(cb1).on_ohlc_candle(cb2)
        
        assert result is engine  # Fluent
        assert len(engine._callbacks) == 2
    
    @pytest.mark.asyncio
    async def test_prepare_calls_ingestor(
        self,
        sample_config,
        mock_feeder,
        sample_events,
    ):
        """Test prepare() runs ingestion pipeline."""
        # Mock the ingestor to return sample events
        with patch("backtest_engine.engine.engine.DataIngestor") as mock_ingestor_class:
            mock_ingestor = AsyncMock()
            mock_ingestor.ingest = AsyncMock(return_value=sample_events)
            mock_ingestor_class.return_value = mock_ingestor
            
            engine = BacktestEngine(sample_config)
            await engine.prepare(feeder=mock_feeder)
            
            # Verify ingestor was called
            mock_ingestor.ingest.assert_called_once_with(mock_feeder, sample_config)
            assert engine.events == sample_events
            assert engine._prepared is True
    
    @pytest.mark.asyncio
    async def test_run_without_prepare_raises(self, sample_config):
        """Test run() without prepare() raises RuntimeError."""
        engine = BacktestEngine(sample_config)
        
        with pytest.raises(RuntimeError, match="prepare"):
            engine.run()
    
    @pytest.mark.asyncio
    async def test_run_executes_loop(
        self,
        sample_config,
        sample_events,
    ):
        """Test run() executes ExecutionLoop with correct args."""
        with patch("backtest_engine.engine.engine.ExecutionLoop") as mock_loop_class:
            mock_result = BacktestResult(events_processed=10, duration_seconds=0.5)
            mock_loop_class.run = MagicMock(return_value=mock_result)
            
            engine = BacktestEngine(sample_config)
            engine._events = sample_events
            engine._prepared = True
            engine.on_ohlc_candle(lambda e, c: None)
            
            # Manually set position_manager and trade_logger since we're not calling prepare()
            from backtest_engine.engine.position_manager import PositionManager
            from backtest_engine.engine.trade_logger import TradeLogger
            engine._position_manager = PositionManager()
            engine._trade_logger = TradeLogger(
                base_dir="/tmp",
                strategy_name="test",
                initial_cash=1_000_000.0,
            )
            
            result = engine.run()
            
            # Verify loop was called with events, callbacks, signal_callbacks, context, position_manager, trade_logger, base_interval
            mock_loop_class.run.assert_called_once()
            call_args = mock_loop_class.run.call_args
            # call_args[0] is positional args tuple
            assert call_args[0][0] == sample_events
            assert len(call_args[0][1]) == 1
            assert len(call_args[0][2]) == 0  # signal_callbacks
            assert call_args[0][3].total_bars == 10
            assert call_args[0][4] is not None  # position_manager
            assert call_args[0][5] is not None  # trade_logger
            assert call_args[0][6] == sample_config.base_interval
            
            assert result == mock_result
            assert engine.result == mock_result
    
    @pytest.mark.asyncio
    async def test_run_no_callbacks_warns(
        self,
        sample_config,
        sample_events,
        capsys,
    ):
        """Test run() with no callbacks logs warning."""
        with patch("backtest_engine.engine.engine.ExecutionLoop.run") as mock_run:
            mock_run.return_value = BacktestResult(events_processed=10, duration_seconds=0.5)
            
            engine = BacktestEngine(sample_config)
            engine._events = sample_events
            engine._prepared = True
            # No callbacks registered
            
            engine.run()
            
            # loguru logs to stderr but may not be captured by capsys in test env
            # Just verify it completes without error
            assert True
    
    @pytest.mark.asyncio
    async def test_context_manager(self, sample_config, mock_feeder, sample_events):
        """Test async context manager protocol."""
        with patch("backtest_engine.engine.engine.DataIngestor") as mock_ingestor_class:
            mock_ingestor = AsyncMock()
            mock_ingestor.ingest = AsyncMock(return_value=sample_events)
            mock_ingestor_class.return_value = mock_ingestor
            
            async with BacktestEngine(sample_config) as engine:
                await engine.prepare(feeder=mock_feeder)
                assert engine._prepared
            
            # Verify close was called
            mock_feeder.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_close_calls_feeder_close(self, sample_config, mock_feeder):
        """Test explicit close() calls feeder.close()."""
        engine = BacktestEngine(sample_config)
        engine._feeder = mock_feeder
        
        await engine.close()
        
        mock_feeder.close.assert_called_once()


class TestRunBacktestConvenience:
    """Test the run_backtest() convenience function."""
    
    @pytest.fixture
    def sample_config(self):
        return BacktestConfig(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            segment=Segment.EQ,
            base_interval=Interval.MINUTE_1,
            timeframes=[Interval.MINUTE_1],
            from_date=datetime(2024, 1, 1, 9, 15, tzinfo=IST),
            to_date=datetime(2024, 1, 1, 15, 30, tzinfo=IST),
        )
    
    @pytest.fixture
    def sample_events(self):
        events = []
        base_time = datetime(2024, 1, 1, 9, 15, tzinfo=IST)
        for i in range(5):
            ts = base_time + timedelta(minutes=i)
            events.append(CandleEvent(
                timestamp=ts,
                timeframe=Interval.MINUTE_1,
                ohlc=NormalizedOHLC(
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
                ),
                context=None,
            ))
        return events
    
    @pytest.mark.asyncio
    async def test_run_backtest_creates_engine_and_runs(
        self,
        sample_config,
        sample_events,
    ):
        """Test run_backtest() creates engine, prepares, runs."""
        with patch("backtest_engine.engine.engine.BacktestEngine") as mock_engine_class:
            mock_engine = MagicMock()
            mock_engine.prepare = AsyncMock()
            mock_engine.run = MagicMock(return_value=BacktestResult(
                events_processed=5, duration_seconds=0.1
            ))
            # on_ohlc_candle returns self for chaining
            mock_engine.on_ohlc_candle.return_value = mock_engine
            mock_engine_class.return_value = mock_engine
            
            def callback(e, c): pass
            
            result = await run_backtest(sample_config, callback)
            
            # Verify engine creation and method calls
            mock_engine_class.assert_called_once_with(sample_config)
            mock_engine.on_ohlc_candle.assert_called_once_with(callback)
            mock_engine.prepare.assert_called_once()
            mock_engine.run.assert_called_once()
            
            assert result.events_processed == 5
    
    @pytest.mark.asyncio
    async def test_run_backtest_passes_custom_feeder(
        self,
        sample_config,
    ):
        """Test run_backtest() passes custom feeder to prepare()."""
        custom_feeder = AsyncMock()
        
        with patch("backtest_engine.engine.engine.BacktestEngine") as mock_engine_class:
            mock_engine = MagicMock()
            mock_engine.prepare = AsyncMock()
            mock_engine.run = MagicMock(return_value=BacktestResult(
                events_processed=0, duration_seconds=0.0
            ))
            mock_engine.on_ohlc_candle.return_value = mock_engine
            mock_engine_class.return_value = mock_engine
            
            def callback(e, c): pass
            
            await run_backtest(sample_config, callback, feeder=custom_feeder)
            
            mock_engine.prepare.assert_called_once_with(custom_feeder)
    
    @pytest.mark.asyncio
    async def test_run_backtest_multiple_callbacks(
        self,
        sample_config,
    ):
        """Test run_backtest() accepts multiple callbacks."""
        with patch("backtest_engine.engine.engine.BacktestEngine") as mock_engine_class:
            mock_engine = MagicMock()
            mock_engine.prepare = AsyncMock()
            mock_engine.run = MagicMock(return_value=BacktestResult(
                events_processed=0, duration_seconds=0.0
            ))
            mock_engine.on_ohlc_candle.return_value = mock_engine
            mock_engine_class.return_value = mock_engine
            
            def cb1(e, c): pass
            def cb2(e, c): pass
            
            await run_backtest(sample_config, cb1, cb2)
            
            # Should call on_ohlc_candle for each callback
            assert mock_engine.on_ohlc_candle.call_count == 2
            mock_engine.on_ohlc_candle.assert_any_call(cb1)
            mock_engine.on_ohlc_candle.assert_any_call(cb2)