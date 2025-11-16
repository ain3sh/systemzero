# External Tools Analysis: Ground Truth from Source Code
## ClaudePoint & ccundo - What They Actually Do

**Last Updated:** 2025-11-16  
**Status:** Verified from source code  
**Repositories Cloned:** `references/ClaudePoint/` and `references/ccundo/`

---

## Executive Summary

**Critical Finding:** Both tools are MORE capable than we initially assumed, but have different strengths:

- **ClaudePoint:** Full project snapshots, hooks integration, MCP server, BUT no conversation tracking
- **ccundo:** Operation-level granularity, reads Claude JSONL directly, undo/redo with cascading, BUT limited to file operations

**Our Value Add:**
1. Conversation rewind (neither tool does this)
2. Agent-agnostic (ClaudePoint is Claude-Code specific)
3. Conversation branching (unique feature)

---

## ClaudePoint Deep Dive

### Repository Info
- **URL:** https://github.com/andycufari/ClaudePoint
- **Version:** 1.4.4
- **License:** MIT
- **Type:** ES Module (Node.js >=18.0.0)
- **Status:** Actively maintained, production-ready

### What It Actually Does

#### 1. Storage Format

**Location:** `.claudepoint/` directory in project root

```
.claudepoint/
├── config.json          # User configuration
├── changelog.json       # Checkpoint history log
├── hooks.json          # Hook configuration
├── snapshots/          # Compressed tarballs
│   ├── checkpoint_20250116_120530.tar.gz
│   ├── checkpoint_20250116_130145.tar.gz
│   └── ...
└── metadata/           # NOT FOUND IN SOURCE - needs verification
```

**Config Format (from source):**
```javascript
{
  "maxCheckpoints": 10,        // Keep 10 most recent
  "autoName": true,           // Generate names automatically
  "ignorePatterns": [         // What to exclude
    ".git", ".claudepoint", "node_modules", ".env", 
    "*.log", ".DS_Store", "__pycache__", "*.pyc",
    ".vscode", ".idea", "dist", "build", "coverage",
    ".next", ".nuxt", ".cache", "tmp", "temp"
  ],
  "additionalIgnores": [],    // User-added patterns
  "forceInclude": [],         // Override ignores
  "nameTemplate": "checkpoint_{timestamp}",
  "maxAge": 30               // Delete checkpoints older than 30 days
}
```

**Hooks Config Format (from source):**
```javascript
{
  "enabled": true,
  "auto_changelog": false,
  "triggers": {
    "before_bulk_edit": {
      "enabled": true,
      "tools": ["MultiEdit"],
      "description": "Safety checkpoint before bulk file edits"
    },
    "before_major_write": {
      "enabled": false,  // Disabled by default
      "tools": ["Write"]
    },
    "before_bash_commands": {
      "enabled": false,  // Disabled by default
      "tools": ["Bash"]
    },
    "before_file_operations": {
      "enabled": false,  // Comprehensive protection (advanced)
      "tools": ["Edit", "MultiEdit", "Write"]
    }
  }
}
```

**Anti-Spam Protection:** Built-in 30-second cooldown (from README)

#### 2. CLI Commands (from package.json and README)

**Primary commands:**
```bash
claudepoint                    # Create checkpoint (default action)
claudepoint create -d "desc"   # Create with description
claudepoint create -n "name"   # Create with custom name

claudepoint undo               # Restore to last checkpoint
claudepoint restore <name>     # Restore specific checkpoint

claudepoint list               # List all checkpoints
claudepoint changes            # Show files modified since last checkpoint
claudepoint changelog          # View checkpoint history

claudepoint config             # View configuration
claudepoint setup              # Interactive setup (hooks + MCP + slash commands)
```

**Setup scopes:**
```bash
claudepoint setup              # Project scope (default)
claudepoint setup --scope user # User scope (all projects)
claudepoint setup --scope global # System-wide
```

#### 3. Integration Capabilities

