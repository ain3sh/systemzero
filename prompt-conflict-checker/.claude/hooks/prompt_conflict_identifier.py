#!/usr/bin/env python3
"""UserPromptSubmit hook to detect conflicting instructions in long prompts.

Works identically with Claude Code and Factory Droid CLI.
When a prompt exceeds the token threshold, this hook blocks submission,
saves the prompt to /tmp/prompt-conflicts/, and instructs the user to
submit a short slash command instead that will ask the agent to analyze
the saved prompt for conflicts.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

# ============================================================================
# Token Counting (tiktoken-based with fallback)
# ============================================================================

try:
    import tiktoken
    _ENC = tiktoken.get_encoding("o200k_base")
    _encode = _ENC.encode_ordinary
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    _encode = None


def count_tokens(text: str) -> int:
    """Count tokens using o200k_base encoding, fallback to char estimate."""
    if TIKTOKEN_AVAILABLE and _encode:
        return len(_encode(text))
    return len(text) >> 2  # ~4 chars per token estimate


# ============================================================================
# Platform Detection (cached at module load)
# ============================================================================

_PLATFORM = sys.platform
_IS_WSL = "microsoft" in os.uname().release.lower() if hasattr(os, "uname") else False


# ============================================================================
# Environment Helpers
# ============================================================================

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def env_bool(key: str, default: bool = False) -> bool:
    """Get boolean env var."""
    val = os.environ.get(key, "").lower()
    return val in _TRUE_VALUES if val else default


def env_int(key: str, default: int) -> int:
    """Get integer env var with default."""
    raw = os.environ.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def env_path(key: str, default: str) -> Path:
    """Get path env var with default."""
    return Path(os.environ.get(key, default))


# ============================================================================
# Configuration
# ============================================================================

@dataclass(slots=True, frozen=True)
class Config:
    """Runtime configuration loaded from environment variables."""

    token_threshold: int
    always_on: bool
    allow_override: bool
    tmp_dir: Path
    skip_prefix: str
    skip_prefix_lower: str


def load_config() -> Config:
    """Load configuration from environment with safe defaults."""
    skip_prefix = "# skip-conflict-check"
    return Config(
        token_threshold=env_int("LONG_PROMPT_THRESHOLD", 1800),
        always_on=env_bool("PROMPT_CONFLICT_ALWAYS_ON", False),
        allow_override=env_bool("PROMPT_CONFLICT_ALLOW_OVERRIDE", True),
        tmp_dir=env_path("PROMPT_CONFLICT_TMP_DIR", "/tmp/prompt-conflicts"),
        skip_prefix=skip_prefix,
        skip_prefix_lower=skip_prefix.lower(),
    )


# ============================================================================
# Hook Input Parsing
# ============================================================================

@dataclass(slots=True, frozen=True)
class HookInput:
    """Parsed UserPromptSubmit hook input."""

    session_id: str
    transcript_path: str
    cwd: str
    permission_mode: str
    prompt: str


class HookInputError(Exception):
    """Raised when hook input cannot be parsed."""


def read_hook_input() -> HookInput:
    """Parse UserPromptSubmit JSON from stdin."""
    raw = sys.stdin.read().strip()
    if not raw:
        raise HookInputError("No input received on stdin")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HookInputError(f"Invalid JSON: {e}") from e

    if not isinstance(data, dict):
        raise HookInputError("Hook input must be a JSON object")

    prompt = data.get("prompt")
    if not isinstance(prompt, str):
        raise HookInputError("Missing 'prompt' field in hook input")

    return HookInput(
        session_id=data.get("session_id", ""),
        transcript_path=data.get("transcript_path", ""),
        cwd=data.get("cwd", ""),
        permission_mode=data.get("permission_mode", "default"),
        prompt=prompt,
    )


# ============================================================================
# Hook Output Emission
# ============================================================================

def emit_block(reason: str) -> NoReturn:
    """Emit blocking decision and exit."""
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def emit_context(context: str) -> NoReturn:
    """Emit additional context to inject into the conversation and exit."""
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context,
        },
    }))
    sys.exit(0)


def exit_allow() -> NoReturn:
    """Exit allowing the prompt to proceed (no output needed)."""
    sys.exit(0)


def exit_error(message: str) -> NoReturn:
    """Exit with non-blocking error (code 1, stderr)."""
    print(message, file=sys.stderr)
    sys.exit(1)


# ============================================================================
# Prompt Storage
# ============================================================================

@dataclass(slots=True, frozen=True)
class StoredPrompt:
    """Information about a prompt saved to disk."""

    path: Path
    filename: str


def store_prompt(prompt: str, config: Config, session_id: str) -> StoredPrompt:
    """Save prompt to timestamped file and create latest.md symlink."""
    config.tmp_dir.mkdir(parents=True, exist_ok=True)

    timestamp = int(time.time())
    sess_short = (session_id or "nosession").replace(os.sep, "_")[:8]
    digest = hashlib.sha256(prompt.encode()).hexdigest()[:10]
    filename = f"{timestamp}-{sess_short}-{digest}.md"

    file_path = config.tmp_dir / filename
    file_path.write_text(prompt, encoding="utf-8")

    # Create/update latest.md symlink
    latest_path = config.tmp_dir / "latest.md"
    try:
        latest_path.unlink(missing_ok=True)
        try:
            latest_path.symlink_to(filename)
        except OSError:
            latest_path.write_text(prompt, encoding="utf-8")
    except OSError:
        pass

    return StoredPrompt(path=file_path, filename=filename)


# ============================================================================
# Clipboard Integration
# ============================================================================

def copy_to_clipboard(text: str) -> bool:
    """Copy text to system clipboard. Returns True on success."""
    text_bytes = text.encode()
    devnull = subprocess.DEVNULL

    try:
        match _PLATFORM:
            case "darwin":
                subprocess.run(
                    ["pbcopy"],
                    input=text_bytes,
                    check=True,
                    stdout=devnull,
                    stderr=devnull,
                )
                return True

            case "win32":
                subprocess.run(
                    ["clip.exe"],
                    input=text_bytes,
                    check=True,
                    stdout=devnull,
                    stderr=devnull,
                )
                return True

            case _ if _IS_WSL:
                subprocess.run(
                    ["clip.exe"],
                    input=text_bytes,
                    check=True,
                    stdout=devnull,
                    stderr=devnull,
                )
                return True

            case _:  # Linux native
                for cmd in (
                    ["xclip", "-selection", "clipboard"],
                    ["xsel", "--clipboard", "--input"],
                ):
                    try:
                        subprocess.run(
                            cmd,
                            input=text_bytes,
                            check=True,
                            stdout=devnull,
                            stderr=devnull,
                        )
                        return True
                    except (FileNotFoundError, subprocess.CalledProcessError):
                        continue
                return False
    except Exception:
        return False


# ============================================================================
# Main Hook Logic
# ============================================================================

def handle_prompt(hook_input: HookInput, config: Config) -> None:
    """Decide whether to block. Exits directly on block, returns on allow."""
    prompt = hook_input.prompt
    stripped = prompt.lstrip()

    # Optional override: skip checking with special prefix
    if config.allow_override and stripped.lower().startswith(config.skip_prefix_lower):
        return  # allow

    token_count = count_tokens(prompt)

    # Short prompts pass through
    if not config.always_on and token_count <= config.token_threshold:
        return  # allow

    # Long prompt detected - save to file and block
    stored = store_prompt(prompt, config, hook_input.session_id)

    slash_command = "/check-conflicts"
    clipboard_hint = (
        f"\n✓ Copied: {slash_command}\n   Paste and press Enter!"
        if copy_to_clipboard(slash_command)
        else f"\n   Copy and submit: {slash_command}"
    )

    reason = f"""Prompt blocked ({token_count:,} tokens > {config.token_threshold:,} threshold).
Saved to: {stored.path}
{clipboard_hint}

────────────────────────────────────────────────
{slash_command}
────────────────────────────────────────────────

This asks the agent to analyze the saved prompt for conflicting
or ambiguous instructions.
"""

    emit_block(reason)  # exits


def main() -> NoReturn:
    """Entry point."""
    config = load_config()

    try:
        hook_input = read_hook_input()
    except HookInputError as e:
        exit_error(f"[prompt_conflict] {e}")

    handle_prompt(hook_input, config)
    exit_allow()


if __name__ == "__main__":
    main()
