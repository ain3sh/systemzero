"""Tests for transcript snapshot and fork creation."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from src.core.transcript_manager import TranscriptCursor, TranscriptManager


@pytest.fixture
def transcript_file(tmp_path: Path) -> Path:
    p = tmp_path / "session.jsonl"

    # Line 1 includes a title field (best-effort rename target)
    line1 = json.dumps({"type": "session_start", "title": "My Session"}) + "\n"
    line2 = json.dumps({"id": "m2", "role": "user", "content": [{"type": "text", "text": "hi"}]})
    p.write_text(line1 + line2, encoding="utf-8")
    return p


def test_compute_cursor_extracts_last_event_id(transcript_file: Path):
    mgr = TranscriptManager()
    cursor = mgr.compute_cursor(transcript_file)

    # File ends without newline; cursor points to end of last *complete* line.
    line1 = (json.dumps({"type": "session_start", "title": "My Session"}) + "\n").encode("utf-8")
    assert cursor.byte_offset_end == len(line1)
    assert cursor.last_event_id is None
    assert cursor.prefix_sha256
    assert cursor.tail_sha256


def test_snapshot_into_checkpoint_writes_gz(tmp_path: Path, transcript_file: Path):
    mgr = TranscriptManager()
    cp_dir = tmp_path / "cp"
    snap = mgr.snapshot_into_checkpoint(transcript_file, cp_dir)

    gz_path = cp_dir / snap.snapshot_relpath
    assert gz_path.exists()

    with gzip.open(gz_path, "rb") as f:
        data = f.read().decode("utf-8")

    assert "My Session" in data
    assert "m2" in data


def test_create_fork_session_fast_path_truncates(tmp_path: Path, transcript_file: Path):
    mgr = TranscriptManager()
    full_cursor = mgr.compute_cursor(transcript_file)

    # Truncate to just the first line boundary.
    first_line = (json.dumps({"type": "session_start", "title": "My Session"}) + "\n").encode("utf-8")
    cursor = TranscriptCursor(
        byte_offset_end=len(first_line),
        last_event_id=full_cursor.last_event_id,
        prefix_sha256=full_cursor.prefix_sha256,
        tail_sha256=full_cursor.tail_sha256,
    )

    fork_path = mgr.create_fork_session(
        checkpoint_cursor=cursor,
        checkpoint_snapshot_gz=None,
        current_transcript_path=transcript_file,
        fork_dir=tmp_path,
        rewrite_title_prefix="[Fork] ",
        agent="droid",
    )

    assert fork_path.exists()
    fork_text = fork_path.read_text(encoding="utf-8")

    # Should contain only the first line (with prefixed title).
    assert fork_text.count("\n") == 1
    assert "\"title\": \"[Fork] My Session\"" in fork_text
    assert "m2" not in fork_text
