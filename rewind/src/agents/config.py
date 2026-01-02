from __future__ import annotations

from pathlib import Path
from typing import Any

from ..utils.env import get_global_rewind_dir
from ..utils.fs import safe_json_load
from .types import AgentOverrides


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_merged_config(project_root: Path | None) -> dict[str, Any]:
    merged: dict[str, Any] = {}

    global_path = get_global_rewind_dir() / "config.json"
    if global_path.exists():
        global_data = safe_json_load(global_path, {})
        if isinstance(global_data, dict):
            merged = _deep_merge(merged, global_data)

    if project_root:
        project_path = project_root / ".agent" / "rewind" / "config.json"
        if project_path.exists():
            project_data = safe_json_load(project_path, {})
            if isinstance(project_data, dict):
                merged = _deep_merge(merged, project_data)

    return merged


def extract_agent_overrides(cfg: dict[str, Any]) -> AgentOverrides:
    # Support both a simple string "agent" or an object "agent".
    forced_agent: str | None = None
    project_root: str | None = None
    transcript_path: str | None = None

    raw_agent = cfg.get("agent")
    if isinstance(raw_agent, str):
        forced_agent = raw_agent
    elif isinstance(raw_agent, dict):
        forced_agent = raw_agent.get("kind") or raw_agent.get("agent")
        transcript_path = raw_agent.get("transcript_path") or raw_agent.get("transcriptPath")
        project_root = raw_agent.get("project_root") or raw_agent.get("projectRoot")

    # Also accept top-level overrides for convenience.
    if isinstance(cfg.get("transcript_path"), str) and not transcript_path:
        transcript_path = cfg.get("transcript_path")
    if isinstance(cfg.get("project_root"), str) and not project_root:
        project_root = cfg.get("project_root")

    return AgentOverrides(
        agent=str(forced_agent).strip() if forced_agent else None,
        project_root=str(project_root).strip() if project_root else None,
        transcript_path=str(transcript_path).strip() if transcript_path else None,
    )
