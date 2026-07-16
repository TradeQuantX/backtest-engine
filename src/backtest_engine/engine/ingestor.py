"""
Data Ingestor — validates, normalizes, preprocesses, resamples, and merges OHLC data.

Transforms raw base-interval data into a sorted, merged timeline of closed CandleEvents
across multiple timeframes. All heavy aggregation done in Polars (Rust) for speed.
"""

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Optional

import polars as pl

from backtest_engine.data_provider.exceptions import (
    DataNotFoundError,
    InsufficientDataError,
    ValidationError,
)
from backtest_engine.data_provider.utils.normalization import normalize_timestamp
from backtest_engine.data_provider.utils.validation import validate_ohlc_data
from backtest_engine.engine.feeder import DataFeeder
from backtest_engine.engine.interfaces import (
    BacktestConfig,
    BacktestContext,
    CandleEvent,
    NormalizedOHLC,
    Preprocessor,
)


# =============================================================================
# Timeframe Duration Mapping
# =============================================================================

_INTERVAL_TO_DURATION = {
    "1minute": "1m",
    "3minute": "3m",
    "5minute": "5m",
    "10minute": "10m",
    "15minute": "15m",
    "30minute": "30m",
    "60minute": "1h",
    "day": "1d",
    "week": "1w",
    "month": "1mo",
}


def _interval_to_polars_duration(interval: str) -> str:
    """Convert Interval enum value to Polars duration string."""
    duration = _INTERVAL_TO_DURATION.get(interval)
    if not duration:
        raise ValueError(f"Unsupported interval for resampling: {interval}")
    return duration


# =============================================================================
# Data Ingestor
# =============================================================================

