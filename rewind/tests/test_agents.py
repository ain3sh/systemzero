from __future__ import annotations

import json
from pathlib import Path

from src.agents.envfile import write_env_exports
from src.agents.normalize import resolve_context_and_envelope


def test_detects_claude_from_transcript_path(tmp_path: Path):
    transcript = tmp_path / ".claude" / "projects" / "x" / "abc.jsonl"
    payload = {
        "session_id": "abc123",
        "transcript_path": str(transcript),
        "hook_event_name": "SessionStart",
        "source": "startup",
    }
    env = {
        "CLAUDE_ENV_FILE": str(tmp_path / "env"),
        "CLAUDE_PROJECT_DIR": str(tmp_path),
    }

    envelope, ctx, profile, overrides = resolve_context_and_envelope(payload, env=env)
    assert overrides.agent is None
    assert profile is not None
    assert ctx.agent == "claude"
    assert envelope.hook_event_name == "SessionStart"
    assert ctx.env_file == env["CLAUDE_ENV_FILE"]


def test_detects_droid_from_transcript_path(tmp_path: Path):
    transcript = tmp_path / ".factory" / "projects" / "x" / "abc.jsonl"
    payload = {
        "session_id": "abc123",
        "transcript_path": str(transcript),
        "hook_event_name": "SessionStart",
        "cwd": str(tmp_path),
        "source": "startup",
    }
    env = {
        "CLAUDE_ENV_FILE": str(tmp_path / "env"),
        "FACTORY_PROJECT_DIR": str(tmp_path),
    }

    envelope, ctx, profile, _overrides = resolve_context_and_envelope(payload, env=env)
    assert profile is not None
    assert ctx.agent == "droid"
    assert ctx.env_file == env["CLAUDE_ENV_FILE"]


def test_config_override_forces_agent(tmp_path: Path, monkeypatch):
    # Global config takes effect when no project override exists.
    cfg_dir = tmp_path / ".rewind"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.json").write_text(json.dumps({"agent": "droid"}))

    transcript = tmp_path / ".claude" / "projects" / "x" / "abc.jsonl"
    payload = {
        "session_id": "abc123",
        "transcript_path": str(transcript),
        "hook_event_name": "SessionStart",
        "source": "startup",
    }
    env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}

    _envelope, ctx, profile, overrides = resolve_context_and_envelope(payload, env=env)
    assert overrides.agent == "droid"
    assert profile is not None
    assert ctx.agent == "droid"


def test_config_override_transcript_path(tmp_path: Path):
    cfg_dir = tmp_path / ".rewind"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.json").write_text(json.dumps({"transcript_path": "/forced.jsonl"}))

    payload = {
        "session_id": "abc123",
        "transcript_path": "/ignored.jsonl",
        "hook_event_name": "SessionStart",
        "cwd": str(tmp_path),
        "source": "startup",
    }

    envelope, ctx, _profile, overrides = resolve_context_and_envelope(payload, env={})
    assert overrides.transcript_path == "/forced.jsonl"
    assert envelope.transcript_path == "/forced.jsonl"
    assert ctx.transcript_path == "/forced.jsonl"


def test_write_env_exports_appends(tmp_path: Path):
    env_file = tmp_path / "env"
    env_file.write_text('export REWIND_AGENT_KIND="old"\n')

    write_env_exports(
        env_file,
        {
            "REWIND_AGENT_KIND": "claude",
            "REWIND_PROJECT_ROOT": "/repo",
        },
    )

    text = env_file.read_text(encoding="utf-8")
    assert 'export REWIND_AGENT_KIND="old"' in text
    assert 'export REWIND_AGENT_KIND="claude"' in text
    assert 'export REWIND_PROJECT_ROOT="/repo"' in text
    assert text.rfind('export REWIND_AGENT_KIND="claude"') > text.rfind('export REWIND_AGENT_KIND="old"')
