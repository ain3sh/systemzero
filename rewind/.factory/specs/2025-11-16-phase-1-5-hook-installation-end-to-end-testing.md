# Next: Install Hooks and Test Phase 1 End-to-End

## What We're Building
Hook installation script + real-world testing of automatic checkpointing during actual coding session.

## Current Status Check
**What We Have:**
- ✅ smart-checkpoint.sh working (tested manually)
- ✅ SessionParser working (tested with real JSONL)
- ✅ ConversationMetadata working (tested with real checkpoints)
- ✅ Config files created (balanced/minimal/aggressive)
- ⚠️ User already has hooks installed in `~/.claude/settings.json`!

**Discovery:** User's `~/.claude/settings.json` already has hooks but calling DIFFERENT script:
```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Edit|Write|NotebookEdit",
      "command": "bash",
      "args": ["-c", "~/.local/bin/smart-checkpoint.sh pre-modify ..."]
    }]
  }
}
```

**Problem:** The args are wrong! It's calling `pre-modify` but our script expects `pre-tool-use`.

## Ground Truth References

**📖 READ BEFORE CODING:**
- `AGENT_REMINDERS.md` lines 1-60 - Core principles (no guessing, real tests)
- User's current hooks: `~/.claude/settings.json` (already exists!)
- Our script interface: `bin/smart-checkpoint.sh` line 1-30 (expects `pre-tool-use`)
- Claude Code version: 2.0.42 (confirmed working)

**✅ What We Know Works:**
- ClaudePoint installed: `claudepoint --version` → 1.4.4
- Claude Code installed: `claude --version` → 2.0.42
- Our script location: `bin/smart-checkpoint.sh` (needs to go to `~/.local/bin/`)
- Hook format: JSON in `~/.claude/settings.json`

## Implementation Plan

### File: `bin/install-hooks.sh`

**Purpose:** Install/update hooks in agent settings

