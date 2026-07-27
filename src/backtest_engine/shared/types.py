"""
Shared types and enums used across the codebase.

This module provides a single source of truth for common types that both
config and data_provider modules depend on. Contains ONLY enums and primitives
to break circular dependencies.
"""

from datetime import datetime
from enum import Enum
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")


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


# NOTE: NormalizedOHLC and NormalizedInstrument are defined in
# backtest_engine.data_provider.interfaces.models
# This module ONLY contains enums and primitives shared across modules.