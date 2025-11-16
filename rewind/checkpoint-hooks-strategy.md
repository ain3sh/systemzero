# Optimal Claude Code Checkpointing Strategy Using Hooks

## Problem Analysis

**Goal:** Automatic, deterministic checkpointing without relying on the model to remember
**Challenge:** Balance safety with avoiding checkpoint spam for trivial/broken changes

## Hook-Based Solution

### Core Strategy: PreToolUse Hook

Use **PreToolUse** hooks to intercept file-modifying operations BEFORE they execute, allowing intelligent checkpoint decisions based on:
- Tool type and parameters
- Time since last checkpoint (anti-spam)
- Change significance (file size, content analysis)
- Operation scope (single file vs multi-file)

---

## Recommended Hook Configuration

### 1. Primary Checkpoint Hook (PreToolUse)

**Target:** File modification tools
**Matcher:** `"Edit|Write|NotebookEdit"`

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "bash",
            "args": [
              "-c",
              "~/.local/bin/smart-checkpoint.sh pre-modify \"$TOOL_NAME\" \"$SESSION_ID\""
            ],
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

### 2. Multi-File Detection Hook (UserPromptSubmit)

**Purpose:** Detect potentially risky prompts and create checkpoints preemptively
**Example triggers:** "refactor all files", "update entire codebase", "delete old code"

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "bash",
            "args": [
              "-c",
              "~/.local/bin/smart-checkpoint.sh analyze-prompt \"$SESSION_ID\""
            ],
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

### 3. Session Boundary Checkpoints (SessionStart)

**Purpose:** Create checkpoint when session starts/resumes to capture clean state

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "bash",
            "args": [
              "-c",
              "~/.local/bin/smart-checkpoint.sh session-start \"$SESSION_ID\" \"$SOURCE\""
            ],
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

---

## Smart Checkpoint Script Logic

### Anti-Spam Rules (Implemented in Bash Script)

```bash
#!/bin/bash
# ~/.local/bin/smart-checkpoint.sh

STATE_DIR="$HOME/.claude-checkpoints"
mkdir -p "$STATE_DIR"

ACTION="$1"
SESSION_ID="$2"

LAST_CHECKPOINT_FILE="$STATE_DIR/$SESSION_ID.last"
MIN_CHECKPOINT_INTERVAL=30  # seconds

should_checkpoint() {
    # Check time since last checkpoint
    if [ -f "$LAST_CHECKPOINT_FILE" ]; then
        LAST_TIME=$(cat "$LAST_CHECKPOINT_FILE")
        NOW=$(date +%s)
        ELAPSED=$((NOW - LAST_TIME))

        if [ $ELAPSED -lt $MIN_CHECKPOINT_INTERVAL ]; then
            echo "⏭️  Skipped: Too soon ($ELAPSED sec)" >&2
            return 1
        fi
    fi

    return 0
}

create_checkpoint() {
    local description="$1"

    if ! should_checkpoint; then
        exit 0  # Success, but no checkpoint created
    fi

    # Create checkpoint via ClaudePoint or MCP
    if command -v claudepoint >/dev/null 2>&1; then
        claudepoint create -d "$description" >/dev/null 2>&1
        echo "✅ Checkpoint: $description" >&2
    fi

    # Update last checkpoint time
    date +%s > "$LAST_CHECKPOINT_FILE"
}

case "$ACTION" in
    pre-modify)
        TOOL_NAME="$3"

        # Read stdin to get tool parameters
        read -r TOOL_INPUT

        # Heuristic: Check change size
        CHANGE_SIZE=$(echo "$TOOL_INPUT" | jq -r '.new_string // .content // ""' | wc -c)

        # Skip checkpoints for tiny changes (< 50 chars)
        if [ "$CHANGE_SIZE" -lt 50 ]; then
            echo "⏭️  Skipped: Trivial change ($CHANGE_SIZE chars)" >&2
            exit 0
        fi

        create_checkpoint "Before $TOOL_NAME"
        ;;

    analyze-prompt)
        # Read prompt from stdin
        read -r INPUT
        PROMPT=$(echo "$INPUT" | jq -r '.prompt // ""' | tr '[:upper:]' '[:lower:]')

        # Detect risky keywords
        if echo "$PROMPT" | grep -qE "(refactor all|entire codebase|delete.*files|migrate all|convert all|update everything)"; then
            create_checkpoint "Before bulk operation: ${PROMPT:0:50}..."
        fi
        ;;

    session-start)
        SOURCE="$3"
        if [ "$SOURCE" = "startup" ] || [ "$SOURCE" = "resume" ]; then
            create_checkpoint "Session $SOURCE"
        fi
        ;;
esac

exit 0
```

