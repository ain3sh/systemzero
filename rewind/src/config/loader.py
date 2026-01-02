"""Configuration loader for Rewind.

Handles loading and merging configuration from multiple sources.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, cast

from ..utils.env import get_global_rewind_dir
from ..utils.fs import safe_json_load
from ..utils.resources import read_json_resource, resource_exists
from .types import IgnoreConfig, RewindConfig, TierConfig


TierName = Literal["minimal", "balanced", "aggressive"]


def _coerce_tier(val: object, default: TierName = "balanced") -> TierName:
    if isinstance(val, str) and val in {"minimal", "balanced", "aggressive"}:
        return cast(TierName, val)
    return default


class ConfigLoader:
    """Loads and manages Rewind configuration."""
    
    def __init__(self, project_root: Path | None = None):
        """Initialize config loader.
        
        Args:
            project_root: Project root directory (for project-local config)
        """
        self.project_root = project_root
        self._config: RewindConfig | None = None
    
    @property
    def config(self) -> RewindConfig:
        """Get loaded configuration, loading if necessary."""
        if self._config is None:
            self._config = self.load()
        return self._config
    
    def load(self) -> RewindConfig:
        """Load configuration from all sources.
        
        Priority (highest to lowest):
        1. Project-local config (.agent/rewind/config.json)
        2. Global config (~/.rewind/config.json)
        3. Default values
        
        Returns:
            Merged RewindConfig
        """
        # Start with defaults
        merged: dict[str, Any] = {}
        
        # Load global config
        global_config_path = get_global_rewind_dir() / "config.json"
        if global_config_path.exists():
            global_data = safe_json_load(global_config_path, {})
            merged = self._deep_merge(merged, global_data)
        
        # Load project config (overrides global)
        if self.project_root:
            project_config_path = self.project_root / ".agent" / "rewind" / "config.json"
            if project_config_path.exists():
                project_data = safe_json_load(project_config_path, {})
                merged = self._deep_merge(merged, project_data)
        
        return RewindConfig.from_dict(merged)
    
    def reload(self) -> RewindConfig:
        """Force reload configuration."""
        self._config = None
        return self.config
    
    def load_tier_config(self, tier_name: str | None = None) -> TierConfig:
        """Load tier configuration.
        
        If tier_name is provided, loads from tier file.
        Otherwise, loads from global config's runtime section.
        
        Args:
            tier_name: Name of tier (minimal, balanced, aggressive), or None to use global config
            
        Returns:
            TierConfig for the specified tier
        """
        tier: TierName

        # If no tier specified, try to get from global config
        if tier_name is None:
            global_config_path = get_global_rewind_dir() / "config.json"
            if global_config_path.exists():
                global_data = safe_json_load(global_config_path, {})
                tier = _coerce_tier(global_data.get("tier"), "balanced")
                # If global config has runtime section, use it directly
                if "runtime" in global_data:
                    return TierConfig.from_dict({
                        "tier": tier,
                        **global_data["runtime"]
                    })
            else:
                tier = "balanced"
        else:
            tier = _coerce_tier(tier_name, "balanced")

        # Try bundled tier JSON first.
        if resource_exists("schemas", "tiers", f"{tier}.json"):
            data = read_json_resource("schemas", "tiers", f"{tier}.json")
            # New format has runtime nested
            if "runtime" in data:
                return TierConfig.from_dict({
                    "tier": _coerce_tier(data.get("tier"), tier),
                    **data["runtime"]
                })
            return TierConfig.from_dict(data)
        
        # Try installed system tiers
        system_path = get_global_rewind_dir() / "system" / "tiers" / f"{tier}.json"
        if system_path.exists():
            data = safe_json_load(system_path, {})
            if "runtime" in data:
                return TierConfig.from_dict({
                    "tier": _coerce_tier(data.get("tier"), tier),
                    **data["runtime"]
                })
            return TierConfig.from_dict(data)
        
        # Return default
        return TierConfig(tier=tier)
    
    def load_ignore_config(self) -> IgnoreConfig:
        """Load ignore patterns configuration.
        
        Returns:
            IgnoreConfig with merged patterns
        """
        # Try installed system config first (most up-to-date after install)
        system_path = get_global_rewind_dir() / "system" / "rewind-checkpoint-ignore.json"
        if system_path.exists():
            data = safe_json_load(system_path, {})
            return IgnoreConfig.from_dict(data)

        # Try bundled config in package resources.
        if resource_exists("schemas", "rewind-checkpoint-ignore.json"):
            data = read_json_resource("schemas", "rewind-checkpoint-ignore.json")
            return IgnoreConfig.from_dict(data)
        
        # Return default
        return IgnoreConfig()
    
    def save_config(self, config: RewindConfig, scope: str = "project") -> Path:
        """Save configuration to file.
        
        Args:
            config: Configuration to save
            scope: "project" or "global"
            
        Returns:
            Path where config was saved
        """
        data = {
            "storage": {
                "mode": config.storage_mode.value
            }
        }
        
        if scope == "global":
            config_path = get_global_rewind_dir() / "config.json"
        else:
            if not self.project_root:
                raise ValueError("No project root set for project-scope config")
            config_path = self.project_root / ".agent" / "rewind" / "config.json"
        
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(data, f, indent=2)
        
        return config_path
    
    @staticmethod
    def _deep_merge(base: dict, override: dict) -> dict:
        """Deep merge two dictionaries.
        
        Args:
            base: Base dictionary
            override: Dictionary to merge (takes precedence)
            
        Returns:
            Merged dictionary
        """
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = ConfigLoader._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