class DataIngestor:
    """
    Transforms base-interval OHLC data into a merged, sorted timeline of CandleEvents.
    
    Pipeline:
    1. Fetch base series from feeder
    2. Validate OHLC integrity, monotonic timestamps, duplicates, gaps
    3. Normalize to IST, sort, deduplicate
    4. Optional preprocessing (vectorized Polars on base series)
    5. Resample to each configured timeframe via Polars group_by_dynamic
    6. Merge all timeframes into single sorted list of CandleEvents
    
    The merged list has len() known upfront, enabling progress tracking
    and deterministic execution in the loop.
    """
    
    def __init__(self):
        self._gap_threshold_minutes = 5  # Max gap before warning
    
    async def ingest(
        self,
        feeder: DataFeeder,
        config: BacktestConfig,
    ) -> list[CandleEvent]:
        """
        Execute the full ingestion pipeline.
        
        Args:
            feeder: DataFeeder implementation (e.g., ParquetDataFeeder)
            config: BacktestConfig with all parameters
            
        Returns:
            Sorted list of CandleEvent across all configured timeframes
            
        Raises:
            DataNotFoundError: No data returned from feeder
            ValidationError: OHLC validation failed (if strict_validation=True)
            InsufficientDataError: Not enough bars for resampling
        """
        # 1. Fetch base series
        base_series = await feeder.fetch_base_series(config)
        
        if not base_series:
            raise DataNotFoundError(
                f"No base data returned for {config.symbol} "
                f"{config.from_date} to {config.to_date}"
            )
        
        # 2. Validate
        self._validate_base_series(base_series, config.strict_validation)
        
        # 3. Normalize & convert to Polars
        base_df = self._normalize_to_polars(base_series)
        
        # 4. Preprocess (optional)
        if config.preprocessor:
            base_df = config.preprocessor.process(base_df)
        
        # 5. Resample to each timeframe
        all_events: list[CandleEvent] = []
        
        for tf in config.timeframes:
            tf_events = self._resample_timeframe(base_df, tf, config)
            all_events.extend(tf_events)
        
        # 6. Merge & sort
        merged_events = self._merge_and_sort(all_events, config.base_interval)
        
        if not merged_events:
            raise InsufficientDataError(
                "No events generated after resampling and merging"
            )
        
        return merged_events
    
    def _validate_base_series(
        self,
        base_series: list[NormalizedOHLC],
        strict: bool,
    ) -> None:
        """
        Validate base series integrity.
        
        Checks:
        - OHLC relationships (high >= low, open/close in [low, high])
        - Volume >= 0
        - Monotonic timestamps (strictly increasing)
        - No duplicate timestamps
        - Gap detection (warn if gaps exceed threshold)
        """
        if not base_series:
            return
        
        # OHLC validation (reuses existing utility)
        errors = validate_ohlc_data(base_series)
        if errors:
            msg = f"OHLC validation failed: {errors}"
            if strict:
                raise ValidationError(msg)
            else:
                # Log warning but continue
                import loguru
                loguru.logger.warning(msg)
        
        # Timestamp validation
        timestamps = [bar.timestamp for bar in base_series]
        
        # Check monotonic
        for i in range(1, len(timestamps)):
            if timestamps[i] <= timestamps[i - 1]:
                msg = f"Non-monotonic timestamp at index {i}: {timestamps[i]} <= {timestamps[i-1]}"
                if strict:
                    raise ValidationError(msg)
                else:
                    import loguru
                    loguru.logger.warning(msg)
        
        # Check duplicates
        seen = set()
        for i, ts in enumerate(timestamps):
            if ts in seen:
                msg = f"Duplicate timestamp at index {i}: {ts}"
                if strict:
                    raise ValidationError(msg)
                else:
                    import loguru
                    loguru.logger.warning(msg)
            seen.add(ts)
        
        # Gap detection
        self._detect_gaps(timestamps, strict)
    
    def _detect_gaps(
        self,
        timestamps: list[datetime],
        strict: bool,
    ) -> None:
        """Detect and report gaps in the time series."""
        if len(timestamps) < 2:
            return
        
        import loguru
        
        for i in range(1, len(timestamps)):
            delta = timestamps[i] - timestamps[i - 1]
            if delta > timedelta(minutes=self._gap_threshold_minutes):
                msg = (
                    f"Gap detected: {delta} between {timestamps[i-1]} and {timestamps[i]}"
                )
                if strict:
                    raise ValidationError(msg)
                else:
                    loguru.logger.warning(msg)
    
    def _normalize_to_polars(self, base_series: list[NormalizedOHLC]) -> pl.DataFrame:
        """
        Convert NormalizedOHLC list to Polars DataFrame.
        
        Ensures:
        - IST timezone
        - Sorted by timestamp
        - Deduplicated (keep last)
        """
        # Convert to list of dicts for Polars
        data = [
            {
                "timestamp": bar.timestamp,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "open_interest": bar.open_interest,
            }
            for bar in base_series
        ]
        
        df = pl.DataFrame(data)
        
        # Ensure timestamp is datetime with timezone
        df = df.with_columns(
            pl.col("timestamp").dt.replace_time_zone("Asia/Kolkata")
        )
        
        # Sort by timestamp
        df = df.sort("timestamp")
        
        # Deduplicate: keep last occurrence
        df = df.unique(subset=["timestamp"], keep="last", maintain_order=True)
        
        return df
    
    def _resample_timeframe(
        self,
        base_df: pl.DataFrame,
        timeframe: "Interval",
        config: BacktestConfig,
    ) -> list[CandleEvent]:
        """
        Resample base DataFrame to a higher timeframe using Polars group_by_dynamic.
        
        Critical: Event timestamp = bucket END (boundary), not bucket start.
        This ensures the callback fires only after all constituent bars are processed.
        """
        tf_str = timeframe.value
        duration = _interval_to_polars_duration(tf_str)
        
        # Group by dynamic windows
        # closed="left" means intervals like [09:15, 09:20) — 09:20 is the boundary
        # The group key will be the window start; we need the window END as event timestamp
        resampled = base_df.group_by_dynamic(
            "timestamp",
            every=duration,
            closed="left",
            label="left",  # Group key = window start
        ).agg(
            pl.col("open").first().alias("open"),
            pl.col("high").max().alias("high"),
            pl.col("low").min().alias("low"),
            pl.col("close").last().alias("close"),
            pl.col("volume").sum().alias("volume"),
            pl.col("open_interest").last().alias("open_interest"),
        )
        
        # The group key is the window START. Event timestamp = window END (boundary).
        # For a 5min window starting at 09:15, the boundary is 09:20.
        # We compute boundary = start + duration
        resampled = resampled.with_columns(
            (pl.col("timestamp") + pl.duration(**self._parse_duration(duration))).alias("boundary")
        )
        
        # Convert to CandleEvents
        events = []
        for row in resampled.iter_rows(named=True):
            # Create NormalizedOHLC for this resampled candle
            ohlc = NormalizedOHLC(
                symbol=config.symbol,
                exchange=config.exchange,
                segment=config.segment,
                interval=timeframe,
                timestamp=row["boundary"],  # BOUNDARY = candle close time
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
                open_interest=row["open_interest"],
            )
            
            # Context will be filled in by the loop; create placeholder
            # The loop will replace with actual context
            placeholder_context = BacktestContext(
                symbol=config.symbol,
                exchange=config.exchange,
                segment=config.segment,
                base_interval=config.base_interval,
                timeframes=config.timeframes,
                total_bars=0,  # Will be updated by loop
                current_bar_index=0,
                progress_pct=0.0,
            )
            events.append(CandleEvent(
                timestamp=row["boundary"],
                timeframe=timeframe,
                ohlc=ohlc,
                context=placeholder_context,
            ))
        
        return events
    
    def _parse_duration(self, duration: str) -> dict:
        """Parse Polars duration string to kwargs for pl.duration()."""
        # "1m" -> {"minutes": 1}, "1h" -> {"hours": 1}, "1d" -> {"days": 1}
        # "1mo" -> {"months": 1}, "1w" -> {"weeks": 1}
        if duration.endswith("mo"):
            return {"months": int(duration[:-2])}
        if duration.endswith("w"):
            return {"weeks": int(duration[:-1])}
        
        unit = duration[-1]
        value = int(duration[:-1])
        
        mapping = {
            "m": "minutes",
            "h": "hours",
            "d": "days",
        }
        
        return {mapping[unit]: value}
    
    def _merge_and_sort(
        self,
        events: list[CandleEvent],
        base_interval: "Interval",
    ) -> list[CandleEvent]:
        """
        Merge all timeframe events and sort by timestamp.
        
        At same timestamp, base_interval events come FIRST (highest priority).
        This ensures base bars are processed before higher-TF candles at the same boundary.
        """
        # Priority: base_interval = 0 (highest), then by duration ascending
        tf_priority = {base_interval: 0}
        
        # Assign priorities to other timeframes
        other_tfs = [event.timeframe for event in events if event.timeframe != base_interval]
        for i, tf in enumerate(sorted(set(other_tfs), key=lambda x: _interval_to_polars_duration(x.value))):
            tf_priority[tf] = i + 1
        
        # Sort by (timestamp, priority)
        events.sort(key=lambda e: (e.timestamp, tf_priority.get(e.timeframe, 999)))
        
        return events