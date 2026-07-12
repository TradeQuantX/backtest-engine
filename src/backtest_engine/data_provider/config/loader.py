"""
Configuration loader with priority-based merging.

Priority (highest to lowest):
1. Environment variables
2. ~/.tradex/config.yml
3. ./config.yml
"""

import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

import yaml

from backtest_engine.data_provider.config.models import (
    DataProviderConfig,
    DhanConfig,
    ProviderConfig,
    ZerodhaConfig,
)


class ConfigLoader:
    """Loads and merges configuration from multiple sources."""
    
    ENV_PREFIX = "TRADEX_"
    
    def __init__(
        self,
        project_config: Optional[Path] = None,
        user_config: Optional[Path] = None,
    ):
        self.project_config = project_config or Path.cwd() / "config.yml"
        self.user_config = user_config or Path.home() / ".tradex" / "config.yml"
        self._config: Optional[DataProviderConfig] = None
        self._providers: dict[str, ProviderConfig] = {}
    
    def load(self) -> DataProviderConfig:
        """Load configuration from all sources with priority merging."""
        # Start with defaults
        config_dict = asdict(DataProviderConfig())
        
        # Load project config
        if self.project_config.exists():
            project_data = self._load_yaml(self.project_config)
            config_dict = self._deep_merge(config_dict, project_data)
        
        # Load user config
        if self.user_config.exists():
            user_data = self._load_yaml(self.user_config)
            config_dict = self._deep_merge(config_dict, user_data)
        
        # Load environment variables (highest priority)
        env_data = self._load_env()
        config_dict = self._deep_merge(config_dict, env_data)
        
        # Parse provider configs
        providers_data = config_dict.pop("providers", {})
        self._providers = self._parse_providers(providers_data)
        
        # Create final config with providers
        config_dict["providers"] = self._providers
        self._config = DataProviderConfig(**config_dict)
        return self._config
    
    def get_provider_config(self, name: str) -> Optional[ProviderConfig]:
        """Get configuration for a specific provider."""
        return self._providers.get(name)
    
    def get_all_providers(self) -> dict[str, ProviderConfig]:
        """Get all provider configurations."""
        return self._providers.copy()
    
    def _load_yaml(self, path: Path) -> dict[str, Any]:
        """Load YAML file."""
        if not path.exists():
            return {}
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return data
    
    def _load_env(self) -> dict[str, Any]:
        """Load configuration from environment variables."""
        config = {}
        
        for key, value in os.environ.items():
            if not key.startswith(self.ENV_PREFIX):
                continue
            
            # Convert TRADEX_PROVIDER_ZERODHA_API_KEY -> providers.zerodha.api_key
            parts = key[len(self.ENV_PREFIX):].lower().split("_")
            if not parts:
                continue
            
            self._set_nested(config, parts, value)
        
        return config
    
    def _set_nested(self, d: dict, parts: list[str], value: str) -> None:
        """Set nested dictionary value from path parts."""
        current = d
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        
        # Try to convert value
        current[parts[-1]] = self._convert_value(value)
    
    def _convert_value(self, value: str) -> Any:
        """Convert string value to appropriate type."""
        # Boolean
        if value.lower() in ("true", "false"):
            return value.lower() == "true"
        
        # Integer
        try:
            return int(value)
        except ValueError:
            pass
        
        # Float
        try:
            return float(value)
        except ValueError:
            pass
        
        # List (comma-separated)
        if "," in value:
            return [v.strip() for v in value.split(",")]
        
        return value
    
    def _deep_merge(self, base: dict, override: dict) -> dict:
        """Deep merge two dictionaries."""
        result = base.copy()
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def _parse_providers(self, providers_data: dict) -> dict[str, ProviderConfig]:
        """Parse provider configurations."""
        providers = {}
        
        for name, data in providers_data.items():
            if not data.get("enabled", True):
                continue
            
            provider_type = data.get("type", name)
            
            if provider_type == "zerodha":
                providers[name] = ZerodhaConfig(**data)
            elif provider_type == "dhan":
                providers[name] = DhanConfig(**data)
            else:
                providers[name] = ProviderConfig(name=name, **data)
        
        return providers


def load_config(
    project_config: Optional[Path] = None,
    user_config: Optional[Path] = None,
) -> DataProviderConfig:
    """Convenience function to load configuration."""
    loader = ConfigLoader(project_config, user_config)
    return loader.load()