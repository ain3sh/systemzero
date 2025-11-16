# Phase 1.6: Test Deployed System + Build Conversation Rewind

## Mega-Think Summary: What We've Built & What's Next

### Current State (VERIFIED)
✅ **Deployed to system:**
- `~/.local/bin/smart-checkpoint.sh` - Integration script
- `~/.local/lib/checkpoint-rewind/parsers/SessionParser.js` - JSONL reader
- `~/.local/lib/checkpoint-rewind/metadata/ConversationMetadata.js` - Metadata storage
- `~/.claude/settings.json` - Hooks installed (backed up)
- `~/.factory/settings.json` - Hooks installed (backed up)

✅ **What works (tested with mocks/manual):**
- SessionParser reads real JSONL from `~/.claude/projects/`
- ConversationMetadata stores/reads checkpoint metadata
- smart-checkpoint.sh creates checkpoints via ClaudePoint
- Hooks configured to fire on Edit/Write/NotebookEdit

⏳ **What's NOT tested yet:**
- Real coding session with Claude (end-to-end)
- Hooks actually firing during tool use
- Metadata capture during real workflow

### The Gap We're Closing

**Anthropic's `/rewind`:**
1. ✅ Code checkpoints (instant restore)
2. ✅ Conversation truncation (removes bad instructions from context)
3. ✅ Three modes: code-only, conversation-only, both
4. ⚠️ Visual UI (ESC ESC) - we can't replicate
5. ⚠️ Instant (no restart) - we need 10-20s restart

