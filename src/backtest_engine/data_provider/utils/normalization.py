"""
Data normalization utilities.

Converts provider-specific data formats to normalized models.
All timestamps are normalized to IST (Asia/Kolkata).
"""

from datetime import datetime
from typing import Any, Optional

import polars as pl

from backtest_engine.data_provider.interfaces.models import (
    Exchange,
    InstrumentType,
    Interval,
    NormalizedInstrument,
    NormalizedOHLC,
    Segment,
)
from backtest_engine.data_provider.utils import IST


def normalize_timestamp(
    timestamp: Any,
    source_tz: str = "Asia/Kolkata",
) -> datetime:
    """
    Normalize timestamp to IST datetime.
    
    Args:
        timestamp: Input timestamp (string, int, float, datetime)
        source_tz: Source timezone (default: IST)
        
    Returns:
        IST datetime
    """
    if isinstance(timestamp, datetime):
        dt = timestamp
    elif isinstance(timestamp, (int, float)):
        # Assume epoch seconds or milliseconds
        if timestamp > 1e12:  # Milliseconds
            timestamp = timestamp / 1000
        # Provider epoch timestamps are IST-based
        dt = datetime.fromtimestamp(timestamp, tz=IST)
    elif isinstance(timestamp, str):
        # Try parsing common formats
        for fmt in [
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]:
            try:
                dt = datetime.strptime(timestamp, fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"Unable to parse timestamp: {timestamp}")
    else:
        raise TypeError(f"Unsupported timestamp type: {type(timestamp)}")
    
    # Ensure timezone aware - assume IST if naive
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    
    # Convert to IST (not UTC)
    return dt.astimezone(IST)


def normalize_interval(interval: str, provider: str) -> Interval:
    """
    Normalize provider-specific interval to standard Interval enum.
    
    Args:
        interval: Provider interval string
        provider: Provider name ('zerodha', 'dhan')
        
    Returns:
        Normalized Interval enum
    """
    interval = interval.lower().strip()
    
    # Zerodha intervals
    zerodha_map = {
        "minute": Interval.MINUTE_1,
        "3minute": Interval.MINUTE_3,
        "5minute": Interval.MINUTE_5,
        "10minute": Interval.MINUTE_10,
        "15minute": Interval.MINUTE_15,
        "30minute": Interval.MINUTE_30,
        "60minute": Interval.MINUTE_60,
        "day": Interval.DAY,
    }
    
    # Dhan intervals
    dhan_map = {
        "1": Interval.MINUTE_1,
        "5": Interval.MINUTE_5,
        "15": Interval.MINUTE_15,
        "30": Interval.MINUTE_30,
        "60": Interval.MINUTE_60,
        "day": Interval.DAY,
    }
    
    if provider == "zerodha":
        return zerodha_map.get(interval, Interval.MINUTE_1)
    elif provider == "dhan":
        return dhan_map.get(interval, Interval.MINUTE_5)
    
    # Try direct match
    for enum_val in Interval:
        if enum_val.value == interval:
            return enum_val
    
    raise ValueError(f"Unknown interval '{interval}' for provider '{provider}'")


def normalize_exchange(exchange: str, provider: str) -> Exchange:
    """Normalize provider-specific exchange to standard Exchange enum."""
    exchange = exchange.upper().strip()
    
    # Zerodha exchanges
    zerodha_map = {
        "NSE": Exchange.NSE,
        "BSE": Exchange.BSE,
        "NFO": Exchange.NFO,
        "BFO": Exchange.BFO,
        "CDS": Exchange.CDS,
        "MCX": Exchange.MCX,
        "BCD": Exchange.BCD,
        "MF": Exchange.MF,
    }
    
    # Dhan exchanges
    dhan_map = {
        "NSE_EQ": Exchange.NSE,
        "BSE_EQ": Exchange.BSE,
        "NSE_FNO": Exchange.NFO,
        "BSE_FNO": Exchange.BFO,
        "MCX_COMM": Exchange.MCX,
        "NSE_CDS": Exchange.CDS,
    }
    
    if provider == "zerodha":
        return zerodha_map.get(exchange, Exchange.NSE)
    elif provider == "dhan":
        return dhan_map.get(exchange, Exchange.NSE)
    
    for enum_val in Exchange:
        if enum_val.value == exchange:
            return enum_val
    
    raise ValueError(f"Unknown exchange '{exchange}' for provider '{provider}'")


