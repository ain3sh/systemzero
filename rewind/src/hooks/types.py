"""Type definitions for hook inputs.

Based on the Factory/Claude Code hooks reference documentation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

HookEventName = Literal[
    "PreToolUse",
    "PostToolUse",
    "Notification",
    "UserPromptSubmit",
    "Stop",
    "SubagentStop",
    "PreCompact",
    "SessionStart",
    "SessionEnd",
]

SessionStartSource = Literal["startup", "resume", "clear", "compact"]


@dataclass(slots=True)
class BaseHookInput:
    """Common fields present in all hook inputs."""
    session_id: str
    transcript_path: str
    cwd: str
    hook_event_name: HookEventName


@dataclass(slots=True)
class PreToolUseInput(BaseHookInput):
    """Input for PreToolUse hooks."""
    tool_name: str
    tool_input: dict[str, Any]


@dataclass(slots=True)
class PostToolUseInput(BaseHookInput):
    """Input for PostToolUse hooks."""
    tool_name: str
    tool_input: dict[str, Any]
    tool_response: dict[str, Any]


@dataclass(slots=True)
class SessionStartInput(BaseHookInput):
    """Input for SessionStart hooks."""
    source: SessionStartSource


@dataclass(slots=True)
class UserPromptSubmitInput(BaseHookInput):
    """Input for UserPromptSubmit hooks."""
    prompt: str


@dataclass(slots=True)
class StopInput(BaseHookInput):
    """Input for Stop hooks."""
    stop_hook_active: bool


# Union type for supported hook inputs
HookInput = PreToolUseInput | PostToolUseInput | SessionStartInput | UserPromptSubmitInput | StopInput
