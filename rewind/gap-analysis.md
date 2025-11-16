# Gap Analysis: Our Hooks vs Anthropic's Rewind

## Current State Comparison

### What Anthropic's Rewind Does

From the official documentation:

1. **Automatic Checkpointing** - Creates checkpoint with EVERY user prompt
2. **Three Restoration Modes:**
   - **Conversation Only** - Revert conversation, keep code changes
   - **Code Only** - Revert code, keep conversation history
   - **Both** - Revert both code and conversation
3. **Access Methods:**
   - Press ESC twice (ESC + ESC)
   - Type `/rewind` command
   - Visual menu shows conversation turns with git-style file notation
4. **Persistence** - Checkpoints persist for 30 days
5. **Limitations:**
   - Only tracks Claude's file edits (not bash commands)
   - Only current session (not manual changes outside session)

### What Our Hook System Does

1. **Smart Checkpointing** - Before Edit/Write/NotebookEdit with anti-spam
2. **One Restoration Mode:**
   - **Code Only** - Can only revert file changes
   - ❌ Cannot restore conversation context
   - ❌ No "conversation only" mode
3. **Access Methods:**
   - CLI: `claudepoint undo`, `ccundo undo`
   - Manual: Must run commands outside Claude Code
   - No visual menu in Claude Code interface
4. **Persistence** - ClaudePoint has 30-day retention ✓
5. **Advantages:**
   - Granular control (significance detection, anti-spam)
   - Works with bash commands (if using ccundo)
   - Batch operation detection

---

## The Gaps (Ranked by Importance)

### 🔴 CRITICAL GAP #1: Conversation Context Restoration

**What's Missing:** Cannot restore conversation/context to earlier point

**Why It Matters:**
- Anthropic's killer feature: "Context Recovery - Remove problematic instructions from Claude's memory"
- Example: You ask Claude to "use approach X", it fails, you want to undo that instruction
- Our system: Can undo the code changes, but Claude still remembers the bad instruction

**Impact:** 40% of Rewind's value

**Technical Challenge:**
- Claude's conversation is stored in JSONL files at `~/.claude/projects/<project-id>/<session-id>.jsonl`
- Each line is a JSON object representing a message or tool call
- To restore conversation:
  1. Read the JSONL file (hooks provide `transcript_path`)
  2. Find the checkpoint turn
  3. Truncate the file to that point
  4. Signal Claude Code to reload the conversation

**Blocker:** No documented way to make Claude Code reload conversation from modified JSONL

---

### 🟡 IMPORTANT GAP #2: UI/UX Integration

**What's Missing:** No in-Claude-Code interface

**Why It Matters:**
- Anthropic: Press ESC ESC, see visual menu, click to restore
- Our system: Exit Claude Code, run `claudepoint list`, copy ID, run `claudepoint undo`
- Friction reduces usage

**Impact:** 20% of Rewind's value (usability)

**Technical Challenge:**
- Claude Code doesn't expose APIs for custom UI
- Can't add buttons/menus to the interface
- Can't hijack ESC key handling

**Possible Solutions:**
- ✅ Use slash commands (`/checkpoint`, `/undo`) - Already possible
- ✅ Natural language ("create a checkpoint", "undo that") - Already works with MCP
- ⚠️ TUI wrapper around Claude Code - Complex, fragile
- ❌ Visual menu in Claude Code - Not possible without source code access

---

### 🟡 IMPORTANT GAP #3: Checkpoint Timing

**What's Missing:** Checkpoints happen before tool use, not before user prompt

**Why It Matters:**
- Anthropic: Checkpoints BEFORE Claude thinks/responds (at user prompt)
- Our system: Checkpoints just before file modification
- Gap: Claude's reasoning/planning not captured

**Impact:** 15% of Rewind's value

**Example of the problem:**
```
User: "Refactor everything to use TypeScript"
Claude: [Thinks through plan, creates multiple edit operations]
  → Our system: Checkpoint before FIRST edit only
  → Anthropic: Checkpoint BEFORE Claude started thinking
```

**Solution:** ✅ **Easily Fixed - Use UserPromptSubmit hook**

---

### 🟢 MINOR GAP #4: Conversation-Aware Checkpoints

**What's Missing:** Checkpoints not tied to conversation turns

**Why It Matters:**
- Anthropic: Shows "Before [user message]" with context
- Our system: Shows "Auto: Before Edit on app.js" (tool-centric)
- Harder to understand what checkpoint represents

**Impact:** 10% of Rewind's value

**Solution:** ✅ **Can improve - Include prompt context in checkpoint description**

---

### 🟢 MINOR GAP #5: Bash Command Tracking

