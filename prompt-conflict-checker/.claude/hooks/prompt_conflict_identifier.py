#!/usr/bin/env python3
"""UserPromptSubmit hook to detect conflicting instructions in long prompts.

Works identically with Claude Code and Factory Droid CLI.
When a prompt exceeds the token threshold, this hook blocks submission,
saves the prompt to /tmp/prompt-conflicts/, and instructs the user to
submit a short slash command instead that will ask the agent to analyze
the saved prompt for conflicts using the built-in Edit/ApplyPatch tool.
"""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Literal

# ============================================================================
# Token Counting (tiktoken-based, optimized for performance)
# ============================================================================

try:
    import tiktoken
    _enc = tiktoken.get_encoding("o200k_base")
    _encode_ordinary = _enc.encode_ordinary
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False


def count_tokens(text: str) -> int:
    """Count tokens using o200k_base encoding.

    Falls back to rough character-based estimation if tiktoken unavailable.
    """
    return len(_encode_ordinary(text)) if TIKTOKEN_AVAILABLE else len(text) >> 2


# ============================================================================
# Platform Detection (cached at module load)
# ============================================================================

_PLATFORM = sys.platform
_IS_WSL = "microsoft" in os.uname().release.lower() if hasattr(os, "uname") else False


# ============================================================================
# Configuration
# ============================================================================

# Frozenset for faster membership testing
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


@dataclass(slots=True, frozen=True)
class Config:
    """Runtime configuration loaded from environment variables."""

    token_threshold: int
    always_on: bool
    allow_override: bool
    tmp_dir: Path
    skip_prefix: str
    skip_prefix_lower: str  # Cached lowercase version


def load_config() -> Config:
    """Load configuration from environment with safe defaults."""
    env = os.environ
    raw_threshold = env.get("LONG_PROMPT_THRESHOLD")

    try:
        token_threshold = int(raw_threshold) if raw_threshold else 1800
    except ValueError:
        token_threshold = 1800

    skip_prefix = "# skip-conflict-check"

    return Config(
        token_threshold=token_threshold,
        always_on=env.get("PROMPT_CONFLICT_ALWAYS_ON", "").lower() in _TRUE_VALUES,
        allow_override=env.get("PROMPT_CONFLICT_ALLOW_OVERRIDE", "").lower() in _TRUE_VALUES,
        tmp_dir=Path(env.get("PROMPT_CONFLICT_TMP_DIR", "/tmp/prompt-conflicts")),
        skip_prefix=skip_prefix,
        skip_prefix_lower=skip_prefix.lower(),
    )


# ============================================================================
# Hook Input Parsing
# ============================================================================

@dataclass(slots=True, frozen=True)
class HookContext:
    """Normalized view of UserPromptSubmit hook input."""

    prompt: str
    session_id: str | None


class HookParseError(Exception):
    """Raised when hook JSON input cannot be parsed."""


def parse_hook_input() -> HookContext:
    """Parse UserPromptSubmit JSON from stdin."""
    raw_text = sys.stdin.read().strip()
    if not raw_text:
        raise HookParseError("No hook input received on stdin")

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise HookParseError(f"Invalid JSON hook input: {exc}") from exc

    prompt = payload.get("prompt")
    if not isinstance(prompt, str):
        raise HookParseError("Hook input JSON missing string 'prompt' field")

    return HookContext(prompt=prompt, session_id=payload.get("session_id"))


# ============================================================================
# Prompt Storage
# ============================================================================

@dataclass(slots=True, frozen=True)
class StoredPrompt:
    """Information about a prompt saved to disk."""

    path: str


def store_prompt(prompt: str, config: Config, session_id: str | None) -> StoredPrompt:
    """Save prompt to timestamped file and create/update latest.md symlink."""
    # Ensure directory exists
    config.tmp_dir.mkdir(parents=True, exist_ok=True)

    # Generate filename: timestamp-session-hash.md
    timestamp = int(time.time())
    sess_short = (session_id or "nosession").replace(os.sep, "_")[:8]
    digest = hashlib.sha256(prompt.encode()).hexdigest()[:10]
    filename = f"{timestamp}-{sess_short}-{digest}.md"

    # Write prompt file
    file_path = config.tmp_dir / filename
    file_path.write_text(prompt, encoding="utf-8")

    # Create/update latest.md symlink
    latest_path = config.tmp_dir / "latest.md"
    try:
        latest_path.unlink(missing_ok=True)
        try:
            latest_path.symlink_to(filename)
        except OSError:
            # Fallback when symlinks are not available or permitted
            latest_path.write_text(prompt, encoding="utf-8")
    except OSError:
        # Symlink or fallback file creation can fail on some systems, non-fatal
        pass

    return StoredPrompt(path=str(file_path))


# ============================================================================
# Clipboard Integration
# ============================================================================

def copy_to_clipboard(text: str) -> bool:
    """Attempt to copy text to system clipboard.

    Returns True if successful, False otherwise.
    """
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
            case "win32" | _ if _IS_WSL:
                subprocess.run(
                    ["clip.exe"],
                    input=text_bytes,
                    check=True,
                    stdout=devnull,
                    stderr=devnull,
                )
                return True
            case _:  # Linux
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

Action = Literal["allow", "block"]


def handle_prompt(
    ctx: HookContext,
    config: Config,
) -> tuple[Action, dict | None]:
    """Decide whether to block a prompt and return appropriate JSON output.

    Returns (action, json_output) where:
    - action is "allow" or "block"
    - json_output is the dict to emit as JSON (or None for simple allow)
    """
    prompt = ctx.prompt
    stripped = prompt.lstrip()

    # Optional override: skip conflict checking with special prefix
    if config.allow_override and stripped.lower().startswith(config.skip_prefix_lower):
        return "allow", None

    token_count = count_tokens(prompt)

    # Short prompts always pass through
    if not config.always_on and token_count <= config.token_threshold:
        return "allow", None

    # Long prompt detected - save to file
    stored = store_prompt(prompt, config, ctx.session_id)

    # Prepare clipboard shortcut
    slash_command = "/check-conflicts"
    clipboard_hint = (
        f"\n✓ Copied to clipboard: {slash_command}\n   Just paste (Ctrl+V / Cmd+V) and press Enter!"
        if copy_to_clipboard(slash_command)
        else f"\n   Copy and submit: {slash_command}"
    )

    # Block with helpful message
    reason = f"""Prompt too long ({token_count:,} tokens > {config.token_threshold:,} threshold).
Saved to: {stored.path}
{clipboard_hint}

────────────────────────────────────────────────
{slash_command}
────────────────────────────────────────────────

This will ask the agent to analyze the saved prompt for conflicting
or ambiguous instructions using Edit/ApplyPatch with git-diff highlighting.
"""

    return "block", {"decision": "block", "reason": reason}


def main() -> int:
    """Entry point for the hook script."""
    config = load_config()

    # Parse hook input
    try:
        ctx = parse_hook_input()
    except HookParseError as exc:
        # Non-blocking error: just log to stderr and allow
        print(f"[prompt_conflict] Hook input error: {exc}", file=sys.stderr)
        return 1

    # Decide whether to block
    action, output = handle_prompt(ctx, config)

    if action == "block" and output:
        print(json.dumps(output))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
