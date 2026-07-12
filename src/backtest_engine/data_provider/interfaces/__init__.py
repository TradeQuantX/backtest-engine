"""
Interfaces package for data provider layer.

This package contains abstract base classes and protocols that define
the contracts for providers, authentication, caching, and storage.
"""

from .auth import (
    AuthConfig,
    AuthProviderProtocol,
    DhanAuthConfig,
    ZerodhaAuthConfig,
)
from .cache import CacheEntry, CacheProtocol
from .models import (
    Exchange,
    HistoricalDataRequest,
    HistoricalDataResponse,
    InstrumentType,
    Interval,
    NormalizedInstrument,
    NormalizedOHLC,
    Segment,
)
from .provider import DataProviderProtocol
from .storage import ReadResult, StorageConfig, StorageProtocol, WriteResult

__all__ = [
    # Auth
    "AuthConfig",
    "AuthProviderProtocol",
    "ZerodhaAuthConfig",
    "DhanAuthConfig",
    # Cache
    "CacheEntry",
    "CacheProtocol",
    # Models
    "Exchange",
    "Segment",
    "Interval",
    "InstrumentType",
    "NormalizedOHLC",
    "NormalizedInstrument",
    "HistoricalDataRequest",
    "HistoricalDataResponse",
    # Provider
    "DataProviderProtocol",
    # Storage
    "StorageConfig",
    "StorageProtocol",
    "WriteResult",
    "ReadResult",
]