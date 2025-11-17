# Hook Templates

These files contain **hook registrations only** - they go directly into `~/.claude/settings.json` or `~/.factory/settings.json`.

## Purpose

Hook templates define **what hooks to register** with Claude Code or Droid CLI. They tell the agent:
- Which events to listen for (PreToolUse, SessionStart, etc.)
- Which tools to match (Edit, Write, etc.)
- What command to run when the hook fires

## NOT for Script Configuration

These files do **NOT** contain script behavior parameters like:
- ❌ `antiSpam.minIntervalSeconds`
- ❌ `significance.minChangeSize`
- ❌ `criticalFiles` patterns

Those belong in `configs/*-tier.json` files, which are read by `smart-checkpoint.sh`.

## File Format

All hook templates follow the official Claude Code / Droid CLI hooks format:

```json
{
  "hooks": {
    "EventName": [
      {
        "matcher": "ToolPattern",
        "hooks": [
          {
            "type": "command",
            "command": "bash",
            "args": ["-c", "script.sh"],
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

## Available Templates

### minimal-hooks.json
- **Use case:** Minimal automation, team projects
- **Hooks:** PreToolUse (Write only)
- **Frequency:** ~2-5 checkpoints per session

### balanced-hooks.json (Recommended)
- **Use case:** General development, solo work
- **Hooks:** PreToolUse (Edit/Write/NotebookEdit), SessionStart
- **Frequency:** ~5-15 checkpoints per session

### aggressive-hooks.json
- **Use case:** Experimental work, learning, risky refactors
- **Hooks:** PreToolUse, UserPromptSubmit, PostToolUse, SessionStart, Stop
- **Frequency:** ~15-40 checkpoints per session

## Installation

The `install-hooks.sh` script will:
1. Read the appropriate hook template
2. Merge it into your `settings.json`
3. Preserve any existing settings
4. Separately copy tier configs to `~/.config/checkpoint-rewind/tiers/`

## See Also

- `../configs/` - Tier configuration files (script parameters)
- `../claude-hooks-examples/` - Reference examples with documentation
- `../bin/install-hooks.sh` - Installation script
