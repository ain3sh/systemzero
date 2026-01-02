from __future__ import annotations

from pathlib import Path
from typing import Mapping


def _env_quote(val: str) -> str:
    """Quote env-file values for broad compatibility.

    Some agents *parse* env files instead of shell-sourcing them. Double quotes are
    more widely handled by simple parsers than single quotes.

    Also escape shell-expansion characters so the line is safe if sourced.
    """

    escaped = (
        val.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("$", "\\$")
        .replace("`", "\\`")
    )
    return f'"{escaped}"'


def write_env_exports(env_file: Path, exports: Mapping[str, str]) -> None:
    """Append export lines to an env file (best-effort).

    Writes lines in the form: `export KEY="value"`.

    This is intentionally append-only to avoid clobbering other hooks that may
    also be writing to the same env file.
    """

    env_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        needs_leading_newline = False
        if env_file.exists():
            try:
                existing = env_file.read_bytes()
                if existing and not existing.endswith(b"\n"):
                    needs_leading_newline = True
            except OSError:
                pass

        with open(env_file, "a", encoding="utf-8") as f:
            if needs_leading_newline:
                f.write("\n")
            f.write("# Added by rewind\n")
            for k, v in exports.items():
                f.write(f"export {k}={_env_quote(v)}\n")
    except OSError:
        return
