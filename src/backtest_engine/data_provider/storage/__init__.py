"""
Storage implementations for the data provider layer.

Provides Parquet-based storage with partitioning.
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import polars as pl

from backtest_engine.data_provider.interfaces import (
    ReadResult,
    StorageConfig,
    StorageProtocol,
    WriteResult,
)


class ParquetStorage(StorageProtocol):
    """Parquet-based storage with partitioning support."""
    
    def __init__(self, base_path: Path):
        self.base_path = Path(base_path).expanduser().resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
    
    def _get_partition_path(self, config: StorageConfig, partition: str) -> Path:
        """Get file path for a partition."""
        # Build path: base/provider/exchange/segment/symbol/timeframe/partition.parquet
        path = self.base_path / config.provider / config.exchange / config.segment / config.symbol / config.timeframe
        path.mkdir(parents=True, exist_ok=True)
        return path / f"{partition}.parquet"
    
    def _get_partition_key(self, timestamp: datetime, partition_by: str) -> str:
        """Generate partition key from timestamp."""
        if partition_by == "day":
            return timestamp.strftime("%Y-%m-%d")
        elif partition_by == "month":
            return timestamp.strftime("%Y-%m")
        elif partition_by == "year":
            return timestamp.strftime("%Y")
        else:
            return timestamp.strftime("%Y-%m")
    
    async def write_ohlc(
        self,
        data: pl.DataFrame,
        config: StorageConfig,
        mode: str = "append",
    ) -> WriteResult:
        """Write OHLC data to partitioned Parquet files."""
        async with self._lock:
            if data.is_empty():
                return WriteResult(
                    success=True,
                    rows_written=0,
                    file_path="",
                    partitions=[],
                )
            
            # Ensure timestamp column exists and is datetime
            if "timestamp" not in data.columns:
                return WriteResult(
                    success=False,
                    rows_written=0,
                    file_path="",
                    partitions=[],
                    error="Missing timestamp column",
                )
            
            # Add partition column
            data = data.with_columns([
                pl.col("timestamp").dt.strftime(
                    "%Y-%m" if config.partition_by == "month" else
                    "%Y-%m-%d" if config.partition_by == "day" else
                    "%Y"
                ).alias("_partition")
            ])
            
            partitions_written = []
            total_rows = 0
            
            # Write each partition
            for partition in data["_partition"].unique().to_list():
                partition_data = data.filter(pl.col("_partition") == partition).drop("_partition")
                
                file_path = self._get_partition_path(config, partition)
                
                if mode == "overwrite" or not file_path.exists():
                    partition_data.write_parquet(
                        file_path,
                        compression=config.compression,
                        row_group_size=config.row_group_size,
                    )
                elif mode == "append":
                    # Read existing, combine, deduplicate, write
                    try:
                        existing = pl.read_parquet(file_path)
                        combined = pl.concat([existing, partition_data]).unique(
                            subset=["symbol", "timestamp"],
                            maintain_order=True,
                        ).sort("timestamp")
                        combined.write_parquet(
                            file_path,
                            compression=config.compression,
                            row_group_size=config.row_group_size,
                        )
                    except Exception:
                        partition_data.write_parquet(
                            file_path,
                            compression=config.compression,
                            row_group_size=config.row_group_size,
                        )
                elif mode == "upsert":
                    # Similar to append but with upsert logic
                    try:
                        existing = pl.read_parquet(file_path)
                        # Upsert: update existing timestamps, insert new
                        combined = pl.concat([existing, partition_data]).unique(
                            subset=["symbol", "timestamp"],
                            maintain_order=True,
                            keep="last",
                        ).sort("timestamp")
                        combined.write_parquet(
                            file_path,
                            compression=config.compression,
                            row_group_size=config.row_group_size,
                        )
                    except Exception:
                        partition_data.write_parquet(
                            file_path,
                            compression=config.compression,
                            row_group_size=config.row_group_size,
                        )
                
                partitions_written.append(partition)
                total_rows += partition_data.height
            
            return WriteResult(
                success=True,
                rows_written=total_rows,
                file_path=str(self.base_path),
                partitions=partitions_written,
            )
    
    async def read_ohlc(
        self,
        config: StorageConfig,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        columns: Optional[list[str]] = None,
    ) -> ReadResult:
        """Read OHLC data from partitioned Parquet files."""
        async with self._lock:
            # Build path pattern
            base_path = (
                self.base_path / config.provider / config.exchange / 
                config.segment / config.symbol / config.timeframe
            )
            
            if not base_path.exists():
                return ReadResult(
                    success=True,
                    data=pl.DataFrame(),
                    file_paths=[],
                )
            
            # Determine which partitions to read
            partitions = []
            if from_date and to_date:
                # Generate partition keys in range
                current = from_date
                while current <= to_date:
                    partition = self._get_partition_key(current, config.partition_by)
                    partition_path = base_path / f"{partition}.parquet"
                    if partition_path.exists():
                        partitions.append(partition_path)
                    # Move to next partition
                    if config.partition_by == "day":
                        current = current.replace(day=1) + timedelta(days=32)
                        current = current.replace(day=1)
                    elif config.partition_by == "month":
                        if current.month == 12:
                            current = current.replace(year=current.year + 1, month=1)
                        else:
                            current = current.replace(month=current.month + 1)
                    else:
                        current = current.replace(year=current.year + 1, month=1, day=1)
            else:
                # Read all partitions
                partitions = list(base_path.glob("*.parquet"))
            
            if not partitions:
                return ReadResult(
                    success=True,
                    data=pl.DataFrame(),
                    file_paths=[],
                )
            
            # Read and combine partitions
            dfs = []
            for partition_path in partitions:
                try:
                    df = pl.read_parquet(partition_path, columns=columns)
                    if not df.is_empty():
                        dfs.append(df)
                except Exception:
                    continue
            
            if not dfs:
                return ReadResult(
                    success=True,
                    data=pl.DataFrame(),
                    file_paths=[str(p) for p in partitions],
                )
            
            combined = pl.concat(dfs).sort("timestamp")
            
            # Filter by date range if specified
            if from_date:
                # Ensure from_date is timezone-aware (UTC) for comparison
                if from_date.tzinfo is None:
                    from_date = from_date.replace(tzinfo=timezone.utc)
                combined = combined.filter(pl.col("timestamp") >= from_date)
            if to_date:
                # Ensure to_date is timezone-aware (UTC) for comparison
                if to_date.tzinfo is None:
                    to_date = to_date.replace(tzinfo=timezone.utc)
                combined = combined.filter(pl.col("timestamp") <= to_date)
            
            return ReadResult(
                success=True,
                data=combined,
                file_paths=[str(p) for p in partitions],
            )
    
    async def write_instruments(
        self,
        data: pl.DataFrame,
        provider: str,
        exchange: str,
        segment: str,
    ) -> WriteResult:
        """Write instrument master data."""
        async with self._lock:
            path = (
                self.base_path / "instruments" / provider / exchange / segment
            )
            path.mkdir(parents=True, exist_ok=True)
            
            file_path = path / "instruments.parquet"
            
            data.write_parquet(
                file_path,
                compression="zstd",
            )
            
            return WriteResult(
                success=True,
                rows_written=data.height,
                file_path=str(file_path),
                partitions=[str(file_path)],
            )
    
    async def read_instruments(
        self,
        provider: str,
        exchange: str,
        segment: str,
    ) -> ReadResult:
        """Read instrument master data."""
        async with self._lock:
            file_path = (
                self.base_path / "instruments" / provider / exchange / segment / "instruments.parquet"
            )
            
            if not file_path.exists():
                return ReadResult(
                    success=True,
                    data=pl.DataFrame(),
                    file_paths=[],
                )
            
            try:
                data = pl.read_parquet(file_path)
                return ReadResult(
                    success=True,
                    data=data,
                    file_paths=[str(file_path)],
                )
            except Exception as e:
                return ReadResult(
                    success=False,
                    data=None,
                    file_paths=[str(file_path)],
                    error=str(e),
                )
    
    async def list_partitions(self, config: StorageConfig) -> list[str]:
        """List available partitions."""
        async with self._lock:
            base_path = (
                self.base_path / config.provider / config.exchange / 
                config.segment / config.symbol / config.timeframe
            )
            
            if not base_path.exists():
                return []
            
            return [p.stem for p in base_path.glob("*.parquet")]
    
    async def delete_partition(self, config: StorageConfig, partition: str) -> bool:
        """Delete a specific partition."""
        async with self._lock:
            file_path = self._get_partition_path(config, partition)
            if file_path.exists():
                file_path.unlink()
                return True
            return False
    
    async def get_storage_stats(self, config: StorageConfig) -> dict:
        """Get storage statistics."""
        async with self._lock:
            base_path = (
                self.base_path / config.provider / config.exchange / 
                config.segment / config.symbol / config.timeframe
            )
            
            if not base_path.exists():
                return {
                    "provider": config.provider,
                    "symbol": config.symbol,
                    "partitions": 0,
                    "total_rows": 0,
                    "total_size_bytes": 0,
                }
            
            partitions = list(base_path.glob("*.parquet"))
            total_size = sum(p.stat().st_size for p in partitions)
            total_rows = 0
            
            for p in partitions:
                try:
                    df = pl.read_parquet(p, columns=["timestamp"])
                    total_rows += df.height
                except Exception:
                    pass
            
            return {
                "provider": config.provider,
                "symbol": config.symbol,
                "partitions": len(partitions),
                "total_rows": total_rows,
                "total_size_bytes": total_size,
            }