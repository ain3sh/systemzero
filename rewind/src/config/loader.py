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


PresetName = Literal["minimal", "balanced", "aggressive"]


def _coerce_preset(val: object, default: PresetName = "balanced") -> PresetName:
    if isinstance(val, str) and val in {"minimal", "balanced", "aggressive"}:
        return cast(PresetName, val)
    return default


def _read_preset_definition(preset: PresetName) -> dict[str, Any]:
    if resource_exists("schemas", "tiers", f"{preset}.json"):
        data = read_json_resource("schemas", "tiers", f"{preset}.json")
        return data if isinstance(data, dict) else {}

    # Installed system fallback.
    system_path = get_global_rewind_dir() / "system" / "src" / "schemas" / "tiers" / f"{preset}.json"
    if system_path.exists():
        data = safe_json_load(system_path, {})
        return data if isinstance(data, dict) else {}

    return {}


def _extract_runtime_overrides(config: dict[str, Any]) -> dict[str, Any]:
    runtime = config.get("runtime", {})
    return runtime if isinstance(runtime, dict) else {}


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
        
        # Resolve preset + runtime.
        preset = _coerce_preset(merged.get("preset"), "balanced")

        preset_def = _read_preset_definition(preset)
        preset_runtime = preset_def.get("runtime", {}) if isinstance(preset_def.get("runtime"), dict) else {}
        runtime_overrides = _extract_runtime_overrides(merged)
        effective_runtime = self._deep_merge(preset_runtime, runtime_overrides)

        tier_config = TierConfig.from_dict(
            {
                "tier": preset,
                "description": preset_def.get("description", "") if isinstance(preset_def.get("description"), str) else "",
                **effective_runtime,
            }
        )

        storage_data = merged.get("storage", {})
        storage_mode_str = storage_data.get("mode", "project") if isinstance(storage_data, dict) else "project"

        ignore_config = IgnoreConfig.from_dict(merged.get("ignore", {}))

        storage_mode = RewindConfig().storage_mode
        if isinstance(storage_mode_str, str) and storage_mode_str in {"project", "global"}:
            storage_mode = RewindConfig.from_dict({"storage": {"mode": storage_mode_str}}).storage_mode

        return RewindConfig(
            storage_mode=storage_mode,
            tier=tier_config,
            ignore=ignore_config,
        )
    
    def reload(self) -> RewindConfig:
        """Force reload configuration."""
        self._config = None
        return self.config
    
    def load_tier_config(self, preset_name: str | None = None) -> TierConfig:
        """Load effective runtime configuration.

        If preset_name is provided, loads preset defaults only.
        Otherwise, uses global config (`~/.rewind/config.json`) to load:
        - `preset` (required for selection; defaults to balanced if missing)
        - `runtime` overrides merged on top of preset runtime
        """
        if preset_name is None:
            global_config_path = get_global_rewind_dir() / "config.json"
            global_data = safe_json_load(global_config_path, {}) if global_config_path.exists() else {}
            preset = _coerce_preset(global_data.get("preset"), "balanced")
            overrides = _extract_runtime_overrides(global_data)
        else:
            preset = _coerce_preset(preset_name, "balanced")
            overrides = {}

        preset_def = _read_preset_definition(preset)
        preset_runtime = preset_def.get("runtime", {}) if isinstance(preset_def.get("runtime"), dict) else {}
        effective_runtime = self._deep_merge(preset_runtime, overrides)

        return TierConfig.from_dict(
            {
                "tier": preset,
                "description": preset_def.get("description", "") if isinstance(preset_def.get("description"), str) else "",
                **effective_runtime,
            }
        )
    
    def load_ignore_config(self) -> IgnoreConfig:
        """Load ignore patterns configuration.
        
        Returns:
            IgnoreConfig with merged patterns
        """
        # Try installed system config first (most up-to-date after install)
        system_path = get_global_rewind_dir() / "system" / "src" / "schemas" / "rewind-checkpoint-ignore.json"
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