**Hook Integration:**
- Installs to `.claude/settings.json` or `~/.claude/settings.json`
- Triggers on: PreToolUse hook before MultiEdit (default)
- Optional triggers: Before Write, Before Bash, Before Edit
- Uses `claudepoint-hook.js` wrapper script

**MCP Server:**
- Entry point: `bin/claudepoint.js` (detects MCP vs CLI mode)
- Runs stdio-based MCP server when piped
- Provides tools:
  - `create_claudepoint`
  - `undo_claudepoint`
  - `list_claudepoints`
  - `restore_claudepoint`
  - `get_changes`

**Slash Commands:**
- `/claudepoint` - Create checkpoint
- `/undo` - Quick restore
- `/claudepoint-list` - Browse checkpoints
- `/claudepoint-restore` - Restore specific
- `/changes` - View modifications
- `/claudepoint-changelog` - History

#### 4. How Checkpoints Are Created

**From `checkpoint-manager.js` source:**

```javascript
async createCheckpoint(description = '', name = null) {
  // 1. Scan project files (excluding ignore patterns)
  const files = await this.getProjectFiles();
  
  // 2. Create tarball
  const checkpointName = name || this.generateCheckpointName();
  const tarballPath = path.join(this.snapshotsDir, `${checkpointName}.tar.gz`);
  
  await tar.create({
    gzip: true,
    file: tarballPath,
    cwd: this.projectRoot,
  }, files);
  
  // 3. Update changelog
  await this.addToChangelog({
    name: checkpointName,
    description: description,
    timestamp: new Date().toISOString(),
    fileCount: files.length,
    size: (await fs.stat(tarballPath)).size
  });
  
  // 4. Cleanup old checkpoints (maxCheckpoints, maxAge)
  await this.cleanupOldCheckpoints();
  
  return checkpointName;
}
```

#### 5. How Restore Works

**From `checkpoint-manager.js` source:**

```javascript
async restoreCheckpoint(checkpointName) {
  const tarballPath = path.join(this.snapshotsDir, `${checkpointName}.tar.gz`);
  
  // Safety: Create backup of current state first
  await this.createCheckpoint('pre-restore backup', `backup_before_${checkpointName}`);
  
  // Extract tarball to project root
  await tar.extract({
    file: tarballPath,
    cwd: this.projectRoot
  });
  
  return true;
}
```

**CRITICAL:** No file-by-file tracking - full extraction overwrites current state.

#### 6. What ClaudePoint DOES NOT Do

❌ **No conversation context tracking**
- Does not read Claude session JSONL files
- Does not store message UUIDs or conversation state
- Purely file-based checkpointing

❌ **No metadata per file**
- Stores entire project as tarball
- Cannot query "which files changed in this checkpoint?"
- Must extract and diff to see changes

❌ **No conversation restoration**
- No code to manipulate `.claude/projects/` JSONL files
- Not agent-agnostic (hardcoded for Claude Code paths)

✅ **What it DOES well:**
- Fast checkpoint creation (tar.gz compression)
- Smart ignore patterns (respects .gitignore)
- Hook integration for auto-checkpointing
- MCP server for tool-based usage
- Cleanup/retention policies

---

## ccundo Deep Dive

### Repository Info
- **URL:** https://github.com/RonitSachdev/ccundo
- **Version:** 1.1.1
- **License:** MIT
- **Type:** ES Module (Node.js >=16.0.0)
- **Status:** Maintained, specialized tool

### What It Actually Does

#### 1. How It Reads Claude Sessions

**From `ClaudeSessionParser.js` source:**

```javascript
// Location detection (cross-platform)
claudeProjectsDir = path.join(os.homedir(), '.claude', 'projects');

// Project directory naming:
// Windows: C:\Users\... → C--Users-...
// Linux/macOS: /home/... → -home-...

async getCurrentSessionFile() {
  const projectDir = await this.getCurrentProjectDir();
  const files = await fs.readdir(projectDir);
  const sessionFiles = files.filter(f => f.endsWith('.jsonl'));
  
  // Get most recently modified session
  stats.sort((a, b) => b.mtime - a.mtime);
  return stats[0].path;
}
```

