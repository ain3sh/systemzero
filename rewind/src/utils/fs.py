"""File system utilities for Rewind.

Provides atomic writes, directory creation, and safe file operations.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write(file_path: Path | str, content: str | bytes, mode: str = "w") -> None:
    """Write content atomically using tempfile + rename pattern.
    
    Args:
        file_path: Target file path
        content: Content to write
        mode: Write mode ('w' for text, 'wb' for binary)
    """
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create temp file in same directory for atomic rename
    fd, tmp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp"
    )
    
    try:
        with os.fdopen(fd, mode) as f:
            f.write(content)
        os.replace(tmp_path, path)
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def ensure_dir(dir_path: Path | str) -> Path:
    """Ensure directory exists, creating it if necessary.
    
    Args:
        dir_path: Directory path to create
        
    Returns:
        Path object for the directory
    """
    path = Path(dir_path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def file_exists(file_path: Path | str) -> bool:
    """Check if file exists.
    
    Args:
        file_path: Path to check
        
    Returns:
        True if file exists
    """
    return Path(file_path).exists()


def safe_json_load(file_path: Path | str, default: Any = None) -> Any:
    """Safely load JSON file with fallback.
    
    Args:
        file_path: Path to JSON file
        default: Default value if file doesn't exist or is invalid
        
    Returns:
        Parsed JSON or default value
    """
    try:
        with open(file_path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default if default is not None else {}


def safe_stat(file_path: Path | str) -> os.stat_result | None:
    """Get file stats safely.
    
    Args:
        file_path: Path to stat
        
    Returns:
        stat_result or None if file doesn't exist
    """
    try:
        return Path(file_path).stat()
    except OSError:
        return None
