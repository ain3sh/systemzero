# System Zero Rewind v4.0 - Implementation Specification

## Overview

Rewind is an automatic checkpointing system for AI coding agents (Claude Code, Droid CLI) that captures both **code snapshots** and **conversation state** together, enabling atomic rollback of both.

---

## Problem Solved

1. **Original Issue**: JS implementation failed because `node` (via nvm) wasn't in hook subprocess PATH
2. **Solution**: Full Python rewrite using stdlib only - Python is universally available

---

## Architecture Decisions

### Language & Dependencies
- **Python 3.9+** - Zero external dependencies (stdlib only)
- Uses: `tarfile`, `json`, `pathlib`, `dataclasses`, `argparse`, `shutil`, `tempfile`

### Storage Locations
| Type | Location |
|------|----------|
| **System install** | `~/.rewind/system/` |
| **Global config** | `~/.rewind/config.json` |
| **Project checkpoints** | `.agent/rewind/` (in project root) |
| **Global checkpoints** | `~/.rewind/storage/<project-hash>/` |

### Session Files (Source of Truth)
Both Claude Code and Droid use JSONL files where each line is an independent message event. **Manually verified**: modifying these files and reloading the session reflects changes correctly.

| Agent | Session Location | Key Fields |
|-------|------------------|------------|
| Claude Code | `~/.claude/projects/<path>/<session-id>.jsonl` | `uuid`, `parentUuid`, `message.content[]` |
| Droid | `~/.factory/sessions/<path>/<session-id>.jsonl` | `id`, `parentId`, `message.content[]` |

Both formats support branching via parent references, but for v4 we use simple truncation/restoration.

---

## Directory Structure

### Source Repository
```
rewind/
├── bin/
│   ├── rewind                         # CLI entry point
│   ├── smart-checkpoint               # Hook entry point (shell shim)
│   └── rewind-checkpoint-ignore.json  # Ignore patterns
├── tiers/
│   ├── minimal.json                   # Session start only
│   ├── balanced.json                  # File edits + session start
│   └── aggressive.json                # + bash, prompts, session end
├── src/                               # Python package
│   ├── __init__.py
│   ├── cli.py                         # CLI commands
│   ├── config/
│   │   ├── __init__.py
│   │   ├── schemas.py                 # Dataclasses for config
│   │   └── loader.py                  # Config loading/merging
│   ├── core/
│   │   ├── __init__.py
│   │   ├── controller.py              # Main orchestrator
│   │   ├── checkpoint_store.py        # Code snapshots (tar.gz)
│   │   └── context_manager.py         # Conversation tracking
│   ├── hooks/
│   │   ├── __init__.py
│   │   ├── __main__.py                # Hook entry point
│   │   ├── types.py                   # Hook input dataclasses
│   │   ├── io.py                      # Hook I/O (exit codes, etc.)
│   │   └── handler.py                 # Decision logic
│   └── utils/
│       ├── __init__.py
│       ├── fs.py                      # Atomic writes, file ops
│       ├── env.py                     # Environment detection
│       └── hook_merger.py             # Smart settings.json merger
├── tests/
├── install.sh
├── pyproject.toml
└── docs/
```

### Installed Structure (`~/.rewind/`)
```
~/.rewind/
├── config.json                        # Global config (tier, storage mode)
└── system/
    ├── src/                           # Python package
    ├── tiers/                         # Tier definitions
    ├── smart-checkpoint               # Hook entry point
    ├── bin-rewind                     # CLI script
    └── rewind-checkpoint-ignore.json
```

### Project Checkpoint Structure (`.agent/rewind/`)
```
.agent/rewind/
├── config.json                        # Project-specific config
├── session.json                       # Current session info (transcript_path, etc.)
├── hook-state.json                    # Anti-spam state
├── checkpoints/
│   └── 20241229_143052_001/
│       ├── metadata.json              # Checkpoint metadata
│       ├── snapshot.tar.gz            # Code snapshot
│       └── transcript.jsonl           # Conversation snapshot
└── transcript-backup/                 # Backup before restore
    └── 20241229_150000.jsonl
```

---

## Hook System

### Hook Entry Point
`~/.rewind/system/smart-checkpoint <action>`

Shell shim calls: `python3 -m src.hooks <action>`

### Hook Protocol
| Exit Code | Meaning |
|-----------|---------|
| 0 | Allow action (no stdout for PreToolUse) |
| 1 | Non-blocking error (stderr shown to user) |
| 2 | Block action (stderr shown to agent) |

### Hook Events

| Event | Action | Behavior |
|-------|--------|----------|
| `SessionStart` (startup) | `session-start` | Store `transcript_path` in `session.json`, create initial checkpoint |
| `PreToolUse` (Edit\|Write\|MultiEdit\|Create) | `pre-tool-use` | Create code checkpoint (with anti-spam) |
| `PostToolUse` (any) | `post-tool-use` | **Warn if `.agent/rewind/` doesn't exist** |
| `Stop` | `stop` | Create final checkpoint (aggressive tier) |

### Anti-Spam
- Configurable minimum interval between checkpoints (default: 30s for balanced)
- State persisted in `.agent/rewind/hook-state.json`

---

## Checkpoint Flow