def normalize_segment(segment: str, provider: str) -> Segment:
    """Normalize provider-specific segment to standard Segment enum."""
    segment = segment.upper().strip()
    
    zerodha_map = {
        "EQ": Segment.EQ,
        "FO": Segment.FO,
        "CDS": Segment.CDS,
        "MCX": Segment.MCX,
        "MF": Segment.MF,
    }
    
    dhan_map = {
        "EQUITY": Segment.EQ,
        "FUTURES": Segment.FO,
        "OPTIONS": Segment.FO,
        "CURRENCY": Segment.CDS,
        "COMMODITY": Segment.MCX,
    }
    
    if provider == "zerodha":
        return zerodha_map.get(segment, Segment.EQ)
    elif provider == "dhan":
        return dhan_map.get(segment, Segment.EQ)
    
    for enum_val in Segment:
        if enum_val.value == segment:
            return enum_val
    
    raise ValueError(f"Unknown segment '{segment}' for provider '{provider}'")


def normalize_instrument_type(inst_type: str, provider: str) -> InstrumentType:
    """Normalize provider-specific instrument type."""
    inst_type = inst_type.upper().strip()
    
    zerodha_map = {
        "EQ": InstrumentType.EQ,
        "FUT": InstrumentType.FUT,
        "OPT": InstrumentType.OPT,
        "IDX": InstrumentType.IDX,
    }
    
    dhan_map = {
        "EQUITY": InstrumentType.EQ,
        "FUTURES": InstrumentType.FUT,
        "OPTIONS": InstrumentType.OPT,
        "INDEX": InstrumentType.IDX,
    }
    
    if provider == "zerodha":
        return zerodha_map.get(inst_type, InstrumentType.EQ)
    elif provider == "dhan":
        return dhan_map.get(inst_type, InstrumentType.EQ)
    
    for enum_val in InstrumentType:
        if enum_val.value == inst_type:
            return enum_val
    
    raise ValueError(f"Unknown instrument type '{inst_type}' for provider '{provider}'")


def zerodha_ohlc_to_normalized(
    candles: list[list],
    symbol: str,
    exchange: Exchange,
    segment: Segment,
    interval: Interval,
    provider: str = "zerodha",
) -> list[NormalizedOHLC]:
    """
    Convert Zerodha candle format to NormalizedOHLC.
    
    Zerodha format: [timestamp, open, high, low, close, volume] or
                    [timestamp, open, high, low, close, volume, oi]
    """
    result = []
    
    for candle in candles:
        if len(candle) < 6:
            continue
        
        timestamp = normalize_timestamp(candle[0])
        oi = candle[6] if len(candle) > 6 else None
        
        result.append(NormalizedOHLC(
            symbol=symbol,
            exchange=exchange,
            segment=segment,
            interval=interval,
            timestamp=timestamp,
            open=float(candle[1]),
            high=float(candle[2]),
            low=float(candle[3]),
            close=float(candle[4]),
            volume=int(candle[5]),
            open_interest=int(oi) if oi is not None else None,
        ))
    
    return result


def dhan_ohlc_to_normalized(
    data: dict,
    symbol: str,
    exchange: Exchange,
    segment: Segment,
    interval: Interval,
    provider: str = "dhan",
) -> list[NormalizedOHLC]:
    """
    Convert Dhan OHLC format to NormalizedOHLC.
    
    Dhan format: {open: [], high: [], low: [], close: [], volume: [], 
                  open_interest: [], timestamp: []}
    """
    result = []
    
    opens = data.get("open", [])
    highs = data.get("high", [])
    lows = data.get("low", [])
    closes = data.get("close", [])
    volumes = data.get("volume", [])
    ois = data.get("open_interest", [])
    timestamps = data.get("timestamp", [])
    
    length = min(len(opens), len(highs), len(lows), len(closes), len(volumes), len(timestamps))
    
    for i in range(length):
        timestamp = normalize_timestamp(timestamps[i])
        oi = ois[i] if i < len(ois) and ois[i] is not None else None
        
        result.append(NormalizedOHLC(
            symbol=symbol,
            exchange=exchange,
            segment=segment,
            interval=interval,
            timestamp=timestamp,
            open=float(opens[i]),
            high=float(highs[i]),
            low=float(lows[i]),
            close=float(closes[i]),
            volume=int(volumes[i]),
            open_interest=int(oi) if oi is not None else None,
        ))
    
    return result