**Our system status:**
- Code checkpoints: ✅ 95% done (just needs real-world test)
- Conversation rewind: 🟡 60% done (can read/store, can't truncate yet)
- Overall parity: **70-75%**

---

## Ground Truth References (READ THESE!)

**📖 Core Principles:**
- `AGENT_REMINDERS.md` lines 1-80 - Real tests, no guessing, failures are information
- `CONVERSATION_REWIND_DEEP_DIVE.md` lines 1-350 - Four approaches evaluated

**📖 JSONL Format:**
- Claude Code: `~/.claude/projects/<project-dir>/<session-id>.jsonl`
- Droid CLI: `~/.factory/sessions/<session-id>.jsonl`
- Each line is JSON: `{"type": "messageStart", "uuid": "msg-xxx", ...}`
- To truncate: Read lines until `uuid == target`, write only those

**📖 Our Metadata Format (from ConversationMetadata.js lines 10-25):**
```json
{
  "checkpoint_name": {
    "agent": "claude-code",
    "sessionId": "abc-123",
    "sessionFile": "/home/user/.claude/projects/xyz/abc-123.jsonl",
    "messageUuid": "msg-456",
    "messageIndex": 42,
    "userPrompt": "Create a new feature",
    "timestamp": "2025-11-16T12:00:00Z"
  }
}
```

**📖 What SessionParser provides (tested!):**
- `getCurrentSession()` - Finds active JSONL file
- `getLatestUserMessage()` - Gets last user prompt with UUID
- Agent detection (claude-code vs droid-cli)
- Error handling for missing sessions

---

## Implementation Plan

### Part A: End-to-End Test (30 minutes)

**Goal:** Verify Phase 1 works in real Claude Code session

**Steps:**
1. Create clean test directory
2. Start Claude Code
3. Make 3 code changes (create file, edit file, wait 30s, edit again)
4. Exit Claude
5. Verify:
   - Checkpoints created in `.claudepoint/snapshots/`
   - Metadata in `.claudepoint/conversation_metadata.json`
   - Anti-spam worked (only 2 checkpoints, not 3)
   - Metadata has correct sessionId, messageUuid, userPrompt

**Success Criteria:**
- ✅ Hooks fire on every tool use
- ✅ ClaudePoint creates checkpoint
- ✅ Metadata links checkpoint to conversation turn
- ✅ Anti-spam prevents rapid checkpoints
- ✅ No errors in output

**If it fails:**
- Check `~/.claude/settings.json` syntax
- Check hook script path (`~/.local/bin/smart-checkpoint.sh`)
- Check Node.js availability for SessionParser
- Read actual error messages (don't guess!)

---

### Part B: Conversation Truncator (1-1.5 hours)

**File:** `lib/rewind/ConversationTruncator.js`

**Purpose:** Safely truncate JSONL files to specific message UUID

**Why Node.js, not Python:**
- Consistency with SessionParser/ConversationMetadata
- Already tested Node.js works on this system
- JSONL line-by-line processing (Node streams excel here)

**Implementation:**

```javascript
#!/usr/bin/env node

/**
 * ConversationTruncator - Safely truncate JSONL conversation files
 * 
 * Truncates conversation to specific message UUID, creating backups.
 * Used for conversation rewind functionality.
 * 
 * Safety features:
 * - Creates timestamped backup before truncation
 * - Validates JSON on each line
 * - Atomic write (write to temp, then rename)
 * - Dry-run mode for testing
 */

import fs from 'fs/promises';
import { createReadStream, createWriteStream } from 'fs';
import { createInterface } from 'readline';
import path from 'path';

export class ConversationTruncator {
  constructor(sessionFile, options = {}) {
    this.sessionFile = path.resolve(sessionFile);
    this.dryRun = options.dryRun || false;
    this.verbose = options.verbose || false;
  }
  
  /**
   * Truncate conversation at specific message UUID
   * 
   * @param {string} messageUuid - Target message UUID
   * @returns {Object} - { success, linesKept, linesRemoved, backupFile }
   */
  async truncateAt(messageUuid) {
    // 1. Validate session file exists
    if (!await this.fileExists(this.sessionFile)) {
      throw new Error(`Session file not found: ${this.sessionFile}`);
    }
    
    // 2. Create backup
    const backupFile = await this.createBackup();
    this.log(`Created backup: ${backupFile}`);
    
    // 3. Read and truncate
    const { lines, targetFound } = await this.readUntilUuid(messageUuid);
    
    if (!targetFound) {
      throw new Error(`Message UUID not found: ${messageUuid}`);
    }
    
    // 4. Write truncated file (atomic)
    if (!this.dryRun) {
      await this.atomicWrite(lines);
    }
    
    // 5. Return stats
    const originalLineCount = await this.countLines(backupFile);
    return {
      success: true,
      linesKept: lines.length,
      linesRemoved: originalLineCount - lines.length,
      backupFile,
      messageUuid
    };
  }
  
  /**
   * Read JSONL until we find the target UUID
   */
  async readUntilUuid(targetUuid) {
    const lines = [];
    let targetFound = false;
    
    const fileStream = createReadStream(this.sessionFile);
    const rl = createInterface({
      input: fileStream,
      crlfDelay: Infinity
    });
    
    for await (const line of rl) {
      // Skip empty lines
      if (!line.trim()) continue;
      
      // Parse JSON
      let data;
      try {
        data = JSON.parse(line);
      } catch (e) {
        this.log(`WARNING: Skipping invalid JSON line: ${line.substring(0, 50)}...`);
        continue;
      }
      
      // Keep line
      lines.push(line);
      
      // Check if this is our target
      if (data.uuid === targetUuid) {
        targetFound = true;
        this.log(`Found target UUID at line ${lines.length}`);
        break;
      }
    }
    
    return { lines, targetFound };
  }
  
  /**
   * Create timestamped backup
   */
  async createBackup() {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const backupFile = `${this.sessionFile}.backup.${timestamp}`;
    
    if (!this.dryRun) {
      await fs.copyFile(this.sessionFile, backupFile);
    }
    
    return backupFile;
  }
  
  /**
   * Atomic write - write to temp file, then rename
   */
  async atomicWrite(lines) {
    const tempFile = `${this.sessionFile}.tmp`;
    
    // Write to temp file
    const content = lines.join('\n') + '\n';
    await fs.writeFile(tempFile, content, 'utf8');
    
    // Atomic rename
    await fs.rename(tempFile, this.sessionFile);
  }
  
  /**
   * Count lines in file
   */
  async countLines(filePath) {
    let count = 0;
    const fileStream = createReadStream(filePath);
    const rl = createInterface({
      input: fileStream,
      crlfDelay: Infinity
    });
    
    for await (const line of rl) {
      if (line.trim()) count++;
    }
    
    return count;
  }
  
  async fileExists(filePath) {
    try {
      await fs.access(filePath);
      return true;
    } catch {
      return false;
    }
  }
  
  log(message) {
    if (this.verbose) {
      console.log(`[ConversationTruncator] ${message}`);
    }
  }
}

// CLI interface
if (import.meta.url === `file://${process.argv[1]}`) {
  const [,, sessionFile, messageUuid, ...flags] = process.argv;
  
  if (!sessionFile || !messageUuid) {
    console.log('Usage: ConversationTruncator.js <session-file> <message-uuid> [--dry-run] [--verbose]');
    console.log('');
    console.log('Truncates JSONL conversation file at specified message UUID.');
    console.log('Creates automatic backup before truncation.');
    console.log('');
    console.log('Options:');
    console.log('  --dry-run   Show what would happen without making changes');
    console.log('  --verbose   Show detailed progress');
    console.log('');
    console.log('Examples:');
    console.log('  ConversationTruncator.js ~/.claude/projects/xyz/session.jsonl msg-456');
    console.log('  ConversationTruncator.js session.jsonl msg-123 --dry-run --verbose');
    process.exit(1);
  }
  
  const options = {
    dryRun: flags.includes('--dry-run'),
    verbose: flags.includes('--verbose') || flags.includes('--dry-run')
  };
  
  const truncator = new ConversationTruncator(sessionFile, options);
  
  try {
    const result = await truncator.truncateAt(messageUuid);
    console.log('');
    console.log('✅ Truncation complete!');
    console.log(`   Lines kept: ${result.linesKept}`);
    console.log(`   Lines removed: ${result.linesRemoved}`);
    console.log(`   Backup: ${result.backupFile}`);
    console.log('');
    
    if (options.dryRun) {
      console.log('(Dry run - no changes made)');
    }
  } catch (error) {
    console.error('❌ Error:', error.message);
    process.exit(1);
  }
}
```

**Testing Strategy (NO MOCKS!):**

```bash
# Test 1: Dry run on real session file
./lib/rewind/ConversationTruncator.js \
  ~/.claude/projects/*/agent-*.jsonl \
  msg-some-real-uuid \
  --dry-run --verbose

# Test 2: Real truncation on COPY of session
cp ~/.claude/projects/*/agent-*.jsonl /tmp/test-session.jsonl
./lib/rewind/ConversationTruncator.js \
  /tmp/test-session.jsonl \
  msg-some-real-uuid \
  --verbose

# Verify: Compare line counts
wc -l /tmp/test-session.jsonl*
# Should see: original.backup has more lines than truncated

# Test 3: Invalid UUID (should fail gracefully)
./lib/rewind/ConversationTruncator.js \
  /tmp/test-session.jsonl \
  msg-does-not-exist

# Expected: Error message, no crash
```

---

### Part C: Rewind Command (45 minutes)

**File:** `bin/checkpoint-rewind-full.sh`

**Purpose:** Orchestrate code + conversation rewind

**What it does:**
```bash
1. Read checkpoint metadata (sessionId, messageUuid)
2. Restore code via ClaudePoint
3. Truncate conversation via ConversationTruncator
4. Display resume instructions to user
```

**Implementation:**

```bash
#!/bin/bash
# checkpoint-rewind-full.sh
# Full rewind: code + conversation

set -euo pipefail

CHECKPOINT_NAME="$1"
PROJECT_ROOT="${2:-.}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔄 Full Rewind: Code + Conversation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 1. Read checkpoint metadata
echo "📖 Reading checkpoint metadata..."
METADATA_FILE="$PROJECT_ROOT/.claudepoint/conversation_metadata.json"

if [[ ! -f "$METADATA_FILE" ]]; then
    echo "❌ No conversation metadata found"
    echo "   This checkpoint has no conversation context."
    echo "   Use 'claudepoint undo' for code-only restore."
    exit 1
fi

METADATA=$(cat "$METADATA_FILE" | jq -r ".\"$CHECKPOINT_NAME\"")

if [[ "$METADATA" == "null" ]]; then
    echo "❌ Checkpoint not found in metadata: $CHECKPOINT_NAME"
    exit 1
fi

SESSION_ID=$(echo "$METADATA" | jq -r '.sessionId')
SESSION_FILE=$(echo "$METADATA" | jq -r '.sessionFile')
MESSAGE_UUID=$(echo "$METADATA" | jq -r '.messageUuid')
USER_PROMPT=$(echo "$METADATA" | jq -r '.userPrompt')
AGENT=$(echo "$METADATA" | jq -r '.agent')

echo "   Session: $SESSION_ID"
echo "   Message: $MESSAGE_UUID"
echo "   Prompt: ${USER_PROMPT:0:60}..."
echo ""

# 2. Restore code via ClaudePoint
echo "💾 Restoring code from checkpoint..."
cd "$PROJECT_ROOT"

if ! claudepoint undo "$CHECKPOINT_NAME"; then
    echo "❌ Code restore failed"
    exit 1
fi

echo "✅ Code restored"
echo ""

# 3. Truncate conversation
echo "✂️  Truncating conversation..."

TRUNCATOR="$(dirname "$0")/../lib/rewind/ConversationTruncator.js"

if [[ ! -f "$TRUNCATOR" ]]; then
    TRUNCATOR="$HOME/.local/lib/checkpoint-rewind/rewind/ConversationTruncator.js"
fi

if [[ ! -f "$TRUNCATOR" ]]; then
    echo "❌ ConversationTruncator not found"
    exit 1
fi

if ! node "$TRUNCATOR" "$SESSION_FILE" "$MESSAGE_UUID" --verbose; then
    echo "❌ Conversation truncation failed"
    echo "   Code has been restored, but conversation is unchanged."
    echo "   You can manually restore conversation or continue with current context."
    exit 1
fi

echo "✅ Conversation truncated"
echo ""

# 4. Display resume instructions
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎉 Rewind Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Both code and conversation have been restored."
echo ""
echo "Next steps:"
echo "  1. Exit your current agent session (Ctrl+C or quit)"
echo "  2. Resume with truncated conversation:"
echo ""

case "$AGENT" in
    claude-code)
        echo "     claude --resume $SESSION_ID"
        ;;
    droid-cli)
        echo "     droid --resume $SESSION_ID"
        ;;
    *)
        echo "     <agent> --resume $SESSION_ID"
        ;;