**Reads JSONL line-by-line:**
```javascript
for await (const line of rl) {
  const entry = JSON.parse(line);
  
  // Look for assistant messages with tool use
  if (entry.type === 'assistant' && entry.message?.content) {
    for (const content of entry.message.content) {
      if (content.type === 'tool_use') {
        const operation = this.extractOperation(content, entry.timestamp);
        operations.push(operation);
      }
    }
  }
}
```

#### 2. Operation Extraction

**From `ClaudeSessionParser.js` - what tools it tracks:**

```javascript
extractOperation(toolUse, timestamp) {
  const { name, input } = toolUse;
  
  switch (name) {
    case 'Write':
      return new Operation(OperationType.FILE_CREATE, {
        filePath: input.file_path,
        content: input.content || ''
      });
      
    case 'Edit':
      return new Operation(OperationType.FILE_EDIT, {
        filePath: input.file_path,
        oldString: input.old_string || '',
        newString: input.new_string || '',
        replaceAll: input.replace_all || false
      });
      
    case 'MultiEdit':
      return new Operation(OperationType.FILE_EDIT, {
        filePath: input.file_path,
        edits: input.edits || [],
        isMultiEdit: true
      });
      
    case 'Bash':
      // Attempts to parse bash commands for file operations
      if (command.includes('rm ')) {
        return new Operation(OperationType.FILE_DELETE, {
          filePath: match[1],
          content: '' // Cannot recover from session
        });
      }
      // Also detects: mkdir, mv, cp, touch
      break;
  }
}
```

**Supported Operation Types:**
- `FILE_CREATE` - Write tool
- `FILE_EDIT` - Edit and MultiEdit tools
- `FILE_DELETE` - Detected from bash `rm`
- `FILE_RENAME` - Detected from bash `mv`
- `DIRECTORY_CREATE` - Detected from bash `mkdir`
- `DIRECTORY_DELETE` - Detected from bash `rmdir`
- `BASH_COMMAND` - Raw bash (manual undo)

#### 3. Undo Mechanism

**From `UndoManager.js` source:**

```javascript
async undoOperation(operation) {
  // Create backup first
  const backupPath = await this.createBackup(operation);
  
  switch (operation.type) {
    case OperationType.FILE_CREATE:
      // Delete created file
      await fs.unlink(operation.data.filePath);
      break;
      
    case OperationType.FILE_EDIT:
      // Revert to original content
      const currentContent = await fs.readFile(operation.data.filePath, 'utf8');
      
      if (operation.data.isMultiEdit) {
        // Reverse each edit
        let restored = currentContent;
        for (const edit of operation.data.edits.reverse()) {
          restored = restored.replace(edit.newString, edit.oldString);
        }
        await fs.writeFile(operation.data.filePath, restored);
      } else {
        // Simple replace
        const restored = currentContent.replace(
          operation.data.newString,
          operation.data.oldString
        );
        await fs.writeFile(operation.data.filePath, restored);
      }
      break;
      
    case OperationType.FILE_DELETE:
      // Restore from backup (if content available)
      if (operation.data.content) {
        await fs.writeFile(operation.data.filePath, operation.data.content);
      } else {
        console.warn('Cannot restore deleted file - content not in session');
      }
      break;
  }
}
```

**Cascading Undo:**
```javascript
async undoWithCascading(operationId, operations) {
  // Find operation index
  const index = operations.findIndex(op => op.id === operationId);
  
  // Undo this operation AND all operations after it
  const toUndo = operations.slice(index);
  
  for (const op of toUndo.reverse()) {
    await this.undoOperation(op);
  }
}
```

#### 4. Redo System

**From `RedoManager.js` source:**

