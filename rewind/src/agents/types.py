from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class AgentOverrides:
    """Config-driven overrides.

    Any field may be None to indicate "no override".
    """

    agent: str | None = None
    project_root: str | None = None
    transcript_path: str | None = None


@dataclass(frozen=True, slots=True)
class AgentProfile:
    id: str
    display_name: str
    data: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class HookEnvelope:
    hook_event_name: str
    session_id: str
    transcript_path: str
    cwd: str
    tool_name: str | None
    tool_input: dict[str, Any] | None
    raw: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class AgentContext:
    agent: str
    project_root: str | None
    cwd: str | None
    transcript_path: str | None
    session_id: str | None
    env_file: str | None