**What's Missing:** Our hooks don't track bash-initiated file changes

**Why It Matters:**
- If Claude runs `rm -rf dist/` via bash, our PreToolUse hooks don't fire
- ccundo tracks this, but ClaudePoint hooks don't

**Impact:** 10% of Rewind's value

**Solution:** ✅ **Can add - PostToolUse hook on Bash tool**

---

### 🟢 MINOR GAP #6: Visual Timeline

**What's Missing:** No visual representation of session history

**Why It Matters:**
- Anthropic: Shows conversation turns with file changes
- Our system: Text list of checkpoints

**Impact:** 5% of Rewind's value

**Solution:** ⚠️ **Possible - Build TUI or web dashboard**

---

## Achievable Improvements

### ✅ HIGH PRIORITY: Fix Checkpoint Timing

**Implementation:**
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
            "args": ["-c", "claudepoint create -d \"Before: $PROMPT\""],
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

**Benefits:**
- Captures state BEFORE Claude thinks
- Checkpoint tied to user message (like Anthropic)
- Can restore to "before I asked that question"

**Drawback:**
- More checkpoints (one per prompt)
- Need aggressive anti-spam (maybe 60s interval)

---

### ✅ HIGH PRIORITY: Improve Checkpoint Descriptions

**Current:**
```
Auto: Before Edit on app.js
Auto: Before Write on test.js
```

**Improved:**
```
Before: "Refactor app.js to use async/await"
  • app.js modified
  • test.js created
  • 3 files affected
```

**Implementation:**
Store user prompt with checkpoint metadata, show in `claudepoint list`

---

### ✅ MEDIUM PRIORITY: Add Bash Command Tracking

**Implementation:**
```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bash",
            "args": ["-c", "~/.local/bin/track-bash-changes.sh"],
            "timeout": 3
          }
        ]
      }
    ]
  }
}
```

**Script Logic:**
- Compare file tree before/after bash command
- If files changed, create checkpoint retroactively
- Or warn user to create manual checkpoint

---

### ✅ MEDIUM PRIORITY: Slash Command Integration

**Implementation:**
Add to `.claude/commands/`:

```markdown
# /checkpoint
Create a manual checkpoint before proceeding.

claudepoint create -d "Manual checkpoint: {{ARGS}}"
```

```markdown
# /undo
Restore to the previous checkpoint.

claudepoint undo
```

**Usage:**
```
User: /checkpoint before-refactor
User: "Refactor everything"
[Changes made]
User: /undo
[Code restored]
```

---

### ⚠️ LOW PRIORITY: Conversation Restoration (Experimental)

**Implementation:**

```bash
#!/bin/bash
# restore-conversation.sh

TRANSCRIPT_PATH="$1"
CHECKPOINT_TURN="$2"

# Read JSONL line by line
# Truncate at checkpoint turn
# Write back to file

# Signal Claude Code to reload (HOW???)
# Options:
#   - Send SIGHUP to Claude Code process?
#   - Modify session file to trigger reload?
#   - Use undocumented API?
```

**Risk:**
- Could corrupt conversation history
- No documented way to trigger reload
- Might require Claude Code restart

**Recommendation:**
- Experiment in isolated environment
- Document findings
- Open issue with Anthropic for official hook support

---

## Hybrid Approach: Enhance Native Rewind

**Insight:** Instead of REPLACING Anthropic's Rewind, ENHANCE it

### Strategy

1. **Use our hooks for automatic checkpointing**
   - Smart filtering
   - Anti-spam
   - Significance detection

2. **Use Anthropic's native /rewind for restoration**
   - Has conversation restoration
   - Has visual UI
   - Fully supported

3. **Bridge the gap**
   - Our hooks create file-level checkpoints (ClaudePoint)
   - Native rewind creates conversation-level checkpoints
   - User can use either depending on need

