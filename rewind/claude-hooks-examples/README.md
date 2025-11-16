# Claude Code Checkpoint Hooks - Example Configurations

This directory contains three hook configurations for automatic checkpointing in Claude Code, ranging from minimal to aggressive protection.

## Quick Setup

```bash
# 1. Install ClaudePoint
npm install -g claudepoint

# 2. Install smart checkpoint script
curl -o ~/.local/bin/smart-checkpoint.sh https://raw.githubusercontent.com/[your-repo]/smart-checkpoint.sh
chmod +x ~/.local/bin/smart-checkpoint.sh

# 3. Choose a configuration and copy to ~/.claude/settings.json
```

## Configuration Options

### 1. Minimal (Safest, Least Invasive)

**File:** `minimal-hooks.json`

**What it does:**
- Only checkpoints before `Write` tool (new file creation)
- No analysis of prompts or edits
- Best for teams who want minimal automation

**Use when:**
- You're sharing hooks with a team
- You want maximum control
- You create files infrequently

**Setup:**
```bash
# For project-level (shared with team)
cp minimal-hooks.json .claude/settings.json

# For user-level (just you)
cp minimal-hooks.json ~/.claude/settings.json
```

---

### 2. Balanced (Recommended)

**File:** `balanced-hooks.json`

**What it does:**
- Checkpoints before `Edit`, `Write`, and `NotebookEdit`
- Smart filtering: skips trivial changes, anti-spam protection
- Creates checkpoint when session starts
- Uses significance detection (file size, critical files)

**Use when:**
- You want good protection without spam
- You're the primary user
- You trust the smart filtering logic

**Setup:**
```bash
cp balanced-hooks.json ~/.claude/settings.json
```

**Behavior:**
- ✅ Checkpoints before modifying package.json (critical file)
- ✅ Checkpoints before large edits (>500 chars)
- ❌ Skips checkpoints for typo fixes (<50 chars)
- ❌ Skips if checkpoint created <30 seconds ago

---

### 3. Aggressive (Maximum Safety)

**File:** `aggressive-hooks.json`

**What it does:**
- All features from "Balanced"
- Analyzes user prompts for risky keywords
- Detects batch operations (3+ ops in 60s)
- Checkpoints after Claude finishes responding (Stop hook)

**Use when:**
- You're experimenting heavily
- You frequently ask Claude to make bulk changes
- You want maximum undo capability

**Setup:**
```bash
cp aggressive-hooks.json ~/.claude/settings.json
```

**Additional Protection:**
- ✅ Detects prompts like "refactor all files" and checkpoints first
- ✅ Detects batch operations and checkpoints mid-stream
- ✅ Checkpoints after Claude stops (captures final state)
- ⚠️ More checkpoint spam, but more safety

---

## How Hooks Work

### PreToolUse Hook Flow

```
User: "Edit app.js to add error handling"
  ↓
Claude creates Edit tool call
  ↓
PreToolUse hook fires
  ↓
smart-checkpoint.sh receives:
  - Tool name: "Edit"
  - Tool input: {"file_path": "app.js", "old_string": "...", "new_string": "..."}
  - Session ID
  ↓
Script checks:
  1. Is change size > 50 chars? ✓
  2. Has 30 seconds passed since last checkpoint? ✓
  3. Is this a significant file? ✓
  ↓
Script calls: claudepoint create -d "Auto: Before Edit on app.js"
  ↓
Checkpoint created
  ↓
Edit tool proceeds normally
```

### UserPromptSubmit Hook Flow

```
User: "Refactor all files in src/"
  ↓
UserPromptSubmit hook fires
  ↓
smart-checkpoint.sh receives:
  - Prompt: "Refactor all files in src/"
  ↓
Script detects keyword: "refactor all"
  ↓
Script calls: claudepoint create -d "Auto: Before bulk operation: Refactor all..."
  ↓
Checkpoint created
  ↓
Claude processes prompt normally
```

---

## Smart Checkpoint Logic

The `smart-checkpoint.sh` script implements these rules:

