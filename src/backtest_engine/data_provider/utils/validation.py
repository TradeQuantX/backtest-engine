"""
Data validation utilities.

Validates OHLC data, instruments, and requests.
"""

from datetime import datetime

import polars as pl

from backtest_engine.data_provider.interfaces.models import (
    Exchange,
    HistoricalDataRequest,
    Interval,
    NormalizedInstrument,
    NormalizedOHLC,
    Segment,
)
from backtest_engine.data_provider.exceptions import ValidationError
from backtest_engine.data_provider.utils import IST


def validate_ohlc_data(data: list[NormalizedOHLC]) -> list[ValidationError]:
    """
    Validate OHLC data for consistency.
    
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    if not data:
        return errors
    
    for i, candle in enumerate(data):
        # Check OHLC relationships
        if candle.high < candle.low:
            errors.append(ValidationError(
                f"High < Low at index {i}",
                field="high/low",
                value=f"high={candle.high}, low={candle.low}",
            ))
        
        if candle.open > candle.high or candle.open < candle.low:
            errors.append(ValidationError(
                f"Open outside High/Low range at index {i}",
                field="open",
                value=str(candle.open),
                expected=f"between {candle.low} and {candle.high}",
            ))
        
        if candle.close > candle.high or candle.close < candle.low:
            errors.append(ValidationError(
                f"Close outside High/Low range at index {i}",
                field="close",
                value=str(candle.close),
                expected=f"between {candle.low} and {candle.high}",
            ))
        
        # Check for negative values
        if candle.volume < 0:
            errors.append(ValidationError(
                f"Negative volume at index {i}",
                field="volume",
                value=str(candle.volume),
                expected=">= 0",
            ))
        
        if candle.open_interest is not None and candle.open_interest < 0:
            errors.append(ValidationError(
                f"Negative open interest at index {i}",
                field="open_interest",
                value=str(candle.open_interest),
                expected=">= 0",
            ))
        
        # Check timestamp ordering
        if i > 0 and candle.timestamp <= data[i - 1].timestamp:
            errors.append(ValidationError(
                f"Timestamp not strictly increasing at index {i}",
                field="timestamp",
                value=candle.timestamp.isoformat(),
                expected=f"> {data[i - 1].timestamp.isoformat()}",
            ))
    
    return errors


def validate_ohlc_dataframe(df: pl.DataFrame) -> list[ValidationError]:
    """Validate OHLC data in Polars DataFrame."""
    errors = []
    
    if df.is_empty():
        return errors
    
    # Check required columns
    required = ["symbol", "exchange", "segment", "interval", "timestamp", 
                "open", "high", "low", "close", "volume"]
    for col in required:
        if col not in df.columns:
            errors.append(ValidationError(
                f"Missing required column: {col}",
                field=col,
            ))
    
    if errors:
        return errors
    
    # Check OHLC relationships
    invalid_high_low = df.filter(pl.col("high") < pl.col("low"))
    if not invalid_high_low.is_empty():
        errors.append(ValidationError(
            f"High < Low in {len(invalid_high_low)} rows",
            field="high/low",
        ))
    
    invalid_open = df.filter(
        (pl.col("open") > pl.col("high")) | (pl.col("open") < pl.col("low"))
    )
    if not invalid_open.is_empty():
        errors.append(ValidationError(
            f"Open outside High/Low in {len(invalid_open)} rows",
            field="open",
        ))
    
    invalid_close = df.filter(
        (pl.col("close") > pl.col("high")) | (pl.col("close") < pl.col("low"))
    )
    if not invalid_close.is_empty():
        errors.append(ValidationError(
            f"Close outside High/Low in {len(invalid_close)} rows",
            field="close",
        ))
    
    # Check negative values
    neg_volume = df.filter(pl.col("volume") < 0)
    if not neg_volume.is_empty():
        errors.append(ValidationError(
            f"Negative volume in {len(neg_volume)} rows",
            field="volume",
        ))
    
    if "open_interest" in df.columns:
        neg_oi = df.filter(pl.col("open_interest") < 0)
        if not neg_oi.is_empty():
            errors.append(ValidationError(
                f"Negative open interest in {len(neg_oi)} rows",
                field="open_interest",
            ))
    
    # Check timestamp ordering (per symbol)
    if "symbol" in df.columns:
        for symbol in df["symbol"].unique():
            symbol_df = df.filter(pl.col("symbol") == symbol).sort("timestamp")
            timestamps = symbol_df["timestamp"].to_list()
            for i in range(1, len(timestamps)):
                if timestamps[i] <= timestamps[i - 1]:
                    errors.append(ValidationError(
                        f"Non-increasing timestamp for {symbol} at index {i}",
                        field="timestamp",
                    ))
                    break
    
    return errors


def validate_instrument(instrument: NormalizedInstrument) -> list[ValidationError]:
    """Validate a single instrument."""
    errors = []
    
    if not instrument.symbol:
        errors.append(ValidationError(
            "Instrument symbol is empty",
            field="symbol",
        ))
    
    if not instrument.instrument_token:
        errors.append(ValidationError(
            "Instrument token is empty",
            field="instrument_token",
        ))
    
    if instrument.lot_size <= 0:
        errors.append(ValidationError(
            "Lot size must be positive",
            field="lot_size",
            value=str(instrument.lot_size),
        ))
    
    if instrument.tick_size <= 0:
        errors.append(ValidationError(
            "Tick size must be positive",
            field="tick_size",
            value=str(instrument.tick_size),
        ))
    
    if instrument.strike is not None and instrument.strike < 0:
        errors.append(ValidationError(
            "Strike price cannot be negative",
            field="strike",
            value=str(instrument.strike),
        ))
    
    return errors


def validate_historical_request(request: HistoricalDataRequest) -> list[ValidationError]:
    """Validate a historical data request."""
    errors = []
    
    if not request.symbol:
        errors.append(ValidationError(
            "Symbol is required",
            field="symbol",
        ))
    
    # Ensure both dates are timezone-aware for comparison
    from_date = request.from_date.replace(tzinfo=IST) if request.from_date.tzinfo is None else request.from_date
    to_date = request.to_date.replace(tzinfo=IST) if request.to_date.tzinfo is None else request.to_date
    
    if from_date >= to_date:
        errors.append(ValidationError(
            "from_date must be before to_date",
            field="from_date/to_date",
            value=f"from={request.from_date}, to={request.to_date}",
        ))
    
    # Check date range not too far in future
    now = datetime.now(IST)
    
    if from_date > now:
        errors.append(ValidationError(
            "from_date cannot be in the future",
            field="from_date",
            value=request.from_date.isoformat(),
        ))
    
    if to_date > now:
        errors.append(ValidationError(
            "to_date cannot be in the future",
            field="to_date",
            value=request.to_date.isoformat(),
        ))
    
    return errors


def validate_dataframe_schema(
    df: pl.DataFrame,
    expected_schema: dict[str, pl.DataType],
) -> list[ValidationError]:
    """Validate DataFrame matches expected schema."""
    errors = []
    
    for col, expected_type in expected_schema.items():
        if col not in df.columns:
            errors.append(ValidationError(
                f"Missing column: {col}",
                field=col,
                expected=str(expected_type),
            ))
        elif df[col].dtype != expected_type:
            errors.append(ValidationError(
                f"Column {col} has wrong type",
                field=col,
                value=str(df[col].dtype),
                expected=str(expected_type),
            ))
    
    return errors