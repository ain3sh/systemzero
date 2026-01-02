from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from src.config.types import AntiSpamConfig, TierConfig
from src.core.checkpoint_store import CheckpointMetadata
from src.integrations.hooks.handler import HookHandler
from src.integrations.hooks.types import SessionStartInput


@dataclass
class _FakeController:
    rewind_dir: Path
    checkpoints: list[CheckpointMetadata]
    created: list[dict]

    def get_rewind_dir(self) -> Path:
        return self.rewind_dir

    def list_checkpoints(self) -> list[CheckpointMetadata]:
        return self.checkpoints

    def create_checkpoint(self, *, description: str, session_id: str | None, transcript_path: str | None, force: bool = False):
        self.created.append(
            {
                "description": description,
                "session_id": session_id,
                "transcript_path": transcript_path,
            }
        )
        return {"success": True}


def _checkpoint_for_transcript(path: str) -> CheckpointMetadata:
    return CheckpointMetadata(
        name="20260101_000000_000",
        timestamp="2026-01-01T00:00:00",
        description="baseline",
        file_count=1,
        total_size=1,
        has_transcript=True,
        transcript={
            "original_path": path,
            "cursor": {"byte_offset_end": 1, "prefix_sha256": "x", "tail_sha256": "y"},
        },
    )


def test_resume_without_transcript_path_warns_and_does_not_checkpoint(tmp_path):
    controller = _FakeController(rewind_dir=tmp_path, checkpoints=[], created=[])
    handler = HookHandler(controller=controller, tier_config=TierConfig())

    outcome = handler.handle(
        SessionStartInput(
            session_id="s1",
            transcript_path="",
            cwd=str(tmp_path),
            hook_event_name="SessionStart",
            source="resume",
        )
    )

    assert controller.created == []
    assert any("transcript path is unavailable" in w for w in outcome.warnings)


def test_resume_with_no_existing_checkpoint_creates_baseline_and_warns(tmp_path):
    transcript = str(tmp_path / "t.jsonl")
    controller = _FakeController(rewind_dir=tmp_path, checkpoints=[], created=[])
    handler = HookHandler(controller=controller, tier_config=TierConfig())

    outcome = handler.handle(
        SessionStartInput(
            session_id="s1",
            transcript_path=transcript,
            cwd=str(tmp_path),
            hook_event_name="SessionStart",
            source="resume",
        )
    )

    assert len(controller.created) == 1
    assert controller.created[0]["description"] == "Session resume"
    assert outcome.checkpoint_created is True
    assert any("created baseline" in w for w in outcome.warnings)


def test_resume_with_existing_checkpoint_does_not_create_baseline(tmp_path):
    transcript = str(tmp_path / "t.jsonl")
    controller = _FakeController(
        rewind_dir=tmp_path,
        checkpoints=[_checkpoint_for_transcript(transcript)],
        created=[],
    )
    handler = HookHandler(controller=controller, tier_config=TierConfig())

    outcome = handler.handle(
        SessionStartInput(
            session_id="s1",
            transcript_path=transcript,
            cwd=str(tmp_path),
            hook_event_name="SessionStart",
            source="resume",
        )
    )

    assert controller.created == []
    assert outcome.checkpoint_created is False
    assert outcome.warnings == []


def test_session_start_resets_anti_spam_state_on_resume(tmp_path):
    controller = _FakeController(rewind_dir=tmp_path, checkpoints=[], created=[])
    tier = TierConfig(anti_spam=AntiSpamConfig(enabled=True, min_interval_seconds=9999))
    handler = HookHandler(controller=controller, tier_config=tier)

    # Seed hook-state.json with a very recent checkpoint time.
    (tmp_path / "hook-state.json").write_text(
        json.dumps({"last_checkpoint_time": time.time()}),
        encoding="utf-8",
    )

    assert handler._should_checkpoint() is False

    handler.handle(
        SessionStartInput(
            session_id="s1",
            transcript_path=str(tmp_path / "t.jsonl"),
            cwd=str(tmp_path),
            hook_event_name="SessionStart",
            source="resume",
        )
    )

    # Reset should allow immediate checkpoints.
    assert handler._should_checkpoint() is True
