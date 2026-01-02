from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

from .config import extract_agent_overrides, load_merged_config
from .detect import select_profile
from .jsonpath import first_present
from .project_root import find_git_root
from .registry import AgentRegistry
from .types import AgentContext, AgentOverrides, AgentProfile, HookEnvelope


def _normalize_event_name(raw: str, mapping: Mapping[str, str]) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    lower = s.lower()
    return mapping.get(lower, s)


def _extract_paths(payload: Mapping[str, Any], paths: list[str]) -> Any:
    return first_present(payload, paths)


def _profile_paths(profile: AgentProfile, key: str) -> list[str]:
    hooks = profile.data.get("hooks") if isinstance(profile.data, dict) else None
    if not isinstance(hooks, dict):
        return []
    val = hooks.get(key)
    if isinstance(val, list):
        return [str(x) for x in val if isinstance(x, str)]
    return []


def _profile_event_map(profile: AgentProfile) -> dict[str, str]:
    hooks = profile.data.get("hooks") if isinstance(profile.data, dict) else None
    if not isinstance(hooks, dict):
        return {}
    m = hooks.get("event_name_map")
    if not isinstance(m, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in m.items():
        if isinstance(k, str) and isinstance(v, str):
            out[k.lower()] = v
    return out


def _profile_env_var(profile: AgentProfile, key: str) -> str | None:
    env = profile.data.get("env") if isinstance(profile.data, dict) else None
    if not isinstance(env, dict):
        return None
    v = env.get(key)
    return str(v) if isinstance(v, str) and v else None


def resolve_context_and_envelope(
    raw_payload: Mapping[str, Any],
    *,
    env: Mapping[str, str] | None = None,
) -> tuple[HookEnvelope, AgentContext, AgentProfile | None, AgentOverrides]:
    """Resolve agent profile + config overrides + canonical hook envelope.

    Returns:
      (envelope, context, profile, overrides)
    """

    env = env or os.environ

    # Seed project root from env vars or payload.cwd.
    seed_dir = None
    for k in ("FACTORY_PROJECT_DIR", "CLAUDE_PROJECT_DIR"):
        if env.get(k):
            seed_dir = Path(env[k]).expanduser()
            break
    if seed_dir is None:
        cwd = raw_payload.get("cwd")
        if isinstance(cwd, str) and cwd:
            seed_dir = Path(cwd).expanduser()
    if seed_dir is None:
        seed_dir = Path.cwd()

    guessed_root = find_git_root(seed_dir) or seed_dir
    cfg = load_merged_config(guessed_root)
    overrides = extract_agent_overrides(cfg)

    registry = AgentRegistry.load_bundled()
    profile = select_profile(list(registry.all()), overrides=overrides, payload=raw_payload, env=env)

    # If we still don't have a profile, fall back to a minimal default.
    event_name = raw_payload.get("hook_event_name") or raw_payload.get("hookEventName") or ""
    session_id = raw_payload.get("session_id") or raw_payload.get("sessionId") or ""
    transcript_path = raw_payload.get("transcript_path") or raw_payload.get("transcriptPath") or ""
    cwd = raw_payload.get("cwd") or ""
    tool_name = raw_payload.get("tool_name") or None
    tool_input = raw_payload.get("tool_input") or None

    if profile is not None:
        event_name = _extract_paths(raw_payload, _profile_paths(profile, "event_name_paths")) or event_name
        session_id = _extract_paths(raw_payload, _profile_paths(profile, "session_id_paths")) or session_id
        transcript_path = _extract_paths(raw_payload, _profile_paths(profile, "transcript_path_paths")) or transcript_path
        cwd = _extract_paths(raw_payload, _profile_paths(profile, "cwd_paths")) or cwd
        tool_name = _extract_paths(raw_payload, _profile_paths(profile, "tool_name_paths")) or tool_name
        tool_input = _extract_paths(raw_payload, _profile_paths(profile, "tool_input_paths")) or tool_input

        event_map = _profile_event_map(profile)
        if isinstance(event_name, str):
            event_name = _normalize_event_name(event_name, event_map)

    # Apply config overrides.
    if overrides.transcript_path:
        transcript_path = overrides.transcript_path
    if overrides.project_root:
        cwd = overrides.project_root

    # Fill env-derived context.
    env_file = None
    project_dir = None
    if profile is not None:
        env_file_var = _profile_env_var(profile, "env_file_var")
        if env_file_var:
            env_file = env.get(env_file_var) or None
        project_dir_var = _profile_env_var(profile, "project_dir_var")
        if project_dir_var:
            project_dir = env.get(project_dir_var) or None

    if overrides.project_root:
        project_root = overrides.project_root
    else:
        seed = Path(project_dir).expanduser() if project_dir else (Path(str(cwd)).expanduser() if cwd else guessed_root)
        project_root = str(find_git_root(seed) or seed)

    envelope = HookEnvelope(
        hook_event_name=str(event_name or ""),
        session_id=str(session_id or ""),
        transcript_path=str(transcript_path or ""),
        cwd=str(cwd or ""),
        tool_name=str(tool_name) if isinstance(tool_name, str) and tool_name else None,
        tool_input=tool_input if isinstance(tool_input, dict) else None,
        raw=raw_payload,
    )

    context = AgentContext(
        agent=profile.id if profile else "unknown",
        project_root=project_root,
        cwd=str(cwd or "") if cwd else None,
        transcript_path=str(transcript_path) if transcript_path else None,
        session_id=str(session_id) if session_id else None,
        env_file=str(env_file) if env_file else None,
    )

    return envelope, context, profile, overrides
