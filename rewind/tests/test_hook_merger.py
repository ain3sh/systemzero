from __future__ import annotations


from src.utils.hook_merger import merge_hooks


def test_merge_hooks_preserves_non_event_metadata_in_hooks_object() -> None:
    settings = {
        "hooks": {
            "claudeHooksImported": True,
            "importedClaudeHooks": [],
            "SessionStart": [
                {
                    "matcher": "startup",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "/home/ain3sh/.openskills/bin/openskills-session-hook",
                            "timeout": 10,
                        }
                    ],
                }
            ],
        }
    }

    tier_hooks = {
        "SessionStart": [
            {
                "matcher": "startup",
                "hooks": [
                    {
                        "type": "command",
                        "command": "~/.rewind/system/smart-checkpoint session-start",
                        "timeout": 5,
                    }
                ],
            }
        ],
        "PreToolUse": [
            {
                "matcher": "Edit|Write",
                "hooks": [
                    {
                        "type": "command",
                        "command": "~/.rewind/system/smart-checkpoint pre-tool-use",
                        "timeout": 10,
                    }
                ],
            }
        ],
    }

    updated = merge_hooks(settings, tier_hooks, remove_only=False)

    assert updated["hooks"]["claudeHooksImported"] is True
    assert updated["hooks"]["importedClaudeHooks"] == []
    assert updated["hooks"]["SessionStart"][0]["hooks"][0]["command"].endswith(
        "openskills-session-hook"
    )
    assert "smart-checkpoint" in updated["hooks"]["SessionStart"][1]["hooks"][0]["command"]
    assert "PreToolUse" in updated["hooks"]


def test_merge_hooks_remove_only_removes_rewind_hooks_without_touching_metadata() -> None:
    settings = {
        "hooks": {
            "claudeHooksImported": True,
            "SessionStart": [
                {
                    "matcher": "startup",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "~/.rewind/system/smart-checkpoint session-start",
                            "timeout": 5,
                        }
                    ],
                },
                {
                    "matcher": "startup",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "/home/ain3sh/.openskills/bin/openskills-session-hook",
                            "timeout": 10,
                        }
                    ],
                },
            ],
        }
    }

    updated = merge_hooks(settings, tier_hooks={}, remove_only=True)

    assert updated["hooks"]["claudeHooksImported"] is True
    assert len(updated["hooks"]["SessionStart"]) == 1
    assert updated["hooks"]["SessionStart"][0]["hooks"][0]["command"].endswith(
        "openskills-session-hook"
    )
