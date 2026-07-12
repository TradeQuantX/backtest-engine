"""
Data-related exceptions.
"""

from typing import Optional

from backtest_engine.data_provider.exceptions.base import DataProviderError


class DataError(DataProviderError):
    """Base data error."""
    pass


class DataNotFoundError(DataError):
    """Requested data not found."""
    
    def __init__(
        self,
        message: str,
        symbol: Optional[str] = None,
        exchange: Optional[str] = None,
        interval: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.symbol = symbol
        self.exchange = exchange
        self.interval = interval
        self.from_date = from_date
        self.to_date = to_date


class DataCorruptionError(DataError):
    """Data file corruption detected."""
    
    def __init__(
        self,
        message: str,
        file_path: Optional[str] = None,
        expected_checksum: Optional[str] = None,
        actual_checksum: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.file_path = file_path
        self.expected_checksum = expected_checksum
        self.actual_checksum = actual_checksum


class ValidationError(DataError):
    """Data validation failed."""
    
    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Optional[str] = None,
        expected: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.field = field
        self.value = value
        self.expected = expected


class SchemaMismatchError(DataError):
    """Data schema doesn't match expected format."""
    pass


class InsufficientDataError(DataError):
    """Not enough data points for the requested operation."""
    pass