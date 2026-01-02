from __future__ import annotations

from pathlib import Path

import pytest

from src.core.checkpoint_store import CheckpointMetadata
from src.core.controller import RewindController
from src.core.transcript_manager import TranscriptManager, TranscriptManagerError


def _write_transcript(path: Path) -> list[bytes]:
    lines = [
        b'{"type": "session_start", "title": "T"}\n',
        b'{"role": "user", "content": [{"type": "text", "text": "first"}]}\n',
        b'{"role": "assistant", "content": [{"type": "text", "text": "a"}]}\n',
        b'{"role": "user", "content": [{"type": "text", "text": "second"}]}\n',
        b'{"role": "assistant", "content": [{"type": "text", "text": "b"}]}\n',
    ]
    path.write_bytes(b"".join(lines))
    return lines


def test_find_boundary_by_user_prompts_n1(tmp_path: Path):
    tp = tmp_path / "t.jsonl"
    lines = _write_transcript(tp)

    mgr = TranscriptManager()
    boundary = mgr.find_boundary_by_user_prompts(tp, 1)

    expected_offset = len(lines[0] + lines[1] + lines[2])
    assert boundary.boundary_offset == expected_offset
    assert boundary.prompts == ["second"]


def test_find_boundary_by_user_prompts_n2(tmp_path: Path):
    tp = tmp_path / "t.jsonl"
    lines = _write_transcript(tp)

    mgr = TranscriptManager()
    boundary = mgr.find_boundary_by_user_prompts(tp, 2)

    expected_offset = len(lines[0])
    assert boundary.boundary_offset == expected_offset
    assert boundary.prompts == ["first", "second"]


def test_create_fork_at_offset_truncates(tmp_path: Path):
    tp = tmp_path / "t.jsonl"
    _write_transcript(tp)

    mgr = TranscriptManager()
    boundary = mgr.find_boundary_by_user_prompts(tp, 1)
    fork = mgr.create_fork_at_offset(current_transcript_path=tp, boundary_offset=boundary.boundary_offset, agent="droid")

    text = fork.read_text(encoding="utf-8")
    assert "first" in text
    assert "second" not in text
    assert text.endswith("\n")


def test_rewrite_in_place_at_offset_backups(tmp_path: Path):
    tp = tmp_path / "t.jsonl"
    _write_transcript(tp)

    mgr = TranscriptManager()
    boundary = mgr.find_boundary_by_user_prompts(tp, 1)
    backup_dir = tmp_path / "backup"
    backup = mgr.rewrite_in_place_at_offset(
        current_transcript_path=tp,
        boundary_offset=boundary.boundary_offset,
        backup_dir=backup_dir,
    )

    assert backup.exists()
    assert "second" in backup.read_text(encoding="utf-8")

    new_text = tp.read_text(encoding="utf-8")
    assert "second" not in new_text


def test_select_checkpoint_for_boundary():
    transcript_path = "/tmp/t.jsonl"
    checkpoints = [
        CheckpointMetadata(
            name="newest",
            timestamp="t",
            description="",
            file_count=0,
            total_size=0,
            has_transcript=True,
            transcript={
                "original_path": transcript_path,
                "cursor": {"byte_offset_end": 150},
            },
        ),
        CheckpointMetadata(
            name="older",
            timestamp="t",
            description="",
            file_count=0,
            total_size=0,
            has_transcript=True,
            transcript={
                "original_path": transcript_path,
                "cursor": {"byte_offset_end": 50},
            },
        ),
    ]

    chosen = RewindController._select_checkpoint_for_boundary(
        checkpoints,
        transcript_path=transcript_path,
        boundary_offset=200,
    )
    assert chosen is not None
    assert chosen.name == "newest"


def test_find_boundary_raises_when_not_enough(tmp_path: Path):
    tp = tmp_path / "t.jsonl"
    tp.write_text("{}\n", encoding="utf-8")

    mgr = TranscriptManager()
    with pytest.raises(TranscriptManagerError):
        mgr.find_boundary_by_user_prompts(tp, 1)
