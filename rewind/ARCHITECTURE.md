# Architecture: Checkpoint & Rewind System

## Overview

This system provides automatic code checkpointing and conversation rewind for Claude Code and Droid CLI through a **clean separation of concerns**:

1. **Hook Registration** - Tells the agent which events to listen for
2. **Script Logic** - Implements the checkpoint decision-making
3. **Tier Parameters** - Configures script behavior

## The Separation Principle

```
┌─────────────────────────────────────────────┐
│ WHAT THE AGENT READS                        │
│ ~/.claude/settings.json                     │
│ ~/.factory/settings.json                    │
│                                             │
│ {                                           │
│   "hooks": {                                │
│     "PreToolUse": [{                        │
│       "matcher": "Edit|Write",              │
│       "hooks": [{                           │
│         "type": "command",                  │
│         "command": "bash",                  │
│         "args": ["-c", "smart-checkpoint..."]│
│       }]                                    │
│     }]                                      │
│   }                                         │
│ }                                           │
│                                             │
│ PURPOSE: Register which hooks fire          │
│ FORMAT: Official Claude/Droid hook syntax   │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│ WHAT THE SCRIPT READS                       │
│ ~/.config/checkpoint-rewind/tiers/*.json    │
│                                             │
│ {                                           │
│   "tier": "balanced",                       │
│   "antiSpam": {                             │
│     "enabled": true,                        │
│     "minIntervalSeconds": 30                │
│   },                                        │
│   "significance": {                         │
│     "enabled": true,                        │
│     "minChangeSize": 50                     │
│   }                                         │
│ }                                           │
│                                             │
│ PURPOSE: Configure script behavior          │
│ FORMAT: Custom JSON schema                  │
└─────────────────────────────────────────────┘
```

## File Structure

```
rewind/
├── hooks/                          # Hook templates (→ settings.json)
│   ├── minimal-hooks.json         # PreToolUse: Write only
│   ├── balanced-hooks.json        # PreToolUse: Edit/Write, SessionStart
│   ├── aggressive-hooks.json      # All hooks enabled
│   └── README.md                  # Explains hook format
│
├── configs/                        # Tier configs (→ ~/.config/...)
│   ├── minimal-tier.json          # No filtering
│   ├── balanced-tier.json         # 30s cooldown, 50 char min
│   ├── aggressive-tier.json       # 15s cooldown, 25 char min
│   └── README.md                  # Explains tier format
│
├── bin/
│   ├── install-hooks.sh           # Installer
│   │   • Copies hooks/ → settings.json
│   │   • Copies configs/ → ~/.config/checkpoint-rewind/tiers/
│   │   • Installs scripts → ~/.local/bin/
│   │   • Sets CHECKPOINT_TIER env var
│   │
│   ├── smart-checkpoint.sh        # Checkpoint logic
│   │   • Reads tier config from ~/.config/
│   │   • Implements anti-spam, significance detection
│   │   • Calls ClaudePoint
│   │   • Stores conversation metadata
│   │
│   └── checkpoint-rewind-full.sh  # Full rewind
│       • Restores code (ClaudePoint)
│       • Truncates conversation (JSONL)
│       • Provides resume instructions
│
├── lib/
│   ├── parsers/
│   │   └── SessionParser.js       # JSONL conversation parser
│   ├── metadata/
│   │   └── ConversationMetadata.js # Links checkpoints to messages
│   └── rewind/
│       └── ConversationTruncator.js # Safely truncates JSONL
│
└── claude-hooks-examples/          # Reference examples
    ├── minimal-hooks.json
    ├── balanced-hooks.json
    └── aggressive-hooks.json
```

## Installation Flow

```
./bin/install-hooks.sh balanced
    ↓
┌─────────────────────────────────────────────┐
│ 1. Copy Scripts                             │
│    hooks/ → settings.json (HOOKS ONLY)      │
│    configs/ → ~/.config/.../tiers/          │
│    bin/* → ~/.local/bin/                    │
│    lib/* → ~/.local/lib/checkpoint-rewind/  │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│ 2. Merge Hooks                              │
│    Read: hooks/balanced-hooks.json          │
│    Merge into: ~/.claude/settings.json      │
│    (preserves existing settings)            │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│ 3. Set Environment                          │
│    Add to ~/.bashrc or ~/.zshrc:            │
│    export CHECKPOINT_TIER=balanced          │
└─────────────────────────────────────────────┘
```

## Runtime Flow

```
User: "Edit app.js"
    ↓
Claude Code processes prompt
    ↓
PreToolUse hook fires (from settings.json)
    ↓
~/.local/bin/smart-checkpoint.sh pre-modify "Edit" "session-123"
    ↓
┌─────────────────────────────────────────────┐
│ smart-checkpoint.sh                         │
│                                             │
│ 1. Load config:                             │
│    TIER = $CHECKPOINT_TIER (env var)        │
│    Read ~/.config/.../tiers/${TIER}-tier.json│
│    Extract: antiSpam, significance params   │
│                                             │
│ 2. Check anti-spam:                         │
│    if <30s since last checkpoint:           │
│       exit 0 (skip)                         │
│                                             │
│ 3. Create checkpoint:                       │
│    claudepoint create -d "Auto: Before Edit"│
│                                             │
│ 4. Get conversation context:                │
│    node ~/.local/lib/.../SessionParser.js   │
│    Parse JSONL for latest user message      │
│                                             │
│ 5. Store metadata:                          │
│    node ~/.local/lib/.../ConversationMetadata.js│
│    Link checkpoint → message UUID           │
│                                             │
│ 6. Update tracker:                          │
│    echo $(date +%s) > ~/.claude-checkpoints/session-123.last│
└─────────────────────────────────────────────┘
    ↓
Hook completes, Edit proceeds
```

