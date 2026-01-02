"""Hook policy helpers.

Keep decision logic separate from side effects so hooks remain easy to reason about.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...core.checkpoint_store import CheckpointMetadata
from .types import SessionStartSource


@dataclass(frozen=True, slots=True)
class HookOutcome:
    checkpoint_created: bool
    context_messages: list[str]
    warnings: list[str]


def _normalize_path(path: str | None) -> str | None:
    if not isinstance(path, str):
        return None
    if not path.strip():
        return None
    return str(Path(path).expanduser())


def checkpoint_transcript_path(checkpoint: CheckpointMetadata) -> str | None:
    meta = checkpoint.transcript
    if not isinstance(meta, dict):
        return None

    original_path = meta.get("original_path") or meta.get("path")
    return _normalize_path(original_path if isinstance(original_path, str) else None)


def has_checkpoint_for_transcript(
    checkpoints: list[CheckpointMetadata],
    *,
    transcript_path: str | None,
) -> bool:
    tp = _normalize_path(transcript_path)
    if tp is None:
        return False

    for cp in checkpoints:
        if checkpoint_transcript_path(cp) == tp:
            return True

    return False


def session_start_description(source: SessionStartSource) -> str:
    if source == "startup":
        return "Session start"
    if source == "resume":
        return "Session resume"
    if source == "clear":
        return "Session clear"
    if source == "compact":
        return "Session compact"
    return "Session start"


def should_create_session_start_baseline(
    *,
    source: SessionStartSource,
    transcript_path: str | None,
    checkpoints: list[CheckpointMetadata],
) -> tuple[bool, list[str]]:
    """Decide whether to create a baseline checkpoint.

    Returns: (should_create, warnings)
    """
    warnings: list[str] = []

    if source == "startup":
        return True, warnings

    if source == "resume" and _normalize_path(transcript_path) is None:
        warnings.append(
            "[rewind] Resume detected but transcript path is unavailable; cannot verify checkpoint coverage"
        )
        return False, warnings

    if has_checkpoint_for_transcript(checkpoints, transcript_path=transcript_path):
        return False, warnings

    if source == "resume":
        warnings.append("[rewind] No existing checkpoint for this transcript; created baseline")

    return True, warnings
