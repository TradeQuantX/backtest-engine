"""
Provider interface/protocol for data providers.

All data providers must implement this protocol.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from backtest_engine.data_provider.interfaces.models import (
    HistoricalDataRequest,
    HistoricalDataResponse,
    NormalizedInstrument,
    NormalizedOHLC,
)


class DataProviderProtocol(ABC):
    """
    Abstract base class for all data providers.
    
    Providers must implement all methods to be compatible with the framework.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique provider name (e.g., 'zerodha', 'dhan')."""
        ...
    
    @property
    @abstractmethod
    def supported_exchanges(self) -> list[str]:
        """List of supported exchange codes."""
        ...
    
    @property
    @abstractmethod
    def supported_intervals(self) -> list[str]:
        """List of supported interval strings."""
        ...
    
    @abstractmethod
    async def authenticate(self) -> bool:
        """
        Authenticate with the provider.
        
        Returns:
            True if authentication successful, False otherwise.
        """
        ...
    
    @abstractmethod
    async def is_authenticated(self) -> bool:
        """Check if currently authenticated."""
        ...
    
    @abstractmethod
    async def get_instruments(
        self,
        exchange: Optional[str] = None,
        segment: Optional[str] = None,
        force_refresh: bool = False,
    ) -> list[NormalizedInstrument]:
        """
        Get instrument master from provider.
        
        Args:
            exchange: Filter by exchange (optional)
            segment: Filter by segment (optional)
            force_refresh: Force download even if cached
            
        Returns:
            List of normalized instruments.
        """
        ...
    
    @abstractmethod
    async def get_historical_data(
        self,
        request: HistoricalDataRequest,
    ) -> HistoricalDataResponse:
        """
        Get historical OHLC data.
        
        Args:
            request: Historical data request parameters
            
        Returns:
            Historical data response with normalized OHLC data.
        """
        ...
    
    @abstractmethod
    async def get_instrument_token(
        self,
        symbol: str,
        exchange: str,
        segment: str,
        expiry: Optional[datetime] = None,
        strike: Optional[float] = None,
        instrument_type: Optional[str] = None,
    ) -> Optional[str]:
        """
        Get provider-specific instrument token for a symbol.
        
        Args:
            symbol: Trading symbol
            exchange: Exchange code
            segment: Market segment
            expiry: Expiry date for derivatives
            strike: Strike price for options
            instrument_type: Instrument type (EQ, FUT, OPT, etc.)
            
        Returns:
            Provider-specific instrument token or None if not found.
        """
        ...
    
    @abstractmethod
    async def close(self) -> None:
        """Close any open connections/sessions."""
        ...
    
    @abstractmethod
    def get_rate_limit_info(self) -> dict:
        """Get current rate limit status."""
        ...