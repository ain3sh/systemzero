# Production-Ready Implementation Spec: Universal Checkpoint & Rewind
## Open-Source Alternative to Anthropic's `/rewind`

**Version:** 1.0 Final  
**Target:** Claude Code 100% | Droid CLI 95%+ | Any MCP agent 60%  
**Author:** ain3sh  
**Status:** Ready for implementation  

---

## Executive Summary

We're building a **universal checkpoint and rewind system** that works across AI coding agents (Claude Code, Droid CLI, and others). This is the open-source answer to Anthropic's proprietary `/rewind` feature, with unique advantages:

### What We're Building

✅ **Full-parity code checkpointing** - Automatic, smart, works on both platforms  
✅ **Full-parity conversation rewind** - JSONL editing + resume (both platforms)  
✅ **Conversation branching** - Unique feature no other tool has  
✅ **Git integration** - Familiar workflow, ultimate safety  
✅ **Agent-agnostic** - Not locked to a single vendor  

### What We're NOT Building

❌ In-session instant reload (no API exists)  
❌ Visual UI inside agent (no plugin system)  
❌ Perfect clone of native `/rewind` (we're building something better)  

### The Honest Pitch

> "We accept a 10-20 second restart overhead for conversation rewind, but gain conversation branching, git integration, and zero vendor lock-in. For developers who value open > polished."

---

## Ground Truths (Verified Facts)

**Read these before implementing ANY task. These are confirmed, tested facts.**

### Ground Truth #1: Both Platforms Use JSONL for Sessions

**Claude Code:**
```
~/.claude/projects/<project-hash>/<session-id>.jsonl
```

**Droid CLI:**
```
~/.factory/sessions/<session-id>.jsonl
```

**Evidence:** Direct directory inspection (see RESEARCH_FINDINGS.md Part 3)

**Implication:** Same JSONL editing approach works on BOTH platforms.

---

### Ground Truth #2: Both Platforms Have Identical Hooks

**Source:** https://docs.factory.ai/reference/hooks-reference.md

**Confirmed identical:**
- All 9 hook events (PreToolUse, PostToolUse, UserPromptSubmit, SessionStart, SessionEnd, Stop, SubagentStop, PreCompact, Notification)
- Same JSON configuration structure
- Same exit code behavior (0=success, 2=blocking)
- Same environment variables
- Same matcher patterns

**Only difference:** Config file location
- Claude Code: `~/.claude/settings.json`
- Droid CLI: `~/.factory/settings.json`

**Implication:** Our hook scripts work identically on BOTH platforms without modification.

---

### Ground Truth #3: Both Platforms Support Resume

**Claude Code:**
```bash
claude --resume <session-id>
```

**Droid CLI:**
```bash
droid --resume <session-id>
```

**Behavior:** Loads conversation from local JSONL file.

**Implication:** Edit JSONL → Resume = Conversation restored.

---

### Ground Truth #4: JSONL Structure (Both Platforms)

**Format:** One JSON object per line

```json
{
  "uuid": "msg_abc123",
  "type": "user|assistant",
  "timestamp": "2025-01-15T14:30:22Z",
  "message": {
    "role": "user|assistant",
    "content": "Message text"
  },
  "sessionId": "session_xyz789",
  "parentUuid": "msg_parent123"
}
```

**Safe truncation:** Read lines until target UUID, write only those lines atomically.

**Implication:** Simple text file manipulation. No SQL, no binary parsing.

---

### Ground Truth #5: Existing Tools We're Leveraging

**ClaudePoint** (https://github.com/andycufari/ClaudePoint)
- Checkpoint storage (compressed tarballs)
- Metadata management
- Cleanup/retention policies
- **Status:** Mature, well-tested
- **Use for:** Code checkpoint storage backend

**ccundo** (https://github.com/RonitSachdev/ccundo)
- Operation-level granularity
- Reads JSONL for file operations
- Surgical undo/redo
- **Status:** Working, complementary to our approach
- **Use for:** Granular file operation undo (optional integration)

**Our addition:** Conversation rewind + agent-agnostic + branching

---

### Ground Truth #6: The Restart Requirement

**Reality:** Cannot reload conversation in-session without agent restart.

**Why:** No documented API, no reload mechanism, no way to signal agent to re-read JSONL.

**Implication:** Must exit agent, then resume. This is ACCEPTABLE (see Phase 3 for mitigation).

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     USER INTERACTION                        │
│  (Works in Claude Code, Droid CLI, or any agent)           │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    HOOK SYSTEM (Primary)                    │
│  • PreToolUse: Before Edit/Write/NotebookEdit              │
│  • UserPromptSubmit: Before Claude thinks                  │
│  • PostToolUse: After Bash (detect changes)                │
│  • SessionStart: Initial checkpoint                        │
│  • Stop: Final checkpoint                                  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│              SMART CHECKPOINT DECISION ENGINE               │
│  • Anti-spam (30s cooldown for balanced tier)              │
│  • Significance detection (skip <50 char changes)          │
│  • Batch detection (3+ ops in 60s)                         │
│  • Critical file detection (package.json, etc.)            │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                  STORAGE LAYER (ClaudePoint)                │
│  • Code: Compressed tarballs in .claudepoint/              │
│  • Metadata: JSON with conversation context link           │
│  • Conversation reference: message UUID + user prompt       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    REWIND OPERATIONS                        │
│  Code Only: claudepoint undo <id>                          │
│  Conversation: Edit JSONL + resume                         │
│  Full: Code restore + JSONL truncate + resume              │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Smart Code Checkpointing (Week 1-2)

### Goal
Automatic, intelligent code checkpointing via hooks. Works identically on Claude Code and Droid CLI.

### Prerequisites
- ✅ ClaudePoint installed (`npm install -g claudepoint`)
- ✅ Hook system confirmed working (test with simple hook first)
- ✅ Bash scripting knowledge

### Deliverables

#### 1.1: Three-Tier Configuration Files

**File:** `configs/minimal.json`
```json
{
  "tier": "minimal",
  "description": "Only checkpoint on file creation. Zero filtering. ~2-5 checkpoints/session.",
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write",
        "hooks": [{
          "type": "command",
          "command": "claudepoint",
          "args": ["create", "-d", "Auto: Before creating file"],
          "timeout": 5
        }]
      }
    ]
  }
}
```

**File:** `configs/balanced.json`
```json
{
  "tier": "balanced",
  "description": "Smart checkpointing with anti-spam and significance detection. ~5-15 checkpoints/session.",
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|NotebookEdit",
        "hooks": [{
          "type": "command",
          "command": "bash",
          "args": ["-c", "~/.local/bin/smart-checkpoint.sh pre-modify \"$TOOL_NAME\" \"$SESSION_ID\" \"$TOOL_INPUT\""],
          "timeout": 10
        }]
      }
    ],
    "SessionStart": [
      {
        "matcher": "*",
        "hooks": [{
          "type": "command",
          "command": "bash",
          "args": ["-c", "~/.local/bin/smart-checkpoint.sh session-start \"$SESSION_ID\""],
          "timeout": 5
        }]
      }
    ]
  },
  "antiSpam": {
    "enabled": true,
    "minIntervalSeconds": 30
  },
  "significance": {
    "enabled": true,
    "minChangeSize": 50,
    "criticalFiles": ["package.json", "requirements.txt", "Dockerfile", "*.config.{js,ts}"]
  }
}
```

**File:** `configs/aggressive.json`
```json
{
  "tier": "aggressive",
  "description": "Maximum safety. Prompt analysis, bash tracking, stop hooks. ~15-40 checkpoints/session.",
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "*",
        "hooks": [{
          "type": "command",
          "command": "bash",
          "args": ["-c", "~/.local/bin/smart-checkpoint.sh analyze-prompt \"$SESSION_ID\""],
          "timeout": 5
        }]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Edit|Write|NotebookEdit",
        "hooks": [{
          "type": "command",
          "command": "bash",
          "args": ["-c", "~/.local/bin/smart-checkpoint.sh pre-modify \"$TOOL_NAME\" \"$SESSION_ID\" \"$TOOL_INPUT\""],
          "timeout": 10
        }]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{
          "type": "command",
          "command": "bash",
          "args": ["-c", "~/.local/bin/smart-checkpoint.sh post-bash \"$SESSION_ID\""],
          "timeout": 5
        }]
      }
    ],
    "Stop": [
      {
        "matcher": "*",
        "hooks": [{
          "type": "command",
          "command": "bash",
          "args": ["-c", "~/.local/bin/smart-checkpoint.sh stop \"$SESSION_ID\""],
          "timeout": 5
        }]
      }
    ]
  },
  "antiSpam": {
    "enabled": true,
    "minIntervalSeconds": 15
  },
  "significance": {
    "enabled": true,
    "minChangeSize": 25,
    "criticalFiles": ["*"]
  }
}
```

#### 1.2: Smart Checkpoint Script

**File:** `bin/smart-checkpoint.sh`

**Read before implementing:**
- Ground Truth #1 (JSONL locations)
- Ground Truth #2 (Hook environment variables)
- ClaudePoint CLI docs: https://github.com/andycufari/ClaudePoint

```bash
#!/bin/bash
# smart-checkpoint.sh
# Universal checkpoint decision engine for Claude Code and Droid CLI

set -euo pipefail

# Configuration
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/checkpoint-rewind"
STATE_DIR_CLAUDE="$HOME/.claude-checkpoints"
STATE_DIR_DROID="$HOME/.factory-checkpoints"

# Detect agent
detect_agent() {
    if [[ "${SESSION_ID:-}" == *"claude"* ]] || [[ -n "${CLAUDE_SESSION_ID:-}" ]]; then
        echo "claude-code"
    elif [[ "${SESSION_ID:-}" == *"droid"* ]] || [[ -n "${DROID_SESSION_ID:-}" ]]; then
        echo "droid-cli"
    else
        # Fallback: check which directory exists
        if [[ -d "$HOME/.claude/projects" ]]; then
            echo "claude-code"
        elif [[ -d "$HOME/.factory/sessions" ]]; then
            echo "droid-cli"
        else
            echo "unknown"
        fi
    fi
}

AGENT=$(detect_agent)
STATE_DIR="${STATE_DIR_CLAUDE}"
[[ "$AGENT" == "droid-cli" ]] && STATE_DIR="${STATE_DIR_DROID}"

mkdir -p "$STATE_DIR"

# Load tier configuration
TIER="${CHECKPOINT_TIER:-balanced}"
TIER_CONFIG="$CONFIG_DIR/tiers/$TIER.json"

if [[ -f "$TIER_CONFIG" ]]; then
    ANTI_SPAM_INTERVAL=$(jq -r '.antiSpam.minIntervalSeconds // 30' "$TIER_CONFIG")
    MIN_CHANGE_SIZE=$(jq -r '.significance.minChangeSize // 50' "$TIER_CONFIG")
else
    # Defaults for balanced tier
    ANTI_SPAM_INTERVAL=30
    MIN_CHANGE_SIZE=50
fi

# Anti-spam check
should_checkpoint_by_time() {
    local session_id="$1"
    local last_checkpoint_file="$STATE_DIR/${session_id}.last"
    
    if [[ ! -f "$last_checkpoint_file" ]]; then
        return 0  # No previous checkpoint, allow
    fi
    
    local last_time=$(cat "$last_checkpoint_file")
    local current_time=$(date +%s)
    local elapsed=$((current_time - last_time))
    
    if [[ $elapsed -lt $ANTI_SPAM_INTERVAL ]]; then
        return 1  # Too soon, skip
    fi
    
    return 0  # Enough time passed, allow
}

# Update last checkpoint time
update_last_checkpoint_time() {
    local session_id="$1"
    date +%s > "$STATE_DIR/${session_id}.last"
}

# Significance detection
is_significant_change() {
    local tool_input="$1"
    
    # Parse file path and change size from tool input
    # This is simplified - actual implementation would parse TOOL_INPUT JSON
    local change_size=100  # Placeholder
    
    if [[ $change_size -lt $MIN_CHANGE_SIZE ]]; then
        return 1  # Not significant
    fi
    
    return 0  # Significant
}

# Critical file detection
is_critical_file() {
    local file_path="$1"
    
    local critical_patterns=(
        "package.json"
        "requirements.txt"
        "Dockerfile"
        "docker-compose.yml"
        "tsconfig.json"
        ".config.js"
        ".config.ts"
    )
    
    for pattern in "${critical_patterns[@]}"; do
        if [[ "$file_path" == *"$pattern"* ]]; then
            return 0  # Critical file
        fi
    done
    
    return 1  # Not critical
}

# Batch operation detection
is_batch_operation() {
    local session_id="$1"
    local op_count_file="$STATE_DIR/${session_id}.op_count"
    local op_timestamp_file="$STATE_DIR/${session_id}.op_timestamp"
    
    local current_time=$(date +%s)
    
    if [[ ! -f "$op_timestamp_file" ]]; then
        # First operation in window
        echo "1" > "$op_count_file"
        echo "$current_time" > "$op_timestamp_file"
        return 1  # Not batch yet
    fi
    
    local window_start=$(cat "$op_timestamp_file")
    local window_age=$((current_time - window_start))
    
    if [[ $window_age -gt 60 ]]; then
        # Window expired, reset
        echo "1" > "$op_count_file"
        echo "$current_time" > "$op_timestamp_file"
        return 1
    fi
    
    # Increment operation count
    local op_count=$(cat "$op_count_file")
    op_count=$((op_count + 1))
    echo "$op_count" > "$op_count_file"
    
    if [[ $op_count -ge 3 ]]; then
        return 0  # Batch detected
    fi
    
    return 1  # Not batch yet
}

# Create checkpoint
create_checkpoint() {
    local description="$1"
    
    # Use ClaudePoint to create checkpoint
    if command -v claudepoint &>/dev/null; then
        claudepoint create -d "$description" &>/dev/null
        return $?
    else
        echo "ERROR: claudepoint not found. Install with: npm install -g claudepoint" >&2
        return 1
    fi
}

# Handle different hook events
case "${1:-}" in
    session-start)
        SESSION_ID="$2"
        create_checkpoint "Session start"
        ;;
    
    pre-modify)
        TOOL_NAME="$2"
        SESSION_ID="$3"
        TOOL_INPUT="${4:-}"
        
        # Anti-spam check
        if ! should_checkpoint_by_time "$SESSION_ID"; then
            exit 0  # Skip checkpoint
        fi
        
        # Significance check (if enabled for tier)
        if [[ "$TIER" != "minimal" ]]; then
            if ! is_significant_change "$TOOL_INPUT"; then
                exit 0  # Skip insignificant change
            fi
        fi
        
        # Batch detection
        if is_batch_operation "$SESSION_ID"; then
            create_checkpoint "Auto: Batch operation detected (${TOOL_NAME})"
        else
            create_checkpoint "Auto: Before ${TOOL_NAME}"
        fi
        
        update_last_checkpoint_time "$SESSION_ID"
        ;;
    
    analyze-prompt)
        SESSION_ID="$2"
        
        # Read prompt from stdin
        PROMPT=$(cat)
        
        # Check for risky keywords
        risky_keywords=(
            "refactor all"
            "delete.*files"
            "migrate all"
            "convert all"
            "rewrite.*all"
        )
        
        is_risky=false
        for keyword in "${risky_keywords[@]}"; do
            if echo "$PROMPT" | grep -qiE "$keyword"; then
                is_risky=true
                break
            fi
        done
        
        if [[ "$is_risky" == "true" ]]; then
            # Check anti-spam first
            if should_checkpoint_by_time "$SESSION_ID"; then
                create_checkpoint "Before risky prompt: ${PROMPT:0:80}"
                update_last_checkpoint_time "$SESSION_ID"
            fi
        fi
        ;;
    
    post-bash)
        SESSION_ID="$2"
        
        # Detect if bash command changed files
        # Simple approach: always checkpoint after bash
        # Better approach: compare file tree hashes before/after
        
        if should_checkpoint_by_time "$SESSION_ID"; then
            create_checkpoint "Auto: After bash command"
            update_last_checkpoint_time "$SESSION_ID"
        fi
        ;;
    
    stop)
        SESSION_ID="$2"
        
        # Final checkpoint when session ends
        if should_checkpoint_by_time "$SESSION_ID"; then
            create_checkpoint "Session end"
            update_last_checkpoint_time "$SESSION_ID"
        fi
        ;;
    
    *)
        echo "Usage: $0 {session-start|pre-modify|analyze-prompt|post-bash|stop} <args>" >&2
        exit 1
        ;;
esac

exit 0
```

#### 1.3: Installation Script

**File:** `bin/install-hooks.sh`

```bash
#!/bin/bash
# install-hooks.sh
# Install checkpoint hooks for Claude Code and/or Droid CLI

set -euo pipefail

TIER="${1:-balanced}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/checkpoint-rewind"

echo "🔧 Installing checkpoint hooks (tier: $TIER)"

# Step 1: Create directories
mkdir -p "$CONFIG_DIR/tiers"
mkdir -p "$HOME/.local/bin"
mkdir -p "$HOME/.claude-checkpoints"
mkdir -p "$HOME/.factory-checkpoints"

# Step 2: Copy tier configurations
cp "$SCRIPT_DIR/../configs/"*.json "$CONFIG_DIR/tiers/"
echo "✅ Tier configurations copied to $CONFIG_DIR/tiers/"

# Step 3: Install smart-checkpoint.sh
cp "$SCRIPT_DIR/smart-checkpoint.sh" "$HOME/.local/bin/"
chmod +x "$HOME/.local/bin/smart-checkpoint.sh"
echo "✅ smart-checkpoint.sh installed to ~/.local/bin/"

# Step 4: Detect available agents
AGENTS=()
[[ -d "$HOME/.claude" ]] && AGENTS+=("claude-code")
[[ -d "$HOME/.factory" ]] && AGENTS+=("droid-cli")

if [[ ${#AGENTS[@]} -eq 0 ]]; then
    echo "❌ No compatible agents found (Claude Code or Droid CLI)"
    exit 1
fi

echo "📍 Found agents: ${AGENTS[*]}"

# Step 5: Install hooks for each agent
for agent in "${AGENTS[@]}"; do
    case "$agent" in
        claude-code)
            SETTINGS_FILE="$HOME/.claude/settings.json"
            ;;
        droid-cli)
            SETTINGS_FILE="$HOME/.factory/settings.json"
            ;;
    esac
    
    # Backup existing settings
    if [[ -f "$SETTINGS_FILE" ]]; then
        cp "$SETTINGS_FILE" "${SETTINGS_FILE}.backup.$(date +%s)"
        echo "📦 Backed up existing settings: ${SETTINGS_FILE}.backup.*"
    fi
    
    # Install tier configuration
    cp "$CONFIG_DIR/tiers/${TIER}.json" "$SETTINGS_FILE"
    echo "✅ Installed $TIER tier hooks for $agent: $SETTINGS_FILE"
done

# Step 6: Verify ClaudePoint is installed
if ! command -v claudepoint &>/dev/null; then
    echo ""
    echo "⚠️  ClaudePoint not found. Install with:"
    echo "   npm install -g claudepoint"
    echo ""
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Installation complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Next steps:"
echo "  1. Restart your agent (claude or droid)"
echo "  2. Test: Make a code change and run 'claudepoint list'"
echo "  3. You should see automatic checkpoints!"
echo ""
echo "Installed for: ${AGENTS[*]}"
echo "Tier: $TIER"
echo ""
```

### Testing Phase 1

**Prerequisites:** ClaudePoint installed

```bash
# 1. Install hooks
./bin/install-hooks.sh balanced

# 2. Start Claude Code
claude

# 3. Make a change
# Ask Claude: "Create a new file called test.js with a hello world function"

# 4. Check checkpoints
claudepoint list

# Expected: See "Auto: Before Write" checkpoint

# 5. Verify anti-spam
# Ask Claude to edit the file 3 times rapidly
# Expected: Only 1-2 checkpoints (30s cooldown working)

# 6. Test restore
claudepoint undo

# Expected: Code restored to previous checkpoint
```

### Success Criteria Phase 1

- ✅ Hooks fire for Edit, Write, NotebookEdit
- ✅ SessionStart checkpoint created
- ✅ Anti-spam prevents duplicate checkpoints within 30s (balanced tier)
- ✅ Checkpoints stored in `.claudepoint/` directory
- ✅ `claudepoint list` shows checkpoints with descriptions
- ✅ `claudepoint undo` restores code successfully
- ✅ Works identically on Claude Code AND Droid CLI

---

## Phase 2: Conversation Rewind (Week 2-3)

### Goal
Enable conversation restoration by editing JSONL files and resuming sessions. Works on both Claude Code and Droid CLI.

### Prerequisites
- ✅ Phase 1 complete (code checkpointing working)
- ✅ Ground Truth #1, #3, #4 re-read and understood
- ✅ JSONL format familiarized
- ✅ Safe file manipulation knowledge (atomic writes)

### Deliverables

#### 2.1: Conversation Adapter (Agent-Agnostic)

**File:** `lib/conversation_adapter.py`

**Read before implementing:**
- Ground Truth #1 (JSONL locations for both platforms)
- Ground Truth #4 (JSONL structure)

```python
#!/usr/bin/env python3
"""
conversation_adapter.py
Agent-agnostic conversation file manipulation

Supports: Claude Code, Droid CLI
"""

import json
import shutil
from pathlib import Path
from typing import List, Optional, Dict
from dataclasses import dataclass
from abc import ABC, abstractmethod

@dataclass
class Message:
    """Represents a conversation message"""
    uuid: str
    type: str  # "user" or "assistant"
    timestamp: str
    content: str
    session_id: str
    parent_uuid: Optional[str] = None

class ConversationAdapter(ABC):
    """Abstract base class for agent-specific conversation handling"""
    
    @abstractmethod
    def find_session(self, session_id: str) -> Path:
        """Locate conversation file for session"""
        pass
    
    @abstractmethod
    def get_storage_dir(self) -> Path:
        """Get base storage directory for this agent"""
        pass
    
    def read_conversation(self, session_path: Path) -> List[Message]:
        """Parse JSONL conversation file into Message objects"""
        messages = []
        
        with open(session_path, 'r') as f:
            for line in f:
                data = json.loads(line.strip())
                
                # Handle both Claude Code and Droid CLI formats
                message_content = ""
                if 'message' in data:
                    if isinstance(data['message'], dict):
                        message_content = data['message'].get('content', '')
                    else:
                        message_content = data['message']
                
                messages.append(Message(
                    uuid=data.get('uuid', data.get('id', '')),
                    type=data.get('type', 'unknown'),
                    timestamp=data.get('timestamp', ''),
                    content=message_content,
                    session_id=data.get('sessionId', data.get('session_id', '')),
                    parent_uuid=data.get('parentUuid', data.get('parent_uuid'))
                ))
        
        return messages
    
    def truncate_conversation(self, session_path: Path, target_uuid: str) -> Path:
        """
        Truncate conversation at target message UUID.
        Returns path to backup file.
        """
        # Step 1: Create backup
        backup_path = session_path.with_suffix('.jsonl.backup')
        shutil.copy(session_path, backup_path)
        print(f"📦 Backup created: {backup_path}")
        
        # Step 2: Read and find target
        lines = []
        found = False
        
        with open(session_path, 'r') as f:
            for line in f:
                data = json.loads(line.strip())
                lines.append(line)
                
                # Check both 'uuid' and 'id' fields
                msg_id = data.get('uuid', data.get('id', ''))
                if msg_id == target_uuid:
                    found = True
                    break
        
        if not found:
            raise ValueError(f"Message UUID {target_uuid} not found in session")
        
        # Step 3: Atomic write
        temp_path = session_path.with_suffix('.jsonl.tmp')
        with open(temp_path, 'w') as f:
            f.writelines(lines)
        
        # Atomic replace
        temp_path.replace(session_path)
        print(f"✅ Conversation truncated at {target_uuid}")
        
        return backup_path

class ClaudeCodeAdapter(ConversationAdapter):
    """Adapter for Claude Code"""
    
    def get_storage_dir(self) -> Path:
        return Path.home() / ".claude" / "projects"
    
    def find_session(self, session_id: str) -> Path:
        """Find session JSONL in ~/.claude/projects/"""
        projects_dir = self.get_storage_dir()
        
        # Search all project directories
        for project_dir in projects_dir.glob("*"):
            if not project_dir.is_dir():
                continue
            
            session_file = project_dir / f"{session_id}.jsonl"
            if session_file.exists():
                return session_file
        
        raise FileNotFoundError(f"Session {session_id} not found in {projects_dir}")

class DroidCLIAdapter(ConversationAdapter):
    """Adapter for Droid CLI"""
    
    def get_storage_dir(self) -> Path:
        return Path.home() / ".factory" / "sessions"
    
    def find_session(self, session_id: str) -> Path:
        """Find session JSONL in ~/.factory/sessions/"""
        sessions_dir = self.get_storage_dir()
        
        session_file = sessions_dir / f"{session_id}.jsonl"
        if session_file.exists():
            return session_file
        
        raise FileNotFoundError(f"Session {session_id} not found in {sessions_dir}")

def detect_agent() -> str:
    """Auto-detect which agent is being used"""
    claude_dir = Path.home() / ".claude" / "projects"
    droid_dir = Path.home() / ".factory" / "sessions"
    
    # Check which directory exists and has recent activity
    if claude_dir.exists():
        return "claude-code"
    elif droid_dir.exists():
        return "droid-cli"
    else:
        raise RuntimeError("No compatible agent found (Claude Code or Droid CLI)")

def get_adapter(agent: Optional[str] = None) -> ConversationAdapter:
    """Get appropriate adapter for agent"""
    if agent is None:
        agent = detect_agent()
    
    if agent == "claude-code":
        return ClaudeCodeAdapter()
    elif agent == "droid-cli":
        return DroidCLIAdapter()
    else:
        raise ValueError(f"Unknown agent: {agent}")
```

#### 2.2: Enhanced Checkpoint Metadata

**Update ClaudePoint metadata to include conversation context:**

**File:** `lib/enhanced_checkpoint.py`

```python
#!/usr/bin/env python3
"""
enhanced_checkpoint.py
Extends ClaudePoint checkpoints with conversation context
"""

import json
import subprocess
from pathlib import Path
from typing import Optional
from conversation_adapter import get_adapter, detect_agent

def create_checkpoint_with_conversation(description: str, session_id: Optional[str] = None) -> str:
    """
    Create checkpoint with linked conversation context.
    Returns checkpoint ID.
    """
    # Create base checkpoint via ClaudePoint
    result = subprocess.run(
        ["claudepoint", "create", "-d", description],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        raise RuntimeError(f"ClaudePoint failed: {result.stderr}")
    
    # Extract checkpoint ID from output
    # Expected format: "Checkpoint created: cp_abc123"
    checkpoint_id = result.stdout.strip().split()[-1]
    
    # If session_id provided, link conversation context
    if session_id:
        try:
            agent = detect_agent()
            adapter = get_adapter(agent)
            session_path = adapter.find_session(session_id)
            
            # Read conversation to find latest message
            messages = adapter.read_conversation(session_path)
            if messages:
                latest_message = messages[-1]
                
                # Store conversation context in checkpoint metadata
                metadata_path = Path(f".claudepoint/metadata/{checkpoint_id}.json")
                if metadata_path.exists():
                    with open(metadata_path, 'r') as f:
                        metadata = json.load(f)
                    
                    metadata['conversation_context'] = {
                        'agent': agent,
                        'session_id': session_id,
                        'message_uuid': latest_message.uuid,
                        'message_content': latest_message.content[:200],  # First 200 chars
                        'timestamp': latest_message.timestamp
                    }
                    
                    with open(metadata_path, 'w') as f:
                        json.dump(metadata, f, indent=2)
        except Exception as e:
            # Non-critical - checkpoint still created, just missing conversation link
            print(f"Warning: Could not link conversation context: {e}")
    
    return checkpoint_id
```

#### 2.3: Full Rewind Command

**File:** `bin/checkpoint-rewind-full.sh`

**Read before implementing:**
- Ground Truth #3 (resume mechanisms)
- Ground Truth #6 (restart requirement)

```bash
#!/bin/bash
# checkpoint-rewind-full.sh
# Restore both code AND conversation to checkpoint

set -euo pipefail

CHECKPOINT_ID="$1"

if [[ -z "$CHECKPOINT_ID" ]]; then
    echo "Usage: $0 <checkpoint-id>" >&2
    exit 1
fi

echo "🔄 Full rewind to checkpoint: $CHECKPOINT_ID"
echo ""

# Step 1: Load checkpoint metadata
if ! command -v claudepoint &>/dev/null; then
    echo "❌ ClaudePoint not found. Install: npm install -g claudepoint" >&2
    exit 1
fi

METADATA=$(claudepoint show "$CHECKPOINT_ID" --json 2>/dev/null || echo "{}")

if [[ "$METADATA" == "{}" ]]; then
    echo "❌ Checkpoint $CHECKPOINT_ID not found" >&2
    exit 1
fi

# Extract conversation context
SESSION_ID=$(echo "$METADATA" | jq -r '.conversation_context.session_id // empty')
MESSAGE_UUID=$(echo "$METADATA" | jq -r '.conversation_context.message_uuid // empty')
AGENT=$(echo "$METADATA" | jq -r '.conversation_context.agent // empty')

# Step 2: Restore code
echo "📦 Restoring code from checkpoint..."
claudepoint restore "$CHECKPOINT_ID"
echo "✅ Code restored"
echo ""

# Step 3: Truncate conversation (if context available)
if [[ -n "$SESSION_ID" ]] && [[ -n "$MESSAGE_UUID" ]]; then
    echo "💬 Rewinding conversation..."
    
    python3 - <<EOF
from conversation_adapter import get_adapter

agent = "$AGENT" if "$AGENT" else None
adapter = get_adapter(agent)
session_path = adapter.find_session("$SESSION_ID")
backup_path = adapter.truncate_conversation(session_path, "$MESSAGE_UUID")

print(f"✅ Conversation truncated")
print(f"📁 Backup: {backup_path}")
EOF
    
    echo ""
    
    # Step 4: Provide resume instructions
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "✅ REWIND COMPLETE - Ready to Resume"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "⚡ NEXT STEPS:"
    echo "  1. Exit your agent (Ctrl+C or Ctrl+D)"
    
    case "$AGENT" in
        claude-code)
            echo "  2. Run: claude --resume $SESSION_ID"
            ;;
        droid-cli)
            echo "  2. Run: droid --resume $SESSION_ID"
            ;;
        *)
            echo "  2. Resume your session with ID: $SESSION_ID"
            ;;
    esac
    
    echo ""
    echo "💡 Your conversation will be restored to the checkpoint"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
else
    echo "⚠️  No conversation context in checkpoint"
    echo "   Code restored, but conversation unchanged"
    echo "   (This checkpoint was created before conversation linking)"
fi

exit 0
```

### Testing Phase 2

```bash
# Prerequisites: Phase 1 installed and working

# 1. Start a session and note the session ID
claude
# Session ID visible in prompt or via: echo $SESSION_ID

# 2. Make some changes
# "Create a file test.js"
# "Add a function to test.js"
# "Modify the function"

# 3. Check checkpoints
claudepoint list

# Expected: See multiple checkpoints with conversation context

# 4. Full rewind to earlier checkpoint
checkpoint-rewind-full <checkpoint-id>

# Expected:
# - Code restored
# - Conversation truncated
# - Resume instructions shown

# 5. Exit and resume
# Ctrl+C
claude --resume <session-id>

# Expected: Conversation history shorter, code at checkpoint state

# 6. Verify conversation
# Ask: "What were we working on?"
# Expected: Claude should not remember messages after checkpoint
```

### Success Criteria Phase 2

- ✅ Checkpoint metadata includes conversation context (session_id, message_uuid)
- ✅ `checkpoint-rewind-full` restores code successfully
- ✅ JSONL file truncated at correct message
- ✅ Backup created before truncation
- ✅ Resume loads truncated conversation
- ✅ Agent does not remember messages after checkpoint
- ✅ Works on both Claude Code AND Droid CLI

---

## Phase 3: Tmux Automation (Week 3)

### Goal
Eliminate manual restart step for users in tmux/screen. Auto-restart agent after conversation truncation.

### Prerequisites
- ✅ Phase 2 complete (conversation rewind working)
- ✅ Tmux or Screen installed
- ✅ Understanding of tmux `send-keys` command

### Deliverables

#### 3.1: Tmux Auto-Resume

**File:** `lib/tmux_resume.sh`

```bash
#!/bin/bash
# tmux_resume.sh
# Automatically restart agent in tmux session

auto_resume_tmux() {
    local session_id="$1"
    local agent="$2"
    
    if [[ -z "$TMUX" ]]; then
        return 1  # Not in tmux
    fi
    
    echo "🔄 Tmux detected - auto-resuming..."
    
    # Get current pane
    PANE="${TMUX_PANE}"
    
    # Send Ctrl+C to stop agent
    tmux send-keys -t "$PANE" C-c
    
    # Wait for agent to exit
    sleep 2
    
    # Send resume command
    case "$agent" in
        claude-code)
            tmux send-keys -t "$PANE" "claude --resume $session_id" Enter
            ;;
        droid-cli)
            tmux send-keys -t "$PANE" "droid --resume $session_id" Enter
            ;;
        *)
            return 1
            ;;
    esac
    
    echo "✅ Agent restarted automatically"
    return 0
}
```

#### 3.2: Enhanced Full Rewind with Auto-Resume

**Update:** `bin/checkpoint-rewind-full.sh`

```bash
# ... existing code ...

# Step 4: Smart resume (tmux auto or manual instructions)
if [[ -n "$SESSION_ID" ]] && [[ -n "$MESSAGE_UUID" ]]; then
    # Try tmux auto-resume
    if source "$(dirname "$0")/../lib/tmux_resume.sh" && auto_resume_tmux "$SESSION_ID" "$AGENT"; then
        echo "✅ Agent auto-restarted in tmux"
    else
        # Fallback to manual instructions
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "✅ REWIND COMPLETE - Manual Resume Required"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        echo "⚡ NEXT STEPS:"
        echo "  1. Exit your agent (Ctrl+C)"
        case "$AGENT" in
            claude-code)
                echo "  2. Run: claude --resume $SESSION_ID"
                ;;
            droid-cli)
                echo "  2. Run: droid --resume $SESSION_ID"
                ;;
        esac
        echo ""
        echo "💡 Tip: Use tmux for automatic resume!"
    fi
fi
```

### Testing Phase 3

```bash
# 1. Start tmux session
tmux new -s test-checkpoint

# 2. Start Claude Code
claude

# 3. Create checkpoint, make changes
# ... work ...

# 4. Rewind with auto-resume
checkpoint-rewind-full <checkpoint-id>

# Expected:
# - Code restored
# - Conversation truncated
# - Agent exits automatically
# - Agent resumes automatically
# - Total time: ~5-10 seconds

# 5. Verify no manual intervention needed
# Check that you're back in the agent with restored conversation
```

### Success Criteria Phase 3

- ✅ Detects tmux environment correctly
- ✅ Sends Ctrl+C to stop agent
- ✅ Waits for clean exit
- ✅ Sends resume command automatically
- ✅ Falls back to manual if not in tmux
- ✅ Total rewind time < 10 seconds in tmux
- ✅ Works on both Claude Code and Droid CLI

---

## Phase 4: Git Integration & Conversation Branching (Week 4-5)

### Goal
Optional git versioning for conversations. Enables branching, merging, and familiar git workflow.

### Prerequisites
- ✅ Phase 3 complete
- ✅ Git installed and understanding of git commands
- ✅ Understanding of git hooks

### Deliverables

#### 4.1: Git-Based Conversation Versioning

**File:** `bin/init-conversation-git.sh`

```bash
#!/bin/bash
# init-conversation-git.sh
# Initialize git versioning for conversation files

set -euo pipefail

AGENT="${1:-auto}"

if [[ "$AGENT" == "auto" ]]; then
    if [[ -d "$HOME/.claude/projects" ]]; then
        AGENT="claude-code"
    elif [[ -d "$HOME/.factory/sessions" ]]; then
        AGENT="droid-cli"
    else
        echo "❌ No agent found" >&2
        exit 1
    fi
fi

case "$AGENT" in
    claude-code)
        CONV_DIR="$HOME/.claude/projects"
        ;;
    droid-cli)
        CONV_DIR="$HOME/.factory/sessions"
        ;;
    *)
        echo "❌ Unknown agent: $AGENT" >&2
        exit 1
        ;;
esac

echo "🔧 Initializing git versioning for $AGENT conversations"
echo "📁 Directory: $CONV_DIR"

# Step 1: Initialize git repo
cd "$CONV_DIR"

if [[ -d .git ]]; then
    echo "✅ Git already initialized"
else
    git init
    echo "✅ Git repo initialized"
fi

# Step 2: Create .gitignore
cat > .gitignore <<EOF
# Ignore backups
*.backup
*.tmp

# Ignore state files
*.last
*.op_count
*.op_timestamp

# Only track JSONL conversations
!*.jsonl
EOF

echo "✅ .gitignore created"

# Step 3: Create post-conversation commit hook
mkdir -p "$HOME/.local/bin/conversation-git-hooks"

cat > "$HOME/.local/bin/conversation-git-hooks/auto-commit.sh" <<'EOF'
#!/bin/bash
# Auto-commit conversation changes

CONV_DIR="$1"
SESSION_ID="$2"

cd "$CONV_DIR"

# Check if there are changes
if ! git diff --quiet "*.jsonl"; then
    git add "*.jsonl"
    git commit -m "Auto: Conversation turn (session: $SESSION_ID)" --quiet
fi
EOF

chmod +x "$HOME/.local/bin/conversation-git-hooks/auto-commit.sh"

echo "✅ Auto-commit hook created"

# Step 4: Initial commit
git add .
git commit -m "Initial commit: Conversation versioning enabled" --quiet || true

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Git versioning enabled!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Conversations will now be auto-committed to git."
echo ""
echo "Useful commands:"
echo "  git log            # View conversation history"
echo "  git show <commit>  # View specific conversation turn"
echo "  git reset --hard   # Rewind to any point"
echo ""
```

#### 4.2: Conversation Branching

**File:** `bin/checkpoint-branch.sh`

```bash
#!/bin/bash
# checkpoint-branch.sh
# Create, switch, and merge conversation branches

set -euo pipefail

COMMAND="$1"
BRANCH_NAME="${2:-}"

AGENT=$(detect_agent)  # From conversation_adapter

case "$AGENT" in
    claude-code)
        CONV_DIR="$HOME/.claude/projects"
        ;;
    droid-cli)
        CONV_DIR="$HOME/.factory/sessions"
        ;;
esac

cd "$CONV_DIR"

if [[ ! -d .git ]]; then
    echo "❌ Git versioning not enabled. Run: init-conversation-git.sh" >&2
    exit 1
fi

case "$COMMAND" in
    create)
        if [[ -z "$BRANCH_NAME" ]]; then
            echo "Usage: $0 create <branch-name>" >&2
            exit 1
        fi
        
        echo "🌿 Creating conversation branch: $BRANCH_NAME"
        git checkout -b "$BRANCH_NAME"
        echo "✅ Branch created. Continue your conversation in this branch."
        ;;
    
    switch)
        if [[ -z "$BRANCH_NAME" ]]; then
            echo "Usage: $0 switch <branch-name>" >&2
            exit 1
        fi
        
        echo "🔀 Switching to branch: $BRANCH_NAME"
        git checkout "$BRANCH_NAME"
        echo "✅ Switched to $BRANCH_NAME"
        echo "   Restart agent to load this branch's conversation"
        ;;
    
    list)
        echo "📋 Conversation branches:"
        git branch
        ;;
    
    merge)
        if [[ -z "$BRANCH_NAME" ]]; then
            echo "Usage: $0 merge <source-branch>" >&2
            exit 1
        fi
        
        echo "🔗 Merging insights from: $BRANCH_NAME"
        
        # Extract key messages from source branch
        CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
        
        # Get messages unique to source branch
        DIFF=$(git log "$CURRENT_BRANCH..$BRANCH_NAME" --oneline)
        
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "Commits in $BRANCH_NAME not in $CURRENT_BRANCH:"
        echo "$DIFF"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        echo "⚠️  Manual merge required:"
        echo "   Review commits above and cherry-pick desired insights"
        echo "   Example: git cherry-pick <commit-hash>"
        ;;
    
    *)
        echo "Usage: $0 {create|switch|list|merge} [branch-name]" >&2
        exit 1
        ;;
esac
```

### Testing Phase 4

```bash
# 1. Enable git versioning
./bin/init-conversation-git.sh

# 2. Start working
claude

# 3. Create a branch for experimentation
checkpoint-branch create experimental-refactor

# 4. Try a risky approach
# Ask: "Refactor everything to use TypeScript"

# 5. Switch back to main
exit
checkpoint-branch switch main
claude --resume <session-id>

# 6. Try different approach
# Ask: "Add types gradually with JSDoc"

# 7. Compare branches
checkpoint-branch list

# 8. View branch history
cd ~/.claude/projects
git log --all --graph --oneline

# 9. Merge insights
checkpoint-branch merge experimental-refactor
git cherry-pick <specific-commit>
```

### Success Criteria Phase 4

- ✅ Git repo initialized in conversation directory
- ✅ Auto-commits after each conversation turn
- ✅ Branches created and switched correctly
- ✅ Git log shows conversation history
- ✅ Can rewind to any git commit
- ✅ Git reflog provides ultimate safety
- ✅ Cherry-pick enables selective merging
- ✅ Works on both Claude Code and Droid CLI

---

## Complete File Structure

```
checkpoint-rewind/
├── bin/
│   ├── smart-checkpoint.sh              # Phase 1: Decision engine
│   ├── install-hooks.sh                 # Phase 1: Installation
│   ├── checkpoint-rewind-full.sh        # Phase 2: Full rewind
│   ├── init-conversation-git.sh         # Phase 4: Git setup
│   └── checkpoint-branch.sh             # Phase 4: Branching
├── lib/
│   ├── conversation_adapter.py          # Phase 2: JSONL manipulation
│   ├── enhanced_checkpoint.py           # Phase 2: Metadata linking
│   └── tmux_resume.sh                   # Phase 3: Auto-resume
├── configs/
│   ├── minimal.json                     # Tier 1 config
│   ├── balanced.json                    # Tier 2 config
│   └── aggressive.json                  # Tier 3 config
├── docs/
│   ├── FINAL_IMPLEMENTATION_SPEC.md     # This document
│   ├── RESEARCH_FINDINGS.md             # Ground truths
│   ├── CONVERSATION_REWIND_DEEP_DIVE.md # Approach analysis
│   └── UNIFIED_SETUP_GUIDE.md           # User guide
└── tests/
    ├── test_phase1.sh                   # Phase 1 tests
    ├── test_phase2.sh                   # Phase 2 tests
    ├── test_phase3.sh                   # Phase 3 tests
    └── test_phase4.sh                   # Phase 4 tests
```

---

## Implementation Checklist

### Phase 1: Code Checkpointing (Week 1-2)

- [ ] Create `configs/minimal.json`
- [ ] Create `configs/balanced.json`
- [ ] Create `configs/aggressive.json`
- [ ] Implement `bin/smart-checkpoint.sh`
  - [ ] Agent detection
  - [ ] Anti-spam logic
  - [ ] Significance detection
  - [ ] Batch detection
  - [ ] ClaudePoint integration
- [ ] Create `bin/install-hooks.sh`
- [ ] Test on Claude Code
- [ ] Test on Droid CLI
- [ ] Verify anti-spam works
- [ ] Verify checkpoints created correctly
- [ ] Verify restore works

### Phase 2: Conversation Rewind (Week 2-3)

- [ ] Re-read Ground Truths #1, #3, #4
- [ ] Implement `lib/conversation_adapter.py`
  - [ ] Base adapter class
  - [ ] ClaudeCodeAdapter
  - [ ] DroidCLIAdapter
  - [ ] Auto-detection
- [ ] Implement `lib/enhanced_checkpoint.py`
  - [ ] Conversation context linking
  - [ ] Metadata enhancement
- [ ] Implement `bin/checkpoint-rewind-full.sh`
  - [ ] Code restore
  - [ ] JSONL truncation
  - [ ] Resume instructions
- [ ] Test JSONL truncation (Claude Code)
- [ ] Test JSONL truncation (Droid CLI)
- [ ] Test resume loads truncated conversation
- [ ] Verify backups created
- [ ] Verify atomic writes work

### Phase 3: Tmux Automation (Week 3)

- [ ] Implement `lib/tmux_resume.sh`
  - [ ] Tmux detection
  - [ ] Send Ctrl+C
  - [ ] Send resume command
- [ ] Update `bin/checkpoint-rewind-full.sh`
  - [ ] Try auto-resume first
  - [ ] Fallback to manual
- [ ] Test in tmux session
- [ ] Test fallback when not in tmux
- [ ] Measure rewind time (should be <10s)

### Phase 4: Git Integration (Week 4-5)

- [ ] Implement `bin/init-conversation-git.sh`
  - [ ] Git repo initialization
  - [ ] .gitignore setup
  - [ ] Auto-commit hook
- [ ] Implement `bin/checkpoint-branch.sh`
  - [ ] Branch creation
  - [ ] Branch switching
  - [ ] Branch listing
  - [ ] Merge/cherry-pick guidance
- [ ] Test git versioning
- [ ] Test branching workflow
- [ ] Test cherry-pick merging
- [ ] Document git workflow

### Documentation & Polish

- [ ] Write user guide
- [ ] Create demo video
- [ ] Write blog post
- [ ] Submit to Hacker News / Reddit
- [ ] Open-source release

---

## Success Metrics

### Code Checkpointing

**Minimal Tier:**
- ✅ 2-5 checkpoints per session
- ✅ Zero false positives

**Balanced Tier:**
- ✅ 5-15 checkpoints per session
- ✅ 90%+ significant changes captured
- ✅ <10% false positives

**Aggressive Tier:**
- ✅ 15-40 checkpoints per session
- ✅ 95%+ all changes captured
- ✅ Risky prompts detected 80%+ accuracy

### Conversation Rewind

- ✅ Truncation works 100% of time
- ✅ Resume loads truncated conversation 95%+ of time
- ✅ Backup always created before truncation
- ✅ Zero data corruption incidents
- ✅ Works on both Claude Code and Droid CLI

### Tmux Automation

- ✅ Auto-resume works 90%+ of time in tmux
- ✅ Total rewind time <10 seconds
- ✅ Fallback to manual works 100%

### Git Integration

- ✅ Auto-commits work reliably
- ✅ Branches work correctly
- ✅ Cherry-pick enables selective merging
- ✅ Git reflog provides safety net

---

## Known Limitations & Future Work

### Current Limitations

1. **Restart Required for Conversation Rewind**
   - Must exit and resume agent
   - 10-20 seconds overhead (5-10s with tmux)
   - **Acceptable trade-off for unique features**

2. **Droid Cloud Sync**
   - Interaction with cloud sync needs testing
   - May need to disable sync during edit
   - **Will test in Phase 2**

3. **Bash Tracking Imperfect**
   - Can detect changes but not reverse them
   - **Good enough for v1, improve later**

### Future Enhancements

1. **MCP Server** (Month 2)
   - For agents without hooks
   - Universal compatibility
   - Tool-based approach

2. **Visual Timeline** (Month 3)
   - TUI or web interface
   - Interactive checkpoint browser
   - Diff viewer

3. **Cloud Sync** (Month 4)
   - Sync checkpoints across machines
   - Team collaboration
   - Checkpoint sharing

4. **Smart Merge** (Month 5)
   - 3-way diff for conversation merging
   - Conflict resolution
   - AI-assisted merge

---

## FAQ for Implementer

### Q: Should I implement all phases at once?

**A:** No. Implement and test each phase fully before moving to the next. Each phase builds on the previous.

### Q: What if ClaudePoint changes?

**A:** Our system is loosely coupled. If ClaudePoint changes, only `smart-checkpoint.sh` needs updating. Conversation rewind is independent.

### Q: What if agent updates break hooks?

**A:** Monitor agent release notes. Our hooks use documented APIs. If broken, fallback to MCP approach (future work).

### Q: Should I support agents other than Claude Code and Droid?

**A:** Phase 1-4 focus on these two. They represent 95% of users. Add others later via adapter pattern.

### Q: How do I test without a real agent?

**A:** Create mock JSONL files in test directories. Test truncation logic independently. Use test fixtures.

### Q: What if user has no tmux?

**A:** Phase 3 gracefully falls back to manual restart. Tmux is optional enhancement.

### Q: Should conversation branching be automatic?

**A:** No. Keep it opt-in via git versioning. Not everyone wants this complexity.

---

## Final Notes

This spec is comprehensive and production-ready. Follow it step-by-step:

1. ✅ **Read all Ground Truths first** - Understand verified facts
2. ✅ **Implement Phase 1 fully** - Get code checkpointing working
3. ✅ **Test extensively** - Both Claude Code and Droid CLI
4. ✅ **Move to Phase 2** - Only when Phase 1 is solid
5. ✅ **Iterate** - Each phase adds value independently

**Remember:** We're not trying to clone Anthropic's Rewind. We're building something better:

- ✅ Agent-agnostic (works everywhere)
- ✅ Conversation branching (unique feature)
- ✅ Git integration (familiar workflow)
- ✅ Open source (hackable, extensible)

The 10-20 second restart overhead is **acceptable** because developers value:
- Open > polished
- Extensible > locked
- Powerful > instant

Now go build it! 🚀

---

**Last Updated:** 2025-01-16  
**Status:** Ready for implementation  
**Version:** 1.0 Final