## Configuration Lookup Chain

### For Hook Registration (what fires):

```
1. Agent reads: ~/.claude/settings.json
2. Finds: hooks.PreToolUse[0].hooks[0].command
3. Executes: bash -c "~/.local/bin/smart-checkpoint.sh ..."
```

### For Script Behavior (how it behaves):

```
1. Script reads: $CHECKPOINT_TIER env var (default: "balanced")
2. Loads: ~/.config/checkpoint-rewind/tiers/${TIER}-tier.json
3. Extracts: antiSpam.minIntervalSeconds, significance.minChangeSize
4. Applies: those parameters to decision logic
```

## Tier Switching

```bash
# Switch tier
export CHECKPOINT_TIER=aggressive

# Restart agent
# Now smart-checkpoint.sh loads aggressive-tier.json
# Hook registration stays the same!
```

**Key insight:** You can change behavior WITHOUT reinstalling hooks.

## Why This Architecture?

### ❌ Old (Broken) Approach

```
configs/balanced.json contained:
{
  "hooks": {...},           # Hook registration
  "antiSpam": {...}         # Script params
}

Installed by copying entire file → settings.json
Result: Claude Code gets "antiSpam" field it doesn't understand
```

### ✅ New (Clean) Approach

```
hooks/balanced-hooks.json:
{
  "hooks": {...}            # ONLY hook registration
}

configs/balanced-tier.json:
{
  "antiSpam": {...}         # ONLY script params
}

Installed separately:
• hooks/ → settings.json (agent reads)
• configs/ → ~/.config/ (script reads)
```

## Agent Compatibility

### Claude Code

```
Hook registration: ~/.claude/settings.json
Tier config: ~/.config/checkpoint-rewind/tiers/
Sessions: ~/.claude/projects/<project>/<session>.jsonl
Checkpoints: .claudepoint/ in project
```

### Droid CLI

```
Hook registration: ~/.factory/settings.json
Tier config: ~/.config/checkpoint-rewind/tiers/ (SAME!)
Sessions: ~/.factory/sessions/<session>.jsonl
Checkpoints: .claudepoint/ in project (SAME!)
```

**The only difference is settings.json location. Everything else is universal.**

## Environment Variables

### Set by Installation

```bash
CHECKPOINT_TIER=balanced    # Which tier config to load
```

### Available to Hooks (from agent)

```bash
SESSION_ID                  # Current session ID
TOOL_NAME                   # Tool being used (Edit, Write, etc.)
TOOL_INPUT                  # JSON of tool parameters
CLAUDE_PROJECT_DIR          # Claude Code: project root
FACTORY_PROJECT_DIR         # Droid CLI: project root
```

## Dependencies

### Required

- **Node.js** - For SessionParser, ConversationMetadata, Truncator
- **jq** - For parsing tier configs
- **ClaudePoint** - For code checkpoint storage (`npm install -g claudepoint`)

### Optional

- **tmux** - For auto-resume functionality (Phase 3)
- **git** - For conversation branching (Phase 4)

## Debugging

### Check Hook Registration

```bash
# Claude Code
cat ~/.claude/settings.json | jq '.hooks'

# Droid CLI
cat ~/.factory/settings.json | jq '.hooks'
```

### Check Tier Config

```bash
echo $CHECKPOINT_TIER
cat ~/.config/checkpoint-rewind/tiers/${CHECKPOINT_TIER}-tier.json
```

### Check Installed Scripts

```bash
ls -la ~/.local/bin/smart-checkpoint.sh
ls -la ~/.local/lib/checkpoint-rewind/
```

### Test Hook Execution

```bash
# Manually trigger
echo '{}' | ~/.local/bin/smart-checkpoint.sh pre-modify "Test" "test-session"
```

## Migration from Old Architecture

If you installed before the unfuck:

```bash
# 1. Backup
cp ~/.claude/settings.json ~/.claude/settings.json.old

# 2. Clean old installation
rm -rf ~/.config/checkpoint-rewind

# 3. Reinstall
cd ~/rewind
./bin/install-hooks.sh balanced

# 4. Restart agent
```

Old settings.json will be backed up, new one will have clean hook registration only.

## Summary

**The Key Rule:**

- **hooks/** = Agent reads (what fires)
- **configs/** = Script reads (how it behaves)

**Never mix them.**

This architecture ensures:
✅ Clean separation of concerns
✅ Easy tier switching
✅ No pollution of settings.json
✅ Agent-agnostic design
✅ Installation can be deleted after setup