### Code Checkpoint (via PreToolUse hook)
```
1. Hook receives: { transcript_path, session_id, tool_name, tool_input, ... }
2. Anti-spam check (skip if too soon)
3. Collect files (respecting ignore patterns)
4. Create tar.gz archive → checkpoints/<timestamp>/snapshot.tar.gz
5. Copy transcript → checkpoints/<timestamp>/transcript.jsonl
6. Write metadata.json
7. Exit 0 (allow the tool to proceed)
```

### Session Initialization (via SessionStart hook)
```
1. Hook receives: { transcript_path, session_id, source, ... }
2. Only act on source="startup"
3. Store session info → .agent/rewind/session.json:
   {
     "transcript_path": "/home/user/.factory/sessions/.../abc.jsonl",
     "session_id": "abc",
     "agent": "droid"  // or "claude"
   }
4. Create initial checkpoint
5. Exit 0
```

---

## Restore Flow

### `rewind restore <checkpoint>` (user-initiated, external shell)
```
1. Read .agent/rewind/session.json to get transcript_path
2. Backup current state:
   - Code: Create backup checkpoint
   - Transcript: Copy to transcript-backup/<timestamp>.jsonl
3. Record restore in .agent/rewind/restore-history.json:
   {
     "timestamp": "...",
     "checkpoint": "<name>",
     "backup_checkpoint": "<backup-name>",
     "transcript_backup": "transcript-backup/<timestamp>.jsonl"
   }
4. Restore code: Extract snapshot.tar.gz to project root
5. Restore transcript: Copy checkpoint's transcript.jsonl → transcript_path
6. Print: "Restored to <checkpoint>. Reload your agent session."
```

### `rewind undo-restore` (undo the last restore)
```
1. Read .agent/rewind/restore-history.json
2. Restore code from backup checkpoint
3. Restore transcript from transcript-backup/
4. Clear restore history entry
```

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `rewind init [--mode project\|global]` | Initialize rewind for project |
| `rewind save [description]` | Manual checkpoint |
| `rewind list [--all]` | List checkpoints |
| `rewind restore <name> [--code-only\|--context-only]` | Restore checkpoint |
| `rewind undo` | Restore to previous checkpoint |
| `rewind undo-restore` | Undo last restore operation |
| `rewind status` | Show system status |
| `rewind validate` | Validate configuration |
| `rewind gc [--keep N]` | Garbage collect old checkpoints |
| `rewind config` | Show current config |
| `rewind config --tier <name>` | Change tier |
| `rewind config --register-hooks` | Register hooks in settings.json |
| `rewind config --unregister-hooks` | Remove hooks from settings.json |

---

## Tier Configurations

### Consolidated Tier Files (`tiers/<name>.json`)
Each tier file contains **both** runtime config and hook registration:

```json
{
  "tier": "balanced",
  "description": "Smart checkpointing before file edits with 30s anti-spam.",
  
  "runtime": {
    "antiSpam": { "enabled": true, "minIntervalSeconds": 30 },
    "significance": { "enabled": true, "minChangeSize": 50 }
  },
  
  "hooks": {
    "PreToolUse": [...],
    "SessionStart": [...]
  }
}
```

| Tier | Anti-Spam | Hooks |
|------|-----------|-------|
| minimal | Disabled | SessionStart only |
| balanced | 30s | SessionStart, PreToolUse (file edits) |
| aggressive | 15s | + PostToolUse (Bash), UserPromptSubmit, Stop |

---

## Installation Flow

### `./install.sh`
```
1. Check prerequisites (Python 3.9+, git)
2. Copy to ~/.rewind/system/
3. Symlink ~/.local/bin/rewind → ~/.rewind/system/bin-rewind
4. Prompt: Select tier (minimal/balanced/aggressive)
5. Extract runtime config → ~/.rewind/config.json
6. Prompt: Register hooks? [Y/n]
7. If yes: Smart merge hooks into ~/.factory/settings.json and/or ~/.claude/settings.json
   - Uses hook_merger.py which ONLY touches rewind hooks
   - Never overwrites non-rewind hooks
8. On existing install: Only re-registers hooks if user confirms
```

### Smart Hook Merger
- Identifies rewind hooks by `"smart-checkpoint"` in command
- Removes existing rewind hooks before adding new ones
- Preserves all other hooks untouched

---

## Key Implementation Notes

### Conversation Checkpointing
- No separate hook needed - transcript is just copied during code checkpoint
- Both Claude Code and Droid session files are source-of-truth
- Restore requires user to reload session (expected behavior)

### PostToolUse Warning
If `.agent/rewind/` doesn't exist when a file-modifying tool runs:
```python
print("[rewind] Warning: No .agent/rewind/ found. Run 'rewind init' first.", file=sys.stderr)
# Exit 0 - don't block, just warn
```

### Agent Isolation
- Agent never knows about checkpoints
- Restore is always user-initiated from external shell
- No way for agent to manipulate checkpoints

---

## Files to Create/Modify

### New Files
- `src/core/controller.py` - Add `session.json` handling, transcript backup/restore
- `src/hooks/handler.py` - Add PostToolUse warning, SessionStart transcript storage
- `src/cli.py` - Add `undo-restore` command

### Key Changes Summary
1. SessionStart hook stores `transcript_path` in `session.json`
2. Code checkpoints also copy transcript
3. Restore backs up current transcript before overwriting
4. New `undo-restore` command to revert a restore
5. PostToolUse hook warns if not initialized