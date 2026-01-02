from __future__ import annotations

from pathlib import Path


def find_git_root(start: Path, *, max_depth: int = 25) -> Path | None:
    """Walk upward from start to find a directory containing `.git/`.

    Returns None if not found within max_depth.
    """

    cur = start.resolve()
    for _ in range(max_depth):
        if (cur / ".git").exists():
            return cur
        if cur.parent == cur:
            return None
        cur = cur.parent
    return None
