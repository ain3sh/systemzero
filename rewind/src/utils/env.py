"""Environment utilities for Rewind."""

from __future__ import annotations

import os
from pathlib import Path


def is_debug_mode() -> bool:
    """Check if debug mode is enabled.
    
    Returns:
        True if REWIND_DEBUG is set to a truthy value
    """
    val = os.environ.get("REWIND_DEBUG", "").lower()
    return val in ("1", "true", "yes", "on")


def get_home_dir() -> Path:
    """Get user home directory.
    
    Returns:
        Path to home directory
    """
    return Path.home()


def get_global_rewind_dir() -> Path:
    """Get global rewind directory (~/.rewind).
    
    Returns:
        Path to global rewind config directory
    """
    return get_home_dir() / ".rewind"


def get_global_storage_dir() -> Path:
    """Get global storage directory (~/.rewind/storage).
    
    Returns:
        Path to global checkpoint storage
    """
    return get_global_rewind_dir() / "storage"