---

## Decision Matrix: When to Checkpoint

### ✅ CREATE Checkpoint

| Trigger | Tool | Condition | Rationale |
|---------|------|-----------|-----------|
| PreToolUse | Edit | `new_string.length > 50` | Non-trivial code change |
| PreToolUse | Write | Always | New file creation is significant |
| PreToolUse | NotebookEdit | `cell_type == "code"` | Code cell modifications matter |
| UserPromptSubmit | * | Keywords: "refactor all", "migrate", "delete" | Bulk operations |
| SessionStart | * | `source == "startup"` | Clean baseline |
| Stop | * | Multiple files modified in turn | After batch changes |

### ❌ SKIP Checkpoint

| Trigger | Tool | Condition | Rationale |
|---------|------|-----------|-----------|
| PreToolUse | Edit | `elapsed < 30s` | Anti-spam cooldown |
| PreToolUse | Edit | `new_string.length < 50` | Trivial typo fix |
| PreToolUse | Write | File in `.gitignore` patterns | Temp/generated files |
| PostToolUse | * | Tool failed (exit code != 0) | Don't checkpoint broken state |
| Any | * | File path matches `node_modules/`, `.git/`, etc. | Excluded directories |

---

## Advanced Features

### 1. Change Significance Detection

```bash
# In smart-checkpoint.sh
detect_significance() {
    local file_path="$1"
    local change_size="$2"

    # Critical files always checkpoint
    if echo "$file_path" | grep -qE "(package.json|requirements.txt|Dockerfile)"; then
        return 0  # Significant
    fi

    # Large changes (>500 chars) always checkpoint
    if [ "$change_size" -gt 500 ]; then
        return 0
    fi

    # Small changes to tests/docs can be skipped
    if echo "$file_path" | grep -qE "(test|spec|\.md$)" && [ "$change_size" -lt 100 ]; then
        return 1  # Not significant
    fi

    return 0  # Default: significant
}
```

### 2. Batch Operation Detection

Track file modification frequency to detect batch operations:

```bash
# State tracking
increment_operation_count() {
    local count_file="$STATE_DIR/$SESSION_ID.op_count"
    local count=0

    if [ -f "$count_file" ]; then
        count=$(cat "$count_file")
    fi

    count=$((count + 1))
    echo "$count" > "$count_file"

    # If 3+ operations in 60 seconds, create checkpoint before first
    if [ "$count" -eq 1 ]; then
        # Reset counter after 60s
        (sleep 60 && echo "0" > "$count_file") &
    elif [ "$count" -ge 3 ]; then
        return 0  # Batch detected
    fi

    return 1
}
```

### 3. Integration with ClaudePoint

```bash
# Prefer ClaudePoint if available, fallback to Rewind-MCP
create_checkpoint_smart() {
    local description="$1"

    if command -v claudepoint >/dev/null 2>&1; then
        # ClaudePoint with persistent storage
        claudepoint create -d "$description" 2>&1
    elif command -v claude >/dev/null 2>&1; then
        # Fallback: Use MCP if available
        echo "{\"tool\":\"checkpoint\",\"files\":[\".\"],\"description\":\"$description\"}"
    else
        echo "⚠️  No checkpoint tool available" >&2
        exit 0
    fi
}
```

---

## Hook Configuration Files

### Project-Level (`.claude/settings.json`)