esac

echo ""
echo "Your agent will restart with the conversation context"
echo "as it was at checkpoint: $CHECKPOINT_NAME"
echo ""
```

**Testing:**
```bash
# Test 1: List available checkpoints
claudepoint list

# Test 2: Dry-run full rewind
./bin/checkpoint-rewind-full.sh auto_before_write_2025-11-16T12-00-00

# Test 3: Real rewind on test project
# (After end-to-end test creates checkpoints)
cd ~/test-checkpoint-project
../bin/checkpoint-rewind-full.sh <checkpoint-name>

# Verify:
# - Code files match checkpoint state
# - JSONL file has fewer lines
# - Backup created (.jsonl.backup.*)
```

---

## Success Criteria

**Phase 1 Complete:**
- ✅ Hooks fire during real Claude Code session
- ✅ Checkpoints created automatically
- ✅ Metadata links checkpoints to conversation turns
- ✅ Anti-spam works in practice

**Phase 2 Complete:**
- ✅ ConversationTruncator truncates JSONL safely
- ✅ checkpoint-rewind-full.sh restores code + conversation
- ✅ Resume with truncated conversation works
- ✅ Tested end-to-end with real coding workflow

**Overall Parity: 90-95%**
- ✅ Code checkpointing: FULL parity (better filtering)
- ✅ Conversation rewind: FULL parity (10-20s restart acceptable)
- ⚠️ UI: CLI-based (acceptable limitation)

---

## Testing Plan (Real Tests!)

### Test 1: End-to-End Phase 1 (30 min)
```bash
# Create test project
mkdir -p ~/test-checkpoint-project
cd ~/test-checkpoint-project
echo "console.log('v1');" > app.js

