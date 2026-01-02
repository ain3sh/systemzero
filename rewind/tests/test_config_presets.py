from __future__ import annotations

import json
from pathlib import Path

from src.config.loader import ConfigLoader
from src.utils.resources import read_json_resource


def _write_global_config(tmp_home: Path, data: dict) -> None:
    cfg_dir = tmp_home / ".rewind"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.json").write_text(json.dumps(data, indent=2), encoding="utf-8")


def test_preset_only_uses_preset_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_global_config(tmp_path, {"preset": "balanced", "storage": {"mode": "project"}})

    preset = read_json_resource("schemas", "tiers", "balanced.json")
    expected_interval = preset["runtime"]["antiSpam"]["minIntervalSeconds"]

    loader = ConfigLoader(project_root=tmp_path / "proj")
    cfg = loader.load()
    assert cfg.tier.tier == "balanced"
    assert cfg.tier.anti_spam.min_interval_seconds == expected_interval


def test_runtime_overrides_merge_on_top_of_preset(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_global_config(
        tmp_path,
        {
            "preset": "balanced",
            "runtime": {"antiSpam": {"minIntervalSeconds": 5}},
            "storage": {"mode": "project"},
        },
    )

    loader = ConfigLoader(project_root=tmp_path / "proj")
    cfg = loader.load()
    assert cfg.tier.tier == "balanced"
    assert cfg.tier.anti_spam.min_interval_seconds == 5


def test_load_tier_config_uses_global_config(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_global_config(
        tmp_path,
        {
            "preset": "aggressive",
            "runtime": {"antiSpam": {"minIntervalSeconds": 3}},
            "storage": {"mode": "project"},
        },
    )

    loader = ConfigLoader(project_root=tmp_path / "proj")
    tier = loader.load_tier_config(None)
    assert tier.tier == "aggressive"
    assert tier.anti_spam.min_interval_seconds == 3