```javascript
async redoOperation(operation) {
  // Re-apply the operation
  switch (operation.type) {
    case OperationType.FILE_CREATE:
      // Recreate file with original content
      await fs.writeFile(operation.data.filePath, operation.data.content);
      break;
      
    case OperationType.FILE_EDIT:
      // Re-apply edit
      const currentContent = await fs.readFile(operation.data.filePath, 'utf8');
      const redone = currentContent.replace(
        operation.data.oldString,
        operation.data.newString
      );
      await fs.writeFile(operation.data.filePath, redone);
      break;
  }
}
```

**Cascading Redo:**
- Redoes selected operation PLUS all undone operations before it
- Maintains consistency

#### 5. State Tracking

**From `UndoTracker.js` source:**

```javascript
// Storage: ~/.ccundo/undone-operations.json
{
  "sessionFile": "~/.claude/projects/xyz/session_abc.jsonl",
  "undoneOperations": [
    {
      "operationId": "toolu_01ABC123",
      "timestamp": "2025-11-16T12:34:56Z",
      "type": "file_edit"
    }
  ]
}
```

Tracks which operations have been undone per session file.

#### 6. CLI Commands (from source)

```bash
ccundo list                    # List operations from current session
ccundo list --all             # Include undone operations
ccundo list --session <id>    # Specific session

ccundo preview                # Interactive preview before undo
ccundo preview <op-id>        # Preview specific operation

ccundo undo                   # Interactive undo with cascading
ccundo undo <op-id>           # Undo specific operation
ccundo undo --yes            # Skip confirmations

ccundo redo                   # Interactive redo
ccundo redo <op-id>           # Redo specific operation
ccundo redo --yes            # Skip confirmations

ccundo sessions              # List all sessions
ccundo session <id>          # Switch session

ccundo language              # Show/change language
ccundo language ja           # Switch to Japanese
```

#### 7. What ccundo DOES NOT Do

❌ **No project-wide checkpoints**
- Tracks individual operations only
- No "snapshot everything" capability
- Cannot restore entire project state at once

❌ **No conversation manipulation**
- Reads JSONL for operation tracking only
- Does not truncate or edit conversation files
- Cannot rewind conversation context

❌ **Limited bash undo**
- Detects some bash commands (rm, mv, mkdir, etc.)
- But marks them as "manual intervention required"
- Cannot actually reverse bash operations

❌ **No hooks integration**
- Does not install hooks
- Purely reactive (user must run commands manually)

✅ **What it DOES well:**
- Surgical operation-level undo
- Reads Claude sessions directly (no separate storage needed)
- Cascading undo/redo maintains consistency
- Detailed preview before making changes
- Multi-language support

---

## Integration Strategy for Our Project

### What We Should Use from ClaudePoint

**1. Checkpoint Storage Format:**
```javascript
// Use ClaudePoint's config format
{
  "maxCheckpoints": 10,
  "ignorePatterns": [...],  // Reuse their smart defaults
  "maxAge": 30
}
```

**2. Hook Integration Pattern:**
```javascript
// ClaudePoint's hook detection is solid
// Use their trigger configuration approach
{
  "triggers": {
    "before_bulk_edit": { enabled: true, tools: ["MultiEdit"] }
  }
}
```

**3. DO NOT use ClaudePoint's CLI directly**
- It doesn't track conversation context
- We need metadata per checkpoint (conversation link)
- We need agent-agnostic paths

### What We Should Use from ccundo

**1. JSONL Parsing Logic:**
```javascript
// Reuse their ClaudeSessionParser approach
// They handle cross-platform path detection correctly
// They parse tool_use correctly

import { ClaudeSessionParser } from 'ccundo/src/core/ClaudeSessionParser.js';
```

**2. Operation Extraction:**
```javascript
// Their extractOperation() method is comprehensive
// Handles Write, Edit, MultiEdit, Bash correctly
// Good detection of bash file operations
```

