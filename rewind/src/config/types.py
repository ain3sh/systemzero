"""Configuration schemas for Rewind.

Defines dataclasses for all configuration structures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class StorageMode(str, Enum):
    """Where checkpoints are stored."""
    PROJECT = "project"  # .agent/rewind/ in project root
    GLOBAL = "global"    # ~/.rewind/storage/


@dataclass
class AntiSpamConfig:
    """Anti-spam settings to prevent checkpoint flooding."""
    enabled: bool = True
    min_interval_seconds: int = 30


@dataclass
class SignificanceConfig:
    """Settings for determining if changes are significant enough to checkpoint."""
    enabled: bool = True
    min_change_size: int = 50  # bytes
    critical_files: list[str] = field(default_factory=lambda: [
        "package.json",
        "requirements.txt",
        "Dockerfile",
        "docker-compose.yml",
        "tsconfig.json",
        "pyproject.toml",
        "Cargo.toml",
        "go.mod",
        "*.config.js",
        "*.config.ts",
    ])


@dataclass
class TierConfig:
    """Configuration tier settings."""
    tier: Literal["minimal", "balanced", "aggressive"] = "balanced"
    description: str = ""
    anti_spam: AntiSpamConfig = field(default_factory=AntiSpamConfig)
    significance: SignificanceConfig = field(default_factory=SignificanceConfig)
    
    @classmethod
    def from_dict(cls, data: dict) -> TierConfig:
        """Create TierConfig from dictionary."""
        anti_spam_data = data.get("antiSpam", {})
        significance_data = data.get("significance", {})

        tier_val = data.get("tier", "balanced")
        tier: Literal["minimal", "balanced", "aggressive"] = "balanced"
        if isinstance(tier_val, str) and tier_val in {"minimal", "balanced", "aggressive"}:
            tier = tier_val
        
        return cls(
            tier=tier,
            description=data.get("description", ""),
            anti_spam=AntiSpamConfig(
                enabled=anti_spam_data.get("enabled", True),
                min_interval_seconds=anti_spam_data.get("minIntervalSeconds", 30),
            ),
            significance=SignificanceConfig(
                enabled=significance_data.get("enabled", True),
                min_change_size=significance_data.get("minChangeSize", 50),
                critical_files=significance_data.get("criticalFiles", SignificanceConfig().critical_files),
            ),
        )


@dataclass
class IgnoreConfig:
    """Patterns for files to ignore during checkpointing."""
    patterns: list[str] = field(default_factory=lambda: [
        ".git",
        ".agent",
        ".claude",
        ".factory",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        "dist",
        "build",
        "coverage",
        "out",
        "tmp",
        "temp",
        "*.log",
        "*.tmp",
        "*.pyc",
        ".cache",
        ".next",
        ".nuxt",
        "*.swp",
        "*.bak",
        ".venv",
        "venv",
        ".env",
    ])
    additional_ignores: list[str] = field(default_factory=list)
    force_include: list[str] = field(default_factory=lambda: [
        ".env.example",
    ])
    
    @classmethod
    def from_dict(cls, data: dict) -> IgnoreConfig:
        """Create IgnoreConfig from dictionary."""
        return cls(
            patterns=data.get("ignorePatterns", cls().patterns),
            additional_ignores=data.get("additionalIgnores", []),
            force_include=data.get("forceInclude", []),
        )
    
    def should_ignore(self, path: str) -> bool:
        """Check if a path should be ignored.
        
        Args:
            path: Relative path to check
            
        Returns:
            True if path should be ignored
        """
        import fnmatch
        
        # Check force include first
        for pattern in self.force_include:
            if fnmatch.fnmatch(path, pattern):
                return False
        
        # Check ignore patterns
        all_patterns = self.patterns + self.additional_ignores
        for pattern in all_patterns:
            if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(path, f"*/{pattern}") or fnmatch.fnmatch(path, f"{pattern}/*"):
                return True
            # Also check if any path component matches
            parts = path.split("/")
            for part in parts:
                if fnmatch.fnmatch(part, pattern):
                    return True
        
        return False


@dataclass
class RewindConfig:
    """Main Rewind configuration."""
    storage_mode: StorageMode = StorageMode.PROJECT
    tier: TierConfig = field(default_factory=TierConfig)
    ignore: IgnoreConfig = field(default_factory=IgnoreConfig)
    
    @classmethod
    def from_dict(cls, data: dict) -> RewindConfig:
        """Create RewindConfig from dictionary.

        Note: Preset resolution (merging preset defaults with runtime overrides)
        is handled by ConfigLoader. This method parses only local values.
        """
        storage_data = data.get("storage", {})
        mode_str = storage_data.get("mode", "project")

        preset_val = data.get("preset")
        preset: Literal["minimal", "balanced", "aggressive"] = "balanced"
        if isinstance(preset_val, str) and preset_val in {"minimal", "balanced", "aggressive"}:
            preset = preset_val

        runtime_overrides = data.get("runtime", {})
        runtime_dict = runtime_overrides if isinstance(runtime_overrides, dict) else {}

        return cls(
            storage_mode=StorageMode(mode_str) if mode_str in ("project", "global") else StorageMode.PROJECT,
            tier=TierConfig.from_dict({"tier": preset, **runtime_dict}),
            ignore=IgnoreConfig.from_dict(data.get("ignore", {})),
        )
