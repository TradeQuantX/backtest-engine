"""
Pytest configuration for data provider tests.
"""

import pytest
import asyncio
from datetime import datetime, timezone


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_ohlc_data():
    """Sample OHLC data for testing."""
    from backtest_engine.data_provider.interfaces.models import (
        NormalizedOHLC, Exchange, Segment, Interval
    )
    
    return [
        NormalizedOHLC(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            segment=Segment.EQ,
            interval=Interval.MINUTE_1,
            timestamp=datetime(2024, 1, 1, 9, 15, tzinfo=timezone.utc),
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
            timestamp=datetime(2024, 1, 1, 9, 16, tzinfo=timezone.utc),
            open=2505.0,
            high=2515.0,
            low=2500.0,
            close=2510.0,
            volume=80000,
            open_interest=51000,
        ),
    ]


@pytest.fixture
def sample_instrument():
    """Sample instrument for testing."""
    from backtest_engine.data_provider.interfaces.models import (
        NormalizedInstrument, Exchange, Segment, InstrumentType
    )
    
    return NormalizedInstrument(
        instrument_token="12345",
        symbol="RELIANCE",
        name="Reliance Industries Ltd",
        exchange=Exchange.NSE,
        segment=Segment.EQ,
        instrument_type=InstrumentType.EQ,
        lot_size=1,
        tick_size=0.05,
    )