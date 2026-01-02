"""I/O utilities for Rewind hooks.

Provides proper hook protocol implementation:
- Exit 0: Allow action (no stdout for PreToolUse)
- Exit 2: Block action (stderr shown to agent)
- Exit 1: Non-blocking error (stderr shown to user)
- Stdout: Only for SessionStart context injection
"""

from __future__ import annotations

import json
import sys
from typing import Any, NoReturn, TypeVar, overload
from ..agents.normalize import resolve_context_and_envelope
from ..agents.types import AgentContext

from .types import (
    BaseHookInput,
    HookEventName,
    HookInput,
    PostToolUseInput,
    PreToolUseInput,
    SessionStartInput,
    StopInput,
    UserPromptSubmitInput,
)


class HookInputError(Exception):
    """Raised when hook input cannot be parsed."""


T = TypeVar("T", bound=BaseHookInput)


def _extract_base_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Extract common base fields from hook input data."""
    return {
        "session_id": data.get("session_id", ""),
        "transcript_path": data.get("transcript_path", ""),
        "cwd": data.get("cwd", ""),
        "hook_event_name": data.get("hook_event_name", ""),
    }


def _parse_pre_tool_use(data: dict[str, Any]) -> PreToolUseInput:
    """Parse PreToolUse hook input."""
    base = _extract_base_fields(data)
    return PreToolUseInput(
        **base,
        tool_name=data.get("tool_name", ""),
        tool_input=data.get("tool_input", {}),
    )


def _parse_post_tool_use(data: dict[str, Any]) -> PostToolUseInput:
    """Parse PostToolUse hook input."""
    base = _extract_base_fields(data)
    return PostToolUseInput(
        **base,
        tool_name=data.get("tool_name", ""),
        tool_input=data.get("tool_input", {}),
        tool_response=data.get("tool_response", {}),
    )


def _parse_session_start(data: dict[str, Any]) -> SessionStartInput:
    """Parse SessionStart hook input."""
    base = _extract_base_fields(data)
    return SessionStartInput(**base, source=data.get("source", "startup"))


def _parse_user_prompt_submit(data: dict[str, Any]) -> UserPromptSubmitInput:
    """Parse UserPromptSubmit hook input."""
    base = _extract_base_fields(data)
    return UserPromptSubmitInput(**base, prompt=data.get("prompt", ""))


def _parse_stop(data: dict[str, Any]) -> StopInput:
    """Parse Stop hook input."""
    base = _extract_base_fields(data)
    return StopInput(**base, stop_hook_active=data.get("stop_hook_active", False))


_PARSERS: dict[HookEventName, Any] = {
    "PreToolUse": _parse_pre_tool_use,
    "PostToolUse": _parse_post_tool_use,
    "SessionStart": _parse_session_start,
    "UserPromptSubmit": _parse_user_prompt_submit,
    "Stop": _parse_stop,
}


def read_input_with_context() -> tuple[HookInput, AgentContext]:
    """Read and parse hook input from stdin.
    
    Returns:
        Typed hook input based on hook_event_name
        
    Raises:
        HookInputError: If input cannot be read or parsed
    """
    raw = sys.stdin.read().strip()
    if not raw:
        raise HookInputError("No input received on stdin")
    
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HookInputError(f"Invalid JSON: {e}") from e
    
    if not isinstance(data, dict):
        raise HookInputError("Hook input must be a JSON object")

    envelope, context, _profile, _overrides = resolve_context_and_envelope(data)
    event_name = envelope.hook_event_name
    if not event_name:
        raise HookInputError("Missing 'hook_event_name' field")

    parser = _PARSERS.get(event_name)  # type: ignore[arg-type]
    if parser is None:
        raise HookInputError(f"Unsupported hook event: {event_name}")

    canonical: dict[str, Any] = {
        "session_id": envelope.session_id,
        "transcript_path": envelope.transcript_path,
        "cwd": envelope.cwd,
        "hook_event_name": event_name,
    }
    if envelope.tool_name is not None:
        canonical["tool_name"] = envelope.tool_name
    if envelope.tool_input is not None:
        canonical["tool_input"] = envelope.tool_input

    return parser(canonical), context


def read_input() -> HookInput:
    hook_input, _context = read_input_with_context()
    return hook_input


@overload
def read_input_as(input_type: type[PreToolUseInput]) -> PreToolUseInput: ...
@overload
def read_input_as(input_type: type[PostToolUseInput]) -> PostToolUseInput: ...
@overload
def read_input_as(input_type: type[SessionStartInput]) -> SessionStartInput: ...
@overload
def read_input_as(input_type: type[UserPromptSubmitInput]) -> UserPromptSubmitInput: ...
@overload
def read_input_as(input_type: type[StopInput]) -> StopInput: ...


def read_input_as(input_type: type[T]) -> T:
    """Read hook input and validate it matches expected type.
    
    Args:
        input_type: Expected input type class
        
    Returns:
        Typed hook input
        
    Raises:
        HookInputError: If input doesn't match expected type
    """
    hook_input = read_input()
    if not isinstance(hook_input, input_type):
        raise HookInputError(
            f"Expected {input_type.__name__}, got {type(hook_input).__name__}"
        )
    return hook_input


def exit_success() -> NoReturn:
    """Exit with success (allow the action).
    
    For PreToolUse: silently allows the tool call.
    For other hooks: normal success.
    """
    sys.exit(0)


def exit_error(message: str) -> NoReturn:
    """Exit with non-blocking error.
    
    Message goes to stderr and is shown to user.
    """
    print(message, file=sys.stderr)
    sys.exit(1)


def exit_block(message: str) -> NoReturn:
    """Exit to block an action.
    
    Message goes to stderr and is shown to agent.
    """
    print(message, file=sys.stderr)
    sys.exit(2)


def emit_context(message: str) -> None:
    """Emit context message to stdout.
    
    Only use for SessionStart hooks - stdout is added to agent context.
    For other hooks, stdout is ignored or causes issues.
    """
    print(message)


def log_debug(message: str) -> None:
    """Log debug message to stderr.
    
    Only outputs if REWIND_DEBUG is set.
    """
    import os
    if os.environ.get("REWIND_DEBUG"):
        print(f"[rewind] {message}", file=sys.stderr)
