"""
Provider registry for auto-discovery and registration.

Providers register themselves via entry points or explicit registration.
"""

from abc import ABC, abstractmethod
from typing import Optional

from backtest_engine.data_provider.config import ProviderConfig
from backtest_engine.data_provider.interfaces import DataProviderProtocol
from backtest_engine.data_provider.providers.base import BaseProvider


class ProviderRegistry:
    """Registry for data providers."""
    
    _providers: dict[str, type[BaseProvider]] = {}
    _instances: dict[str, BaseProvider] = {}
    
    @classmethod
    def register(cls, provider_class: type[BaseProvider]) -> None:
        """Register a provider class."""
        # Create temporary instance to get name
        instance = provider_class.__new__(provider_class)
        name = instance.name
        cls._providers[name] = provider_class
    
    @classmethod
    def unregister(cls, name: str) -> None:
        """Unregister a provider."""
        cls._providers.pop(name, None)
        cls._instances.pop(name, None)
    
    @classmethod
    def get_provider_class(cls, name: str) -> Optional[type[BaseProvider]]:
        """Get provider class by name."""
        return cls._providers.get(name)
    
    @classmethod
    def get_all_providers(cls) -> dict[str, type[BaseProvider]]:
        """Get all registered providers."""
        return cls._providers.copy()
    
    @classmethod
    def create_provider(
        cls,
        name: str,
        config: ProviderConfig,
        global_config,
        cache=None,
        storage=None,
    ) -> Optional[BaseProvider]:
        """Create provider instance."""
        provider_class = cls.get_provider_class(name)
        if not provider_class:
            return None
        
        if name in cls._instances:
            return cls._instances[name]
        
        instance = provider_class(config, global_config, cache, storage)
        cls._instances[name] = instance
        return instance
    
    @classmethod
    def get_instance(cls, name: str) -> Optional[BaseProvider]:
        """Get existing provider instance."""
        return cls._instances.get(name)
    
    @classmethod
    def clear_instances(cls) -> None:
        """Clear all instances (for testing)."""
        cls._instances.clear()


def register_provider(provider_class: type[BaseProvider]) -> type[BaseProvider]:
    """Decorator to register a provider."""
    ProviderRegistry.register(provider_class)
    return provider_class