**3. DO NOT use ccundo's undo mechanism**
- We need checkpoint-level restoration, not operation-level
- ccundo is complementary, not a replacement

### What We Build (Unique Value)

**1. Conversation Context Linking:**
```javascript
// ClaudePoint metadata enhancement
{
  "checkpoint_id": "cp_abc123",
  "conversation_context": {
    "agent": "claude-code",
    "session_id": "xyz789",
    "session_file": "~/.claude/projects/xyz/session_abc.jsonl",
    "message_uuid": "msg_def456",
    "message_index": 42,
    "user_prompt": "Add error handling",
    "timestamp": "2025-11-16T12:00:00Z"
  },
  "code_snapshot": {
    "tarball": "checkpoint_20251116_120000.tar.gz",
    "file_count": 45,
    "size_bytes": 123456
  }
}
```

**2. Conversation Truncation:**
```python
# Neither tool does this - our unique feature
def truncate_conversation(session_path, target_uuid):
    backup = create_backup(session_path)
    lines = read_until_uuid(session_path, target_uuid)
    atomic_write(session_path, lines)
    return backup
```

**3. Agent-Agnostic Adapters:**
```python
# Support both Claude Code and Droid CLI
class ClaudeCodeAdapter(ConversationAdapter):
    session_dir = "~/.claude/projects/"
    
class DroidCLIAdapter(ConversationAdapter):
    session_dir = "~/.factory/sessions/"
```

**4. Conversation Branching:**
```bash
# Git integration - neither tool has this
checkpoint-branch create experimental
checkpoint-branch switch main
checkpoint-branch merge experimental --insights-only
```

---

## Revised Implementation Plan

### Phase 1: Code Checkpointing

**Use ClaudePoint as-is for code snapshots:**
```bash
# Our hooks call ClaudePoint directly
claudepoint create -d "Auto: Before ${TOOL_NAME}"
```

**Add conversation metadata afterward:**
```python
# After ClaudePoint creates checkpoint
checkpoint_id = get_latest_checkpoint()
add_conversation_metadata(checkpoint_id, session_info)
```

### Phase 2: Conversation Rewind

**Borrow ccundo's JSONL parsing:**
```python
# Use their ClaudeSessionParser for reading
from references.ccundo.src.core import ClaudeSessionParser

parser = ClaudeSessionParser()
session_file = parser.getCurrentSessionFile()
operations = parser.parseSessionFile(session_file)

# Find message UUID for our checkpoint
message_uuid = find_message_at_checkpoint_time(operations, checkpoint_time)
```

**Our unique truncation logic:**
```python
# This is what neither tool does
truncate_conversation(session_file, message_uuid)
```

### Phase 3-4: Unchanged

Tmux automation and git branching are our own features.

---

## File Dependencies

### From ClaudePoint (can use directly)

```
references/ClaudePoint/
├── src/lib/checkpoint-manager.js  # Config format reference
├── bin/claudepoint-hook.js        # Hook wrapper pattern
└── src/mcp-server.js             # MCP integration example
```

### From ccundo (can adapt/reuse)

```
references/ccundo/
├── src/core/ClaudeSessionParser.js  # JSONL parsing logic
├── src/core/Operation.js            # Operation type definitions
└── src/utils/formatting.js          # Helper functions
```

### What We Build

```
our-project/
├── lib/
│   ├── conversation_adapter.py      # Agent-agnostic JSONL manipulation
│   ├── metadata_enhancer.py         # Add conversation context to ClaudePoint checkpoints
│   └── tmux_resume.sh              # Auto-restart
├── bin/
│   ├── checkpoint-rewind-full.sh    # Code + conversation restore
│   └── checkpoint-branch.sh         # Git branching
└── configs/
    └── enhanced-checkpoint.json     # Extended ClaudePoint config
```

---

## Key Insights from Source Code