For shared team settings - minimal, non-invasive:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write",
        "hooks": [
          {
            "type": "command",
            "command": "claudepoint",
            "args": ["create", "-d", "Auto: Before file creation"],
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

### User-Level (`~/.claude/settings.json`)

For personal aggressive checkpointing:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "bash",
            "args": ["-c", "~/.local/bin/smart-checkpoint.sh pre-modify \"$TOOL_NAME\" \"$SESSION_ID\""],
            "timeout": 10
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "bash",
            "args": ["-c", "~/.local/bin/smart-checkpoint.sh analyze-prompt \"$SESSION_ID\""],
            "timeout": 5
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "claudepoint",
            "args": ["create", "-d", "Session start"],
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

---

## Exit Code Strategy

### Success Cases (Exit 0)
- Checkpoint created successfully → stdout message shown in transcript
- Checkpoint skipped due to anti-spam → stderr message (user sees reason)
- No checkpoint needed (read-only operation) → silent success

### Blocking Errors (Exit 2)
- Checkpoint failed critically AND operation is destructive → stderr fed to Claude
- Example: "Failed to create checkpoint before deleting 50 files. Please create manual checkpoint."

### Non-Blocking Errors (Other codes)
- Checkpoint failed but operation is safe to proceed → stderr shown to user
- Example: "Checkpoint creation failed but continuing with Edit operation"

---

## Recommended Setup

### Minimal Setup (Safe Default)
```bash
# Install ClaudePoint
npm install -g claudepoint
cd your-project
claudepoint setup

# Add to ~/.claude/settings.json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write",
        "hooks": [{"type": "command", "command": "claudepoint", "args": ["create", "-d", "Auto: File creation"], "timeout": 5}]
      }
    ]
  }
}
```

### Aggressive Setup (Maximum Safety)
```bash
# Install ClaudePoint + smart checkpoint script
npm install -g claudepoint
curl -o ~/.local/bin/smart-checkpoint.sh https://[script-url]
chmod +x ~/.local/bin/smart-checkpoint.sh

# Use full hooks configuration from above
```

### Balanced Setup (Recommended)
```bash
# Install ClaudePoint
npm install -g claudepoint
claudepoint setup  # This installs hooks automatically

# ClaudePoint's built-in hooks already handle:
# - Anti-spam (30s cooldown)
# - PreToolUse for bulk operations
# - Smart detection of risky operations
```

---

## Testing Hook Behavior

```bash
# Test checkpoint creation
echo '{"tool_name":"Write","tool_input":{"file_path":"test.txt","content":"hello"}}' | \
  ~/.local/bin/smart-checkpoint.sh pre-modify Write test-session

# Test anti-spam
~/.local/bin/smart-checkpoint.sh pre-modify Edit test-session  # Should checkpoint
sleep 10
~/.local/bin/smart-checkpoint.sh pre-modify Edit test-session  # Should skip (< 30s)

# Test prompt analysis
echo '{"prompt":"refactor all the files in src/"}' | \
  ~/.local/bin/smart-checkpoint.sh analyze-prompt test-session
```

---

## Migration Path

1. **Phase 1:** Install ClaudePoint with default hooks (least invasive)
2. **Phase 2:** Add UserPromptSubmit hook for bulk operation detection
3. **Phase 3:** Implement smart-checkpoint.sh with significance detection
4. **Phase 4:** Fine-tune anti-spam intervals based on usage patterns

---

## Key Takeaways

✅ **Use PreToolUse hooks** - Intercept before damage is done
✅ **Implement anti-spam** - 30-second cooldown minimum
✅ **Detect significance** - Skip trivial changes, checkpoint critical ones
✅ **Exit 0 for flexibility** - Allow operations to proceed even if checkpoint fails
✅ **ClaudePoint integration** - Leverage existing tool with MCP + CLI + hooks
✅ **Progressive enhancement** - Start simple, add sophistication as needed

❌ **Don't** checkpoint every single operation (spam)
❌ **Don't** use exit 2 liberally (blocks operations)
❌ **Don't** checkpoint failed operations (broken state)
❌ **Don't** ignore batch operations (most dangerous scenario)
