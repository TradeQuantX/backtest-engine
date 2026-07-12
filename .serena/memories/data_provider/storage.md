# Storage Module

## Location
`src/backtest_engine/data_provider/storage/`

## ParquetStorage
- Partitioned Parquet files with ZSTD compression
- Monthly partitions by default (configurable: day/week/month/year)
- Append/overwrite/upsert modes
- Polars + PyArrow backend

## Partition Strategy
```
{base_path}/{provider}/{exchange}/{segment}/{symbol}/{interval}/{partition}.parquet
Example: ~/.tradex/data/zerodha/NSE/EQ/RELIANCE/minute/2024-01.parquet
```

### Partition Formats
- `month`: `YYYY-MM.parquet` (default)
- `day`: `YYYY-MM-DD.parquet`
- `week`: `YYYY-WW.parquet`
- `year`: `YYYY.parquet`

## Schema
```python
# Polars schema
{
    "timestamp": Datetime("us"),
    "open": Decimal(18, 4),
    "high": Decimal(18, 4),
    "low": Decimal(18, 4),
    "close": Decimal(18, 4),
    "volume": Int64,
    "symbol": String,
    "exchange": String,
    "segment": String,
    "interval": String,
    "provider": String
}
```

## Write Modes
- `append`: Add new data, keep existing (default)
- `overwrite`: Replace partition entirely
- `upsert`: Merge on timestamp (deduplicate)

```python
storage = ParquetStorage(base_path="~/.tradex/data", partition_by="month")

# Write
await storage.write(
    data=normalized_ohlc_list,
    provider="zerodha",
    exchange="NSE",
    segment="EQ",
    symbol="RELIANCE",
    interval="minute",
    mode="append"
)

# Read
df = await storage.read(
    provider="zerodha",
    exchange="NSE",
    segment="EQ",
    symbol="RELIANCE",
    interval="minute",
    from_date="2024-01-01",
    to_date="2024-01-31"
)

# Read all partitions for symbol
df = await storage.read_symbol(
    provider="zerodha",
    exchange="NSE",
    segment="EQ",
    symbol="RELIANCE",
    interval="minute"
)
```

## Compression
- Default: `zstd` (level 3)
- Options: `snappy`, `gzip`, `lz4`, `zstd`, `none`

## Performance
- Partition pruning on date range queries
- Columnar storage for fast column selection
- Predicate pushdown with Polars lazy API