### Implementation

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
            "args": ["-c", "
              # Create our smart checkpoint
              ~/.local/bin/smart-checkpoint.sh user-prompt \"$SESSION_ID\"

              # Native rewind handles conversation automatically
              # No conflict - complementary systems
            "],
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

**Result:**
- **Native /rewind** for conversation + code restoration
- **claudepoint undo** for granular code-only restoration
- **ccundo** for surgical operation-level undo
- Best of all worlds

---

## Recommended Action Plan

### Phase 1: Quick Wins (1 hour)

1. ✅ **Switch to UserPromptSubmit hook** - Checkpoint before Claude thinks
2. ✅ **Add prompt context to checkpoints** - Better descriptions
3. ✅ **Create slash commands** - `/checkpoint` and `/undo`
4. ✅ **Document hybrid usage** - When to use native vs hooks

### Phase 2: Enhanced Features (4 hours)

1. ✅ **Add Bash tracking hook** - Detect bash-initiated changes
2. ✅ **Improve anti-spam logic** - Context-aware cooldowns
3. ✅ **Build simple TUI** - Better checkpoint browsing
4. ✅ **Add checkpoint tagging** - Named checkpoints

### Phase 3: Experimental (8+ hours)

1. ⚠️ **Conversation restoration POC** - Modify JSONL files
2. ⚠️ **Claude Code reload mechanism** - Find way to trigger reload
3. ⚠️ **Visual dashboard** - Web UI for checkpoint management
4. ⚠️ **MCP server enhancement** - Full-featured rewind MCP server

---

## The Hard Truth

### What We CAN'T Do (Without Anthropic's Help)

1. **Cannot restore conversation context** - No API to reload conversation
2. **Cannot add UI to Claude Code** - No plugin system for UI
3. **Cannot hijack ESC key** - No keyboard hook API
4. **Cannot access Claude's internal state** - No API for context window

### What We CAN Do (With Current Hooks)

1. **Can checkpoint code state** ✅
2. **Can checkpoint before Claude acts** ✅ (UserPromptSubmit)
3. **Can make checkpoints smart** ✅ (significance detection)
4. **Can track all file operations** ✅ (including bash with PostToolUse)
5. **Can provide good UX** ⚠️ (slash commands, TUI, but not in-app UI)

### The 80/20 Solution

**Get 80% of Anthropic's Rewind value with 20% of the effort:**

1. Use UserPromptSubmit hook for timing
2. Add prompt context to checkpoints
3. Create slash commands for easy access
4. Use native `/rewind` when you need conversation restoration
5. Use our hooks when you need granular code restoration

**Total effort:** 2-3 hours
**Value gained:** 80% of full Rewind functionality

---

## Proposed Final Implementation

### Updated Hook Configuration

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
              "~/.local/bin/smart-checkpoint.sh user-prompt-submit \"$SESSION_ID\""
            ],
            "timeout": 5
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Edit|Write|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "bash",
            "args": [
              "-c",
              "~/.local/bin/smart-checkpoint.sh pre-tool-use \"$TOOL_NAME\" \"$SESSION_ID\""
            ],
            "timeout": 3
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bash",
            "args": [
              "-c",
              "~/.local/bin/smart-checkpoint.sh post-bash \"$SESSION_ID\""
            ],
            "timeout": 3
          }
        ]
      }
    ]
  }
}
```

### Updated Smart Checkpoint Script

**New Action:** `user-prompt-submit`

```bash
handle_user_prompt_submit() {
    local session_id="$1"

    # Read prompt from stdin
    local input=$(cat)
    local prompt=$(echo "$input" | jq -r '.prompt // ""' 2>/dev/null || echo "")

    # Check anti-spam (longer interval for prompt-level checkpoints)
    if ! should_checkpoint_by_time "$session_id" 60; then
        exit 0
    fi

    # Create checkpoint with prompt context
    local truncated_prompt="${prompt:0:80}"
    if create_checkpoint "Before: $truncated_prompt"; then
        update_last_checkpoint_time "$session_id"
    fi
}
```

### Slash Commands

Create `.claude/commands/checkpoint.md`:
```markdown
Create a checkpoint with optional description.

claudepoint create -d "${ARGS:-Manual checkpoint}"
```

Create `.claude/commands/undo.md`:
```markdown
Restore to previous checkpoint.

claudepoint undo
```

Create `.claude/commands/checkpoints.md`:
```markdown
List recent checkpoints.

claudepoint list
```

---

## Conclusion: The Parity Verdict

### Can We Achieve Full Parity? NO

**Missing:** Conversation restoration (40% of value)
**Blocker:** No API to reload Claude's conversation context

### Can We Get Close? YES

**Achievable:** 80% of Anthropic's Rewind value
**With:** UserPromptSubmit hooks + smart filtering + slash commands

### Should We Try? YES, BUT...

**Recommendation:**
1. Implement Phase 1 quick wins (80% value, 1 hour)
2. Use native `/rewind` for conversation restoration
3. Use our hooks for granular code control
4. Wait for Anthropic to expose conversation APIs before attempting Phase 3

---

## Next Steps

Which phase do you want to implement?

1. **Phase 1** - UserPromptSubmit hook + slash commands (1 hour)
2. **Phase 2** - Bash tracking + TUI (4 hours)
3. **Phase 3** - Experimental conversation restoration (risky)
4. **Hybrid** - Just document using native + hooks together (30 min)
