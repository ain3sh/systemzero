from __future__ import annotations

import json
from importlib import resources
from typing import Any


def resource_dir(*parts: str) -> resources.abc.Traversable:
    base = resources.files("src")
    return base.joinpath(*parts)


def resource_exists(*parts: str) -> bool:
    try:
        return resource_dir(*parts).is_file()
    except Exception:
        return False


def read_text_resource(*parts: str, encoding: str = "utf-8") -> str:
    return resource_dir(*parts).read_text(encoding=encoding)


def read_json_resource(*parts: str) -> Any:
    return json.loads(read_text_resource(*parts))