**Key Design Decisions:**
1. **DON'T overwrite existing settings blindly** - Merge with existing hooks
2. **Backup before any changes** - User has custom env/permissions settings
3. **Install script to ~/.local/bin/** - Make it globally accessible
4. **Copy Node.js modules too** - SessionParser and ConversationMetadata need to be accessible
5. **Detect what's already installed** - Don't duplicate, just update

**What it does:**
```bash
1. Detect agents (Claude Code: ~/.claude/, Droid CLI: ~/.factory/)
2. Backup existing settings.json → settings.json.backup.TIMESTAMP
3. Copy bin/smart-checkpoint.sh → ~/.local/bin/
4. Copy lib/ directory → ~/.local/lib/checkpoint-rewind/
5. Read existing settings.json
6. Merge our hooks (PreToolUse, SessionStart)
7. Write updated settings.json
8. Verify Node.js is available
9. Print restart instructions
```

**Merge Strategy (CRITICAL):**
```bash
# User's existing settings.json has:
# - env variables
# - permissions
# - Maybe other hooks

# We need to:
# 1. Preserve all existing keys (env, permissions, etc.)
# 2. Add/update only hooks section
# 3. Use jq for JSON manipulation (safer than sed/awk)
```

### Installation Steps

**1. Copy files to system locations:**
```bash
~/.local/bin/smart-checkpoint.sh           # Main script
~/.local/lib/checkpoint-rewind/            # Our modules
  ├── parsers/
  │   └── SessionParser.js
  └── metadata/
      └── ConversationMetadata.js
```

**2. Update ~/.claude/settings.json:**
```json
{
  "env": { ... },              // PRESERVE existing
  "permissions": { ... },      // PRESERVE existing
  "hooks": {                   // ADD/UPDATE our hooks
    "PreToolUse": [{
      "matcher": "Edit|Write|NotebookEdit",
      "hooks": [{
        "type": "command",
        "command": "bash",
        "args": ["-c", "~/.local/bin/smart-checkpoint.sh pre-tool-use"],
        "timeout": 10
      }]
    }],
    "SessionStart": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "bash",
        "args": ["-c", "~/.local/bin/smart-checkpoint.sh session-start"],
        "timeout": 5
      }]
    }]
  }
}
```

### Testing Strategy (NO MOCKS!)

**Test 1: Installation in dry-run mode**
```bash
./bin/install-hooks.sh --dry-run
# Verify: Shows what would be changed
# Verify: No files actually modified
```

**Test 2: Real installation**
```bash
./bin/install-hooks.sh balanced
# Verify: Backup created ~/.claude/settings.json.backup.*
# Verify: Script copied to ~/.local/bin/
# Verify: Modules copied to ~/.local/lib/checkpoint-rewind/
# Verify: settings.json has our hooks + preserved existing settings
```

**Test 3: Start Claude and make a change**
```bash
cd ~/test-project
claude
# In Claude: "Create a file test.js"
# Exit Claude
claudepoint list
# Verify: "Auto: Before Write" checkpoint exists
```

**Test 4: Check conversation metadata**
```bash
cd ~/test-project
cat .claudepoint/conversation_metadata.json | jq
# Verify: Checkpoint has sessionId, messageUuid, userPrompt
```

**Test 5: Verify hook called on each tool use**
```bash
cd ~/test-project  
claude
# In Claude: "Edit test.js and add a comment"
# Wait 30+ seconds
# In Claude: "Edit test.js and add another comment"
# Exit
claudepoint list
# Verify: 2 checkpoints (anti-spam worked - second edit after 30s)
```

## Edge Cases to Handle

**1. No ~/.local/bin/ exists**
```bash
mkdir -p ~/.local/bin
# Add to PATH if not already there
```

**2. User has no settings.json**
```bash
# Create new with just our hooks
```

**3. User has settings.json but no hooks key**
```bash
# Add hooks key with our config
```

**4. jq not installed**
```bash
# Provide manual merge instructions
# OR use Python json module as fallback
```

**5. Node.js not found**
```bash
# Error with installation instructions
```

## Success Criteria

**Installation:**
- [ ] Backup created with timestamp
- [ ] Script installed to ~/.local/bin/
- [ ] Modules installed to ~/.local/lib/checkpoint-rewind/
- [ ] settings.json updated with our hooks
- [ ] Existing env/permissions preserved
- [ ] No syntax errors in settings.json

**Runtime:**
- [ ] Hook fires on Write/Edit/NotebookEdit
- [ ] Checkpoint created via ClaudePoint
- [ ] Conversation metadata stored
- [ ] Anti-spam prevents rapid checkpoints
- [ ] SessionStart hook creates initial checkpoint
- [ ] All tested in REAL Claude Code session

## What NOT to Do (Reminders)

❌ Don't overwrite user's settings.json without backup
❌ Don't assume jq is installed - provide fallback
❌ Don't hardcode paths - detect home directory
❌ Don't skip error checking - installation can fail
❌ Don't test with fake hooks - use real Claude Code session

## Implementation Details

### Merge Logic (Using jq)
```bash
# Read existing settings
EXISTING=$(cat ~/.claude/settings.json)

# Merge with our hooks
echo "$EXISTING" | jq '. + {
  "hooks": {
    "PreToolUse": [{
      "matcher": "Edit|Write|NotebookEdit",
      "hooks": [{
        "type": "command",
        "command": "bash",
        "args": ["-c", "~/.local/bin/smart-checkpoint.sh pre-tool-use"],
        "timeout": 10
      }]
    }],
    "SessionStart": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "bash",
        "args": ["-c", "~/.local/bin/smart-checkpoint.sh session-start"],
        "timeout": 5
      }]
    }]
  }
}' > ~/.claude/settings.json.new

# Validate JSON
if jq empty ~/.claude/settings.json.new 2>/dev/null; then
  mv ~/.claude/settings.json.new ~/.claude/settings.json
else
  echo "ERROR: Invalid JSON generated"
  exit 1
fi
```

## Estimated Time
- install-hooks.sh implementation: 45 minutes
- Testing installation: 15 minutes
- End-to-end testing with Claude: 30 minutes
- **Total: 1.5 hours to fully working Phase 1**

## Files to Create/Modify
1. `bin/install-hooks.sh` - Hook installer script
2. Test in real Claude Code session (no mock!)

## What Happens After This

**Phase 1 COMPLETE!** We'll have:
- ✅ Automatic code checkpointing during coding
- ✅ Conversation context linked to checkpoints
- ✅ Agent-agnostic infrastructure ready
- ✅ Tested end-to-end in real workflow

**Next:** Phase 2 - Conversation Rewind
- JSONL truncation script
- checkpoint-rewind-full.sh command
- Test conversation restoration with real sessions

**This completes Phase 1: Automatic code checkpointing with conversation metadata!** 🎉