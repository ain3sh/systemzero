from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_home(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Prevent developer machine `~/.rewind/config.json` from influencing tests."""

    monkeypatch.setenv("HOME", str(tmp_path))