### Anti-Spam Protection
- **30-second cooldown** between checkpoints
- Prevents checkpoint spam during rapid iterations

### Significance Detection

**Always Checkpoint:**
- Critical files: package.json, Dockerfile, requirements.txt, etc.
- Large changes: >500 characters
- New file creation (Write tool)
- Risky prompts: "refactor all", "delete files", etc.

**Skip Checkpoint:**
- Tiny changes: <50 characters
- Test/doc files with small changes
- Changes within 30s of last checkpoint
- Excluded directories: node_modules/, .git/, dist/, etc.

### Batch Operation Detection

Tracks operations per session:
- Counts file modifications
- If 3+ operations in 60 seconds → creates checkpoint
- Prevents catastrophic batch operations without backup

---

## Testing Your Hooks

### Test Minimal Hook

```bash
# In a test project
echo "test" > test.txt

# In Claude Code
User: "Create a file called newfile.txt"
# Should see: ✅ Checkpoint created: Auto: Before file creation
# File is created
```

### Test Balanced Hook

```bash
# Test small change (should skip)
User: "Change line 5 in app.js to add a semicolon"
# Should see: ⏭️ Skipped: Change too small (1 chars)

# Test large change (should checkpoint)
User: "Add a new function to app.js that processes user data..."
# Should see: ✅ Checkpoint created: Auto: Before Edit on app.js
```

### Test Aggressive Hook

```bash
# Test prompt analysis
User: "Refactor all files in the src directory to use async/await"
# Should see: ⚠️ Risky prompt detected: matches 'refactor all'
# Should see: ✅ Checkpoint created: Auto: Before bulk operation: Refactor all...
```

---

## Debugging Hooks

### View Hook Output

Hooks write to stderr, which appears in the Claude Code transcript:

```
⏭️ Skipped: Too soon since last checkpoint (15s < 30s)
✅ Checkpoint created: Auto: Before Edit on config.js
⚠️ Warning: ClaudePoint checkpoint failed
```

### Check State Files

```bash
# View checkpoint timestamps
ls -la ~/.claude-checkpoints/

# See last checkpoint time for session
cat ~/.claude-checkpoints/<session-id>.last

# See operation count (batch detection)
cat ~/.claude-checkpoints/<session-id>.op_count
```

### Test Script Manually

```bash
# Test pre-modify action
echo '{"file_path":"test.js","new_string":"console.log(\"test\")"}' | \
  ~/.local/bin/smart-checkpoint.sh pre-modify test-session Edit

# Test prompt analysis
echo '{"prompt":"refactor all the things"}' | \
  ~/.local/bin/smart-checkpoint.sh analyze-prompt test-session

# Test session start
~/.local/bin/smart-checkpoint.sh session-start test-session startup
```

---

## Customization

### Adjust Anti-Spam Interval

Edit `~/.local/bin/smart-checkpoint.sh`:

```bash
MIN_CHECKPOINT_INTERVAL=60  # Change from 30 to 60 seconds
```

### Adjust Minimum Change Size

```bash
MIN_CHANGE_SIZE=100  # Change from 50 to 100 characters
```

### Add Custom Critical Files

Edit the `detect_significance()` function:

```bash
if echo "$file_path" | grep -qE "(package\.json|myconfig\.yaml|important\.conf)"; then
    # Add your patterns here
fi
```

### Add Custom Risky Keywords

Edit `handle_analyze_prompt()`:

```bash
local risky_patterns=(
    "refactor all"
    "delete.*files"
    "drop database"  # Add your patterns
)
```

---

## Migration Between Configurations

### From Minimal → Balanced

```bash
# Backup current settings
cp ~/.claude/settings.json ~/.claude/settings.json.backup

# Copy balanced configuration
cp balanced-hooks.json ~/.claude/settings.json

# Restart Claude Code
```

### From Balanced → Aggressive

```bash
cp aggressive-hooks.json ~/.claude/settings.json
# Restart Claude Code

# Monitor checkpoint frequency
claudepoint list | head -20

# If too many checkpoints, increase MIN_CHECKPOINT_INTERVAL
```

