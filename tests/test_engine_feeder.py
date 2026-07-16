"""
Tests for ParquetDataFeeder — mock DataProviderClient to verify contract.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from backtest_engine.data_provider.interfaces.models import (
    Exchange,
    Interval,
    NormalizedOHLC,
    Segment,
)
from backtest_engine.data_provider.utils import IST
from backtest_engine.engine.feeder import ParquetDataFeeder
from backtest_engine.engine.interfaces import BacktestConfig, DataFeeder


class TestParquetDataFeeder:
    """Test the ParquetDataFeeder implementation of DataFeeder."""
    
    @pytest.fixture
    def mock_client(self):
        """Create a mock DataProviderClient."""
        client = AsyncMock()
        client.initialize = AsyncMock()
        client.close = AsyncMock()
        client.get_historical_ohlc_data = AsyncMock()
        return client
    
    @pytest.fixture
    def sample_config(self):
        """Create a sample BacktestConfig."""
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
    def sample_ohlc_data(self):
        """Create sample NormalizedOHLC data."""
        return [
            NormalizedOHLC(
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
                open_interest=50000,
            ),
            NormalizedOHLC(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                segment=Segment.EQ,
                interval=Interval.MINUTE_1,
                timestamp=datetime(2024, 1, 1, 9, 16, tzinfo=IST),
                open=2505.0,
                high=2515.0,
                low=2500.0,
                close=2510.0,
                volume=80000,
                open_interest=51000,
            ),
        ]
    
    @pytest.mark.asyncio
    async def test_fetch_base_series_success(
        self,
        mock_client,
        sample_config,
        sample_ohlc_data,
    ):
        """Test successful data fetch returns NormalizedOHLC list."""
        # Setup mock response
        mock_response = MagicMock()
        mock_response.data = sample_ohlc_data
        mock_response.provider = "zerodha"
        mock_client.get_historical_ohlc_data.return_value = mock_response
        
        feeder = ParquetDataFeeder(client=mock_client)
        result = await feeder.fetch_base_series(sample_config)
        
        # Verify client was initialized and called correctly
        mock_client.initialize.assert_called_once()
        mock_client.get_historical_ohlc_data.assert_called_once()
        
        # Verify result
        assert result == sample_ohlc_data
        assert len(result) == 2
    
    @pytest.mark.asyncio
    async def test_fetch_base_series_empty_data_raises(
        self,
        mock_client,
        sample_config,
    ):
        """Test that empty data raises DataNotFoundError."""
        mock_response = MagicMock()
        mock_response.data = []
        mock_response.provider = "zerodha"
        mock_client.get_historical_ohlc_data.return_value = mock_response
        
        feeder = ParquetDataFeeder(client=mock_client)
        
        with pytest.raises(Exception) as exc_info:
            await feeder.fetch_base_series(sample_config)
        
        # Should be DataNotFoundError
        assert "No data found" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_fetch_base_series_passes_correct_request(
        self,
        mock_client,
        sample_config,
        sample_ohlc_data,
    ):
        """Test that the correct parameters are passed to client."""
        mock_response = MagicMock()
        mock_response.data = sample_ohlc_data
        mock_response.provider = "zerodha"
        mock_client.get_historical_ohlc_data.return_value = mock_response
        
        feeder = ParquetDataFeeder(client=mock_client)
        await feeder.fetch_base_series(sample_config)
        
        # Verify the parameters passed to client
        call_args = mock_client.get_historical_ohlc_data.call_args
        kwargs = call_args.kwargs
        
        assert kwargs["symbol"] == "RELIANCE"
        assert kwargs["exchange"] == "NSE"
        assert kwargs["segment"] == "EQ"
        assert kwargs["interval"] == "1minute"
        assert kwargs["from_date"] == sample_config.from_date
        assert kwargs["to_date"] == sample_config.to_date
        assert kwargs["continuous"] is False
        assert kwargs["oi"] is False
    
    @pytest.mark.asyncio
    async def test_lazy_initialization(
        self,
        mock_client,
        sample_config,
        sample_ohlc_data,
    ):
        """Test that client is initialized only once on first fetch."""
        mock_response = MagicMock()
        mock_response.data = sample_ohlc_data
        mock_response.provider = "zerodha"
        mock_client.get_historical_ohlc_data.return_value = mock_response
        
        feeder = ParquetDataFeeder(client=mock_client)
        
        # First fetch
        await feeder.fetch_base_series(sample_config)
        assert mock_client.initialize.call_count == 1
        
        # Second fetch
        await feeder.fetch_base_series(sample_config)
        assert mock_client.initialize.call_count == 1  # Not called again
    
    @pytest.mark.asyncio
    async def test_context_manager(
        self,
        mock_client,
        sample_config,
        sample_ohlc_data,
    ):
        """Test async context manager protocol."""
        mock_response = MagicMock()
        mock_response.data = sample_ohlc_data
        mock_response.provider = "zerodha"
        mock_client.get_historical_ohlc_data.return_value = mock_response
        
        async with ParquetDataFeeder(client=mock_client) as feeder:
            result = await feeder.fetch_base_series(sample_config)
            assert len(result) == 2
        
        # Verify close was called on exit
        mock_client.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_close_calls_client_close(self, mock_client):
        """Test explicit close() calls client.close()."""
        feeder = ParquetDataFeeder(client=mock_client)
        feeder._initialized = True
        
        await feeder.close()
        
        mock_client.close.assert_called_once()
    
    def test_feeder_implements_protocol(self):
        """Verify ParquetDataFeeder implements DataFeeder."""
        from backtest_engine.engine.interfaces import DataFeeder
        
        feeder = ParquetDataFeeder()
        assert isinstance(feeder, DataFeeder)
    
    @pytest.mark.asyncio
    async def test_custom_client_injected(self, sample_config, sample_ohlc_data):
        """Test that a custom client can be injected."""
        custom_client = AsyncMock()
        custom_client.initialize = AsyncMock()
        custom_client.close = AsyncMock()
        custom_client.get_historical_ohlc_data = AsyncMock()
        
        mock_response = MagicMock()
        mock_response.data = sample_ohlc_data
        mock_response.provider = "custom"
        custom_client.get_historical_ohlc_data.return_value = mock_response
        
        feeder = ParquetDataFeeder(client=custom_client)
        result = await feeder.fetch_base_series(sample_config)
        
        assert result == sample_ohlc_data
        custom_client.initialize.assert_called_once()