# Start Claude Code
claude

# In Claude:
> "Edit app.js and change v1 to v2"
# Wait for completion
# Wait 35 seconds (anti-spam cooldown)
> "Edit app.js and change v2 to v3"
# Wait for completion
> quit

# Verify Phase 1
claudepoint list
# Expected: 2 checkpoints (auto_before_edit_...)

cat .claudepoint/conversation_metadata.json | jq
# Expected: 2 entries with sessionId, messageUuid, userPrompt

# Test anti-spam worked
# (Should be 2 checkpoints, not 3, because 2nd and 3rd edits were <30s apart)
```

### Test 2: Conversation Truncator (15 min)
```bash
# Get real session file
SESSION_FILE=$(cat .claudepoint/conversation_metadata.json | jq -r '.[0].sessionFile')

# Get real message UUID from metadata
MESSAGE_UUID=$(cat .claudepoint/conversation_metadata.json | jq -r '.[0].messageUuid')

# Test truncation
node ~/.local/lib/checkpoint-rewind/rewind/ConversationTruncator.js \
  "$SESSION_FILE" \
  "$MESSAGE_UUID" \
  --dry-run --verbose

# Verify: Shows lines that would be kept/removed
```

### Test 3: Full Rewind (20 min)
```bash
# Get checkpoint name
CHECKPOINT=$(claudepoint list | grep auto_before | head -1 | awk '{print $1}')

