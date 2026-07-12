"""
Storage interface for data persistence.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
import polars as pl


@dataclass(frozen=True, slots=True)
class StorageConfig:
    """Storage configuration."""
    base_path: str
    provider: str
    exchange: str
    segment: str
    symbol: str
    timeframe: str
    partition_by: str = "month"  # month, day, year
    compression: str = "zstd"
    row_group_size: int = 1_000_000


@dataclass(frozen=True, slots=True)
class WriteResult:
    """Result of a write operation."""
    success: bool
    rows_written: int
    file_path: str
    partitions: list[str]
    error: Optional[str] = None


@dataclass(frozen=True, slots=True)
class ReadResult:
    """Result of a read operation."""
    success: bool
    data: Optional[pl.DataFrame]
    file_paths: list[str]
    error: Optional[str] = None


class StorageProtocol(ABC):
    """Abstract base class for storage implementations."""
    
    @abstractmethod
    async def write_ohlc(
        self,
        data: pl.DataFrame,
        config: StorageConfig,
        mode: str = "append",  # append, overwrite, upsert
    ) -> WriteResult:
        """
        Write OHLC data to storage.
        
        Args:
            data: Polars DataFrame with OHLC data
            config: Storage configuration
            mode: Write mode
            
        Returns:
            WriteResult with details
        """
        ...
    
    @abstractmethod
    async def read_ohlc(
        self,
        config: StorageConfig,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        columns: Optional[list[str]] = None,
    ) -> ReadResult:
        """
        Read OHLC data from storage.
        
        Args:
            config: Storage configuration
            from_date: Start date filter
            to_date: End date filter
            columns: Columns to read (None = all)
            
        Returns:
            ReadResult with data
        """
        ...
    
    @abstractmethod
    async def write_instruments(
        self,
        data: pl.DataFrame,
        provider: str,
        exchange: str,
        segment: str,
    ) -> WriteResult:
        """Write instrument master data."""
        ...
    
    @abstractmethod
    async def read_instruments(
        self,
        provider: str,
        exchange: str,
        segment: str,
    ) -> ReadResult:
        """Read instrument master data."""
        ...
    
    @abstractmethod
    async def list_partitions(self, config: StorageConfig) -> list[str]:
        """List available partitions for a config."""
        ...
    
    @abstractmethod
    async def delete_partition(self, config: StorageConfig, partition: str) -> bool:
        """Delete a specific partition."""
        ...
    
    @abstractmethod
    async def get_storage_stats(self, config: StorageConfig) -> dict:
        """Get storage statistics."""
        ...