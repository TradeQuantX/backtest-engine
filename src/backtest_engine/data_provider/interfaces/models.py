"""
Normalized data models for the data provider layer.

All providers must normalize their data to these models before returning.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class Exchange(str, Enum):
    """Supported exchanges."""
    NSE = "NSE"
    BSE = "BSE"
    MCX = "MCX"
    NFO = "NFO"
    BFO = "BFO"
    CDS = "CDS"
    BCD = "BCD"
    MF = "MF"


class Segment(str, Enum):
    """Market segments."""
    EQ = "EQ"      # Equity
    FO = "FO"      # Futures & Options
    CDS = "CDS"    # Currency Derivatives
    MCX = "MCX"    # Commodity
    MF = "MF"      # Mutual Funds


class Interval(str, Enum):
    """Supported time intervals."""
    MINUTE_1 = "1minute"
    MINUTE_3 = "3minute"
    MINUTE_5 = "5minute"
    MINUTE_10 = "10minute"
    MINUTE_15 = "15minute"
    MINUTE_30 = "30minute"
    MINUTE_60 = "60minute"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class InstrumentType(str, Enum):
    """Instrument types."""
    EQ = "EQ"
    FUT = "FUT"
    OPT = "OPT"
    IDX = "IDX"
    CUR = "CUR"
    COM = "COM"
    MF = "MF"


@dataclass(frozen=True, slots=True)
class NormalizedOHLC:
    """
    Normalized OHLC data point.
    
    All providers must convert their data to this format.
    Timestamps are always IST (Asia/Kolkata).
    """
    symbol: str
    exchange: Exchange
    segment: Segment
    interval: Interval
    timestamp: datetime  # IST
    open: float
    high: float
    low: float
    close: float
    volume: int
    open_interest: Optional[int] = None


@dataclass(frozen=True, slots=True)
class NormalizedInstrument:
    """
    Normalized instrument master entry.
    
    All providers must convert their instrument data to this format.
    """
    instrument_token: str  # Provider-specific token
    symbol: str
    name: str
    exchange: Exchange
    segment: Segment
    instrument_type: InstrumentType
    expiry: Optional[datetime] = None
    strike: Optional[float] = None
    lot_size: int = 1
    tick_size: float = 0.05
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class HistoricalDataRequest:
    """Request parameters for historical data."""
    symbol: str
    exchange: Exchange
    segment: Segment
    interval: Interval
    from_date: datetime
    to_date: datetime
    continuous: bool = False
    oi: bool = False


@dataclass(frozen=True, slots=True)
class HistoricalDataResponse:
    """Response containing historical OHLC data."""
    data: list[NormalizedOHLC]
    symbol: str
    exchange: Exchange
    segment: Segment
    interval: Interval
    from_date: datetime
    to_date: datetime
    provider: str
    cached: bool = False