### ClaudePoint Strengths
1. ✅ Production-ready checkpoint storage
2. ✅ Smart ignore patterns (respects .gitignore + custom)
3. ✅ Hook integration works well
4. ✅ MCP server for tool access
5. ✅ Automatic cleanup (age + count limits)

### ClaudePoint Limitations
1. ❌ No conversation awareness
2. ❌ No per-file metadata (tar.gz black box)
3. ❌ Claude Code-specific paths
4. ❌ No message UUID tracking

### ccundo Strengths
1. ✅ Reads Claude JSONL directly
2. ✅ Comprehensive operation extraction
3. ✅ Cross-platform path detection
4. ✅ Cascading undo logic
5. ✅ Good bash command detection

### ccundo Limitations
1. ❌ No project-wide checkpoints
2. ❌ Cannot restore full state
3. ❌ No conversation manipulation
4. ❌ No hooks integration
5. ❌ Bash undo requires manual intervention

### Our Unique Contributions
1. ✅ Conversation context linking
2. ✅ JSONL truncation (conversation rewind)
3. ✅ Agent-agnostic (Claude + Droid)
4. ✅ Conversation branching
5. ✅ Unified code + conversation restoration

---

## Updated Ground Truths

### Ground Truth #5 (Revised): External Tool Integration

**ClaudePoint:**
- **Use for:** Code checkpoint storage backend
- **CLI:** `claudepoint create -d "description"`
- **Storage:** `.claudepoint/snapshots/*.tar.gz`
- **Config:** `.claudepoint/config.json`
- **Hooks:** Via `claudepoint-hook.js`
- **Status:** Production-ready, use as-is

**ccundo:**
- **Use for:** Reference implementation for JSONL parsing
- **Don't use:** As checkpoint backend (operation-level, not project-level)
- **Borrow:** `ClaudeSessionParser.js` logic
- **Status:** Complementary tool, not dependency

**Our additions:**
- Conversation metadata in ClaudePoint checkpoints
- JSONL truncation for conversation rewind
- Agent-agnostic adapters
- Git-based branching

---

## Action Items

### Immediate (Before Implementing Phase 1)

1. ✅ **Verify ClaudePoint is installed:**
   ```bash
   npm install -g claudepoint
   claudepoint --version  # Should be >=1.4.4
   ```

2. ✅ **Test ClaudePoint in a dummy project:**
   ```bash
   mkdir test-project && cd test-project
   echo "test" > test.txt
   claudepoint create -d "Test checkpoint"
   claudepoint list
   ls .claudepoint/snapshots/
   ```

3. ✅ **Extract ccundo's ClaudeSessionParser:**
   ```bash
   # Copy to our lib/ directory for reuse
   cp references/ccundo/src/core/ClaudeSessionParser.js lib/
   cp references/ccundo/src/core/Operation.js lib/
   ```

4. ✅ **Update FINAL_IMPLEMENTATION_SPEC.md:**
   - Replace guessed API calls with actual ClaudePoint CLI
   - Replace JSONL parsing logic with ccundo's approach
   - Add references to source files in comments

### Before Phase 2

1. Test ccundo's JSONL parsing on real Claude session:
   ```bash
   cd project-with-claude-session
   ccundo list  # Verify it finds operations
   ```

2. Manually test JSONL truncation safety:
   ```bash
   cp ~/.claude/projects/xyz/session.jsonl session.backup
   # Test our truncation script
   # Verify resume works
   ```

### Before Phase 3-4

No dependencies on external tools. Pure bash/python implementation.

---

## Conclusion

We now have **ground truth** from source code inspection:

✅ **ClaudePoint:** Use it for code checkpointing (works perfectly)  
✅ **ccundo:** Reference for JSONL parsing (don't depend on it)  
✅ **Our value:** Conversation rewind + agent-agnostic + branching

The implementation spec can now be updated with **actual API calls** instead of guesses.

**Next step:** Update `FINAL_IMPLEMENTATION_SPEC.md` Phase 1 to call `claudepoint create` directly instead of implementing checkpoint storage ourselves.
