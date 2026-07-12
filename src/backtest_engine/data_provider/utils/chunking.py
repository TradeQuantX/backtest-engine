"""
Request chunking utilities for historical data.

Handles splitting large date ranges into provider-compatible chunks.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from backtest_engine.data_provider.interfaces.models import Interval


@dataclass(frozen=True, slots=True)
class DateChunk:
    """A single date range chunk."""
    from_date: datetime
    to_date: datetime
    chunk_index: int
    total_chunks: int


@dataclass(frozen=True, slots=True)
class ChunkingConfig:
    """Configuration for chunking behavior."""
    # Max days per chunk by interval
    max_days_per_interval: dict[str, int] = None
    
    def __post_init__(self):
        if self.max_days_per_interval is None:
            object.__setattr__(self, "max_days_per_interval", {
                "minute": 30,
                "3minute": 60,
                "5minute": 90,
                "10minute": 120,
                "15minute": 180,
                "30minute": 360,
                "60minute": 720,
                "day": 2000,
                "week": 2000,
                "month": 2000,
            })


DEFAULT_CHUNKING_CONFIG = ChunkingConfig()


def chunk_date_range(
    from_date: datetime,
    to_date: datetime,
    interval: Interval,
    config: ChunkingConfig = None,
) -> list[DateChunk]:
    """
    Split a date range into chunks based on interval limits.
    
    Args:
        from_date: Start date (inclusive)
        to_date: End date (inclusive)
        interval: Data interval
        config: Chunking configuration
        
    Returns:
        List of DateChunk objects
    """
    config = config or DEFAULT_CHUNKING_CONFIG
    interval_key = interval.value if hasattr(interval, "value") else str(interval)
    max_days = config.max_days_per_interval.get(interval_key, 30)
    
    chunks = []
    current_start = from_date
    chunk_index = 0
    
    while current_start <= to_date:
        # Calculate chunk end
        chunk_end = min(
            current_start + timedelta(days=max_days - 1),
            to_date,
        )
        
        chunks.append(DateChunk(
            from_date=current_start,
            to_date=chunk_end,
            chunk_index=chunk_index,
            total_chunks=0,  # Will be updated after loop
        ))
        
        current_start = chunk_end + timedelta(days=1)
        chunk_index += 1
    
    # Update total_chunks
    total = len(chunks)
    chunks = [
        DateChunk(
            from_date=c.from_date,
            to_date=c.to_date,
            chunk_index=c.chunk_index,
            total_chunks=total,
        )
        for c in chunks
    ]
    
    return chunks


def get_max_days_for_interval(interval: Interval, config: ChunkingConfig = None) -> int:
    """Get maximum days allowed for a single request at given interval."""
    config = config or DEFAULT_CHUNKING_CONFIG
    interval_key = interval.value if hasattr(interval, "value") else str(interval)
    return config.max_days_per_interval.get(interval_key, 30)


def estimate_chunks(
    from_date: datetime,
    to_date: datetime,
    interval: Interval,
    config: ChunkingConfig = None,
) -> int:
    """Estimate number of chunks needed for a date range."""
    config = config or DEFAULT_CHUNKING_CONFIG
    interval_key = interval.value if hasattr(interval, "value") else str(interval)
    max_days = config.max_days_per_interval.get(interval_key, 30)
    
    total_days = (to_date - from_date).days + 1
    return (total_days + max_days - 1) // max_days  # Ceiling division


def merge_chunks(chunks: list[DateChunk]) -> list[DateChunk]:
    """Merge adjacent/overlapping chunks."""
    if not chunks:
        return []
    
    # Sort by from_date
    sorted_chunks = sorted(chunks, key=lambda c: c.from_date)
    merged = [sorted_chunks[0]]
    
    for chunk in sorted_chunks[1:]:
        last = merged[-1]
        # If adjacent or overlapping, merge
        if chunk.from_date <= last.to_date + timedelta(days=1):
            merged[-1] = DateChunk(
                from_date=last.from_date,
                to_date=max(last.to_date, chunk.to_date),
                chunk_index=last.chunk_index,
                total_chunks=0,  # Will recalculate
            )
        else:
            merged.append(chunk)
    
    # Recalculate indices and total
    total = len(merged)
    return [
        DateChunk(
            from_date=c.from_date,
            to_date=c.to_date,
            chunk_index=i,
            total_chunks=total,
        )
        for i, c in enumerate(merged)
    ]