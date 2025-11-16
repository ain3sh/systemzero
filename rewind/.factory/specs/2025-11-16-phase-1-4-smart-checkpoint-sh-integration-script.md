# Next Step: Implement smart-checkpoint.sh - The Integration Layer

## What We're Building
A bash script that gets called by hooks and orchestrates:
1. ClaudePoint (creates code checkpoint)
2. SessionParser (reads current session, finds latest message)
3. ConversationMetadata (links checkpoint to conversation turn)

## Ground Truth References (Read Before Coding)

**📖 MUST READ FIRST:**
- `AGENT_REMINDERS.md` lines 235-275 - Quality checklist, testing mantras
- `CLAUDEPOINT_ACTUAL_BEHAVIOR.md` - ClaudePoint CLI verified behavior
- `lib/parsers/SessionParser.js` lines 196-237 - CLI interface we built
- `lib/metadata/ConversationMetadata.js` lines 101-150 - CLI interface we built

**✅ What We VERIFIED Works:**
- ClaudePoint: `claudepoint create -d "description"` → checkpoint in `.claudepoint/snapshots/`
- SessionParser: `node SessionParser.js current-session` → finds active session file
- SessionParser: `node SessionParser.js latest-user` → gets last user message JSON
- ConversationMetadata: `node ConversationMetadata.js add <name> '<json>'` → stores metadata

## Implementation Plan

### File: `bin/smart-checkpoint.sh`

**Purpose:** Hook script that:
1. Checks anti-spam (30s cooldown for balanced tier)
2. Calls `claudepoint create -d "Auto: Before ${TOOL_NAME}"`
3. Extracts checkpoint name from ClaudePoint output
4. Calls SessionParser to get current session + latest user message
5. Calls ConversationMetadata to link checkpoint to conversation
6. Handles errors gracefully (missing session OK, ClaudePoint failure NOT OK)

**Key Design Decisions:**
- **No hardcoded paths** - Detect agent (Claude/Droid) from environment
- **Fail gracefully** - If session not found, still create checkpoint (code-only mode)
- **Parse real output** - Extract checkpoint name from ClaudePoint's actual output format
- **State in temp files** - Use `~/.claude-checkpoints/${SESSION_ID}.last` for anti-spam

### File: `configs/balanced-tier.json`

**Purpose:** Configuration that smart-checkpoint.sh loads

```json
{
  "tier": "balanced",
  "antiSpam": {
    "enabled": true,
    "minIntervalSeconds": 30
  },
  "significance": {
    "enabled": true,
    "minChangeSize": 50
  }
}
```

### File: `bin/install-hooks.sh`

**Purpose:** Installs hooks into `.claude/settings.json` or `.factory/settings.json`

**What it does:**
1. Detects which agents are installed (Claude Code, Droid CLI)
2. Backs up existing settings
3. Installs PreToolUse hook that calls `smart-checkpoint.sh`
4. Adds SessionStart hook for initial checkpoint
5. Provides instructions for restart

## Testing Strategy (NO MOCKS!)

**Test 1: Manual invocation**
```bash
cd /tmp/test-project
export TOOL_NAME="Edit"
export SESSION_ID="test-123"
./bin/smart-checkpoint.sh pre-tool-use
# Verify: checkpoint created, metadata stored
```

**Test 2: With real Claude session**
```bash
cd ~ # Directory with actual Claude sessions
export SESSION_ID=$(basename ~/.claude/projects/-home-*/agent-*.jsonl .jsonl | head -1)
export TOOL_NAME="Write"
./bin/smart-checkpoint.sh pre-tool-use
# Verify: checkpoint has conversation metadata with real message UUID
```

**Test 3: Anti-spam**
```bash
# Call twice within 30 seconds
./bin/smart-checkpoint.sh pre-tool-use
sleep 5
./bin/smart-checkpoint.sh pre-tool-use
# Verify: Second call skipped (anti-spam working)
```

**Test 4: Missing session (graceful degradation)**
```bash
cd /tmp/no-sessions-here
export SESSION_ID="nonexistent"
./bin/smart-checkpoint.sh pre-tool-use
# Verify: Checkpoint created, metadata shows sessionId: null (graceful)
```

## Success Criteria

- [ ] Script creates checkpoint via ClaudePoint
- [ ] Extracts checkpoint name from output correctly
- [ ] Finds current session when available
- [ ] Stores conversation metadata when session exists
- [ ] Handles missing session gracefully (code-only checkpoint)
- [ ] Anti-spam prevents duplicate checkpoints within 30s
- [ ] All tested with REAL files, not mocks
- [ ] Error messages helpful (not crashes)

## What NOT to Do (Reminders)

❌ Don't hardcode paths like `/home/ain3sh/.claude`
❌ Don't mock ClaudePoint output - parse the real output
❌ Don't assume session exists - handle gracefully if missing
❌ Don't skip error handling - ClaudePoint failures should abort
❌ Don't write tests that just check "script exists" - run it for real

## Estimated Time
- smart-checkpoint.sh: 1 hour (with proper testing)
- Config files: 15 minutes
- install-hooks.sh: 30 minutes
- Integration testing: 30 minutes
- **Total: 2-2.5 hours to working Phase 1**

## Files to Create
1. `bin/smart-checkpoint.sh` - Main integration script
2. `configs/balanced-tier.json` - Configuration
3. `configs/minimal-tier.json` - Minimal config
4. `configs/aggressive-tier.json` - Aggressive config
5. `bin/install-hooks.sh` - Hook installation
6. `tests/test-smart-checkpoint.sh` - Real integration tests

## What Happens After This
Once smart-checkpoint.sh works:
- Install hooks in real Claude Code session
- Test automatic checkpoint creation during actual coding
- Verify metadata links checkpoints to conversation
- Move to Phase 2: Conversation rewind (JSONL truncation)

**This completes Phase 1: Automatic code checkpointing with conversation context tracking!**