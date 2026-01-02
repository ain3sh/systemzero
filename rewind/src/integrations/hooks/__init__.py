"""Hook handling for Rewind.

Provides proper hook protocol implementation for Droid/Claude Code.
"""

from .types import (
    HookEventName,
    PreToolUseInput,
    PostToolUseInput,
    SessionStartInput,
    UserPromptSubmitInput,
    StopInput,
)
from .io import (
    read_input,
    read_input_as,
    exit_success,
    exit_error,
    emit_context,
)
from .handler import HookHandler

__all__ = [
    "HookEventName",
    "PreToolUseInput",
    "PostToolUseInput", 
    "SessionStartInput",
    "UserPromptSubmitInput",
    "StopInput",
    "read_input",
    "read_input_as",
    "exit_success",
    "exit_error",
    "emit_context",
    "HookHandler",
]