---

## Integration with ClaudePoint

All configurations assume ClaudePoint is installed. If you prefer Rewind-MCP:

```bash
# Edit smart-checkpoint.sh
# Change the create_checkpoint() function to use MCP instead

# Or use ClaudePoint's built-in hooks:
claudepoint setup  # This installs hooks automatically
```

ClaudePoint's default hooks are equivalent to our "Balanced" configuration but with ClaudePoint-native integration.

---

## Troubleshooting

### Hooks Not Firing

1. Check hooks are enabled: `/hooks` in Claude Code
2. Verify script is executable: `chmod +x ~/.local/bin/smart-checkpoint.sh`
3. Check script path is correct in settings.json
4. Restart Claude Code completely

### Too Many Checkpoints

1. Increase `MIN_CHECKPOINT_INTERVAL` to 60 or 90 seconds
2. Increase `MIN_CHANGE_SIZE` to 100 or 200 characters
3. Switch from "Aggressive" to "Balanced" configuration
4. Add more file patterns to the exclusion list

### No Checkpoints Created

1. Check ClaudePoint is installed: `which claudepoint`
2. Run setup: `claudepoint setup`
3. Test manually: `claudepoint create -d "test"`
4. Check hook logs in stderr output

### Script Errors

```bash
# Test the script directly
bash -x ~/.local/bin/smart-checkpoint.sh pre-modify test-session Edit < test-input.json

# Check for syntax errors
bash -n ~/.local/bin/smart-checkpoint.sh

# View full error output
~/.local/bin/smart-checkpoint.sh pre-modify test-session Edit 2>&1
```

---

## Performance Considerations

### Hook Execution Time

- **Minimal:** ~50ms (just calls claudepoint)
- **Balanced:** ~100-200ms (significance detection + checkpoint)
- **Aggressive:** ~200-300ms (prompt analysis + batch detection)

All hooks have timeouts (5-10s) to prevent blocking Claude Code.

### Storage Impact

Each checkpoint uses:
- ~1-5MB for small projects (<100 files)
- ~10-50MB for medium projects (100-1000 files)
- ClaudePoint auto-cleans old checkpoints (default: keep 10, archive after 30 days)

### CPU Impact

Negligible - hooks run as separate processes and don't block Claude's thinking.

---

## Best Practices

1. **Start with Balanced** - Good protection without spam
2. **Monitor checkpoint frequency** - `claudepoint list` shows recent checkpoints
3. **Customize for your workflow** - Adjust intervals based on your coding patterns
4. **Use project-level for teams** - Keep team hooks minimal to avoid surprises
5. **Use user-level for personal** - Be more aggressive with your own hooks
6. **Test before deploying** - Try hooks in a test project first
7. **Keep hooks simple** - Complex hooks can slow down Claude Code

---

## Example Workflows

### Solo Developer (Aggressive)
```bash
# User-level aggressive hooks for maximum safety
cp aggressive-hooks.json ~/.claude/settings.json

# No project-level hooks
# Don't commit .claude/settings.json
```

### Team Lead (Balanced)
```bash
# Personal aggressive hooks
cp aggressive-hooks.json ~/.claude/settings.json

# Team gets minimal hooks
cp minimal-hooks.json .claude/settings.json
git add .claude/settings.json
git commit -m "Add minimal checkpoint hooks for team"
```

### Learning/Experimenting (Aggressive + Manual)
```bash
# Aggressive auto-checkpoints
cp aggressive-hooks.json ~/.claude/settings.json

# Plus manual checkpoints before risky operations
# In Claude Code: "Create a claudepoint before you start"
```

---

## Support

For issues with:
- **ClaudePoint:** https://github.com/andycufari/ClaudePoint/issues
- **Smart checkpoint script:** [Your issue tracker]
- **Claude Code hooks:** https://github.com/anthropics/claude-code/issues

## License

MIT - Feel free to modify and distribute
