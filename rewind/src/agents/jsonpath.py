from __future__ import annotations

from typing import Any, Iterable


def _iter_path_parts(path: str) -> list[str]:
    s = path.strip()
    if not s:
        return []
    if s.startswith("$."):
        s = s[2:]
    return [p for p in s.split(".") if p]


def get_path(data: Any, path: str) -> Any:
    """Minimal JSON-path-like getter.

    Supports only dotted object traversal: `$.a.b.c`.
    Returns None if any component is missing.
    """

    cur: Any = data
    for part in _iter_path_parts(path):
        if not isinstance(cur, dict):
            return None
        if part not in cur:
            return None
        cur = cur[part]
    return cur


def first_present(data: Any, paths: Iterable[str]) -> Any:
    for p in paths:
        val = get_path(data, p)
        if val is not None:
            return val
    return None