# Full rewind
~/rewind/bin/checkpoint-rewind-full.sh "$CHECKPOINT"

# Verify code restored
cat app.js  # Should show v1 or v2 (earlier version)

# Verify conversation truncated
wc -l "$SESSION_FILE"*
# backup should have more lines

# Resume Claude
SESSION_ID=$(cat .claudepoint/conversation_metadata.json | jq -r '.[0].sessionId')
claude --resume "$SESSION_ID"

# Verify: Claude doesn't remember later messages
> "What was the last thing I asked you to do?"
# Should reference truncated conversation, not later turns
```

---

## Time Estimates

| Task | Time | Critical? |
|------|------|-----------|
| End-to-end test Phase 1 | 30 min | ✅ YES |
| Implement ConversationTruncator | 45 min | ✅ YES |
| Test ConversationTruncator | 15 min | ✅ YES |
| Implement checkpoint-rewind-full.sh | 30 min | ✅ YES |
| Test full rewind end-to-end | 20 min | ✅ YES |
| Install to system | 10 min | ✅ YES |
| **TOTAL** | **2.5 hours** | **To 90% parity** |

---

## What We'll Have After This

**Full Parity Checklist:**
- ✅ Automatic code checkpointing
- ✅ Automatic conversation metadata
- ✅ Code-only restore (ClaudePoint)
- ✅ Conversation-only restore (truncate JSONL)
- ✅ Full restore (both code + conversation)
- ✅ Agent-agnostic (Claude Code + Droid CLI)
- ✅ Safe (automatic backups)
- ⚠️ CLI-based (not visual UI - acceptable)
- ⚠️ Requires restart (10-20s - acceptable)

**What Anthropic's `/rewind` can do that we can't:**
- ESC ESC visual menu (no API for UI injection)
- Instant conversation reload (no restart needed)

**What we can do that Anthropic's `/rewind` can't:**
- ✅ 3-tier filtering (minimal/balanced/aggressive)
- ✅ Anti-spam (prevent checkpoint fatigue)
- ✅ Bash command tracking
- ✅ Works with multiple agents (not just Claude Code)
- ✅ Open source (inspect, modify, extend)
- ✅ CLI power-user features (scripting, automation)

**Result: 90-95% parity with unique advantages!** 🎉