def normalized_to_polars(data: list[NormalizedOHLC]) -> pl.DataFrame:
    """Convert list of NormalizedOHLC to Polars DataFrame."""
    if not data:
        return pl.DataFrame(schema={
            "symbol": pl.Utf8,
            "exchange": pl.Utf8,
            "segment": pl.Utf8,
            "interval": pl.Utf8,
            "timestamp": pl.Datetime("us", "Asia/Kolkata"),
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Int64,
            "open_interest": pl.Int64,
        })
    
    return pl.DataFrame([
        {
            "symbol": d.symbol,
            "exchange": d.exchange.value,
            "segment": d.segment.value,
            "interval": d.interval.value,
            "timestamp": d.timestamp,
            "open": d.open,
            "high": d.high,
            "low": d.low,
            "close": d.close,
            "volume": d.volume,
            "open_interest": d.open_interest,
        }
        for d in data
    ])


def polars_to_normalized(df: pl.DataFrame) -> list[NormalizedOHLC]:
    """Convert Polars DataFrame to list of NormalizedOHLC."""
    result = []
    
    for row in df.iter_rows(named=True):
        result.append(NormalizedOHLC(
            symbol=row["symbol"],
            exchange=Exchange(row["exchange"]),
            segment=Segment(row["segment"]),
            interval=Interval(row["interval"]),
            timestamp=row["timestamp"],
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=row["volume"],
            open_interest=row.get("open_interest"),
        ))
    
    return result


def zerodha_instrument_to_normalized(
    instrument: dict,
    provider: str = "zerodha",
) -> NormalizedInstrument:
    """Convert Zerodha instrument to NormalizedInstrument."""
    return NormalizedInstrument(
        instrument_token=str(instrument.get("instrument_token", "")),
        symbol=instrument.get("tradingsymbol", ""),
        name=instrument.get("name", ""),
        exchange=normalize_exchange(instrument.get("exchange", ""), provider),
        segment=normalize_segment(instrument.get("segment", ""), provider),
        instrument_type=normalize_instrument_type(
            instrument.get("instrument_type", ""), provider
        ),
        expiry=normalize_timestamp(instrument["expiry"]) if instrument.get("expiry") else None,
        strike=float(instrument["strike"]) if instrument.get("strike") else None,
        lot_size=int(instrument.get("lot_size", 1)),
        tick_size=float(instrument.get("tick_size", 0.05)),
        is_active=True,
    )


def dhan_instrument_to_normalized(
    instrument: dict,
    provider: str = "dhan",
) -> NormalizedInstrument:
    """Convert Dhan instrument to NormalizedInstrument."""
    return NormalizedInstrument(
        instrument_token=str(instrument.get("securityId", "")),
        symbol=instrument.get("tradingSymbol", ""),
        name=instrument.get("symbolName", ""),
        exchange=normalize_exchange(instrument.get("exchangeSegment", ""), provider),
        segment=normalize_segment(instrument.get("instrument", ""), provider),
        instrument_type=normalize_instrument_type(
            instrument.get("instrumentType", ""), provider
        ),
        expiry=normalize_timestamp(instrument["expiryDate"]) if instrument.get("expiryDate") else None,
        strike=float(instrument["strikePrice"]) if instrument.get("strikePrice") else None,
        lot_size=int(instrument.get("lotSize", 1)),
        tick_size=float(instrument.get("tickSize", 0.05)),
        is_active=instrument.get("isActive", True),
    )