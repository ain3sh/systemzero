# Quick Test Guide: Does It Work?

## ✅ Status: **READY TO TEST**

The code is complete and functional. Here's how to test it in a Claude Code chat.

---

## Prerequisites Check

```bash
# 1. Check ClaudePoint is installed
claudepoint --version
# If not: npm install -g claudepoint

# 2. Check Node.js
node --version
# Need v16+

# 3. Check jq
jq --version
# If not: sudo apt install jq (Linux) or brew install jq (Mac)
```

---

## Test 1: Dry Run (Safe - No Changes)

```bash
cd ~/rewind  # or wherever you cloned the repo

# Test the installer
./bin/install-hooks.sh --dry-run balanced
```

**Expected Output:**
```
✓ Node.js: v22.x.x
✓ jq: jq-1.7
✓ Claude Code detected
[DRY RUN] Would create directories...
✓ Dry run complete - no changes made
```

**If this works → proceed to Test 2**

---

## Test 2: Real Installation

```bash
cd ~/rewind

# Install for real
./bin/install-hooks.sh balanced
```

**Expected Output:**
```
✓ Installed smart-checkpoint.sh to ~/.local/bin/
✓ Installed Node.js modules to ~/.local/lib/checkpoint-rewind/
✓ Installed tier configs to ~/.config/checkpoint-rewind/tiers/
✓ Merged hooks into existing settings
✓ Added CHECKPOINT_TIER to ~/.zshrc
✅ Installation complete!
```

**Restart your shell:**
```bash
source ~/.zshrc  # or ~/.bashrc
```

---

## Test 3: Start Claude Code in Test Project

```bash
# Create a test project
mkdir -p ~/test-checkpoint-demo
cd ~/test-checkpoint-demo

# Create a simple file
echo "console.log('version 1');" > app.js

# Start Claude Code
claude
```

---

## Test 4: Trigger Automatic Checkpoints

**In Claude Code chat, type:**

```
"Edit app.js and change 'version 1' to 'version 2'"
```

**Wait for Claude to complete the edit.**

**What should happen:**
1. Hook fires BEFORE the edit
2. `smart-checkpoint.sh` runs
3. ClaudePoint creates checkpoint
4. Edit proceeds normally

**You won't see the checkpoint creation in the chat, but you'll see it in stderr if you run with --debug**

---

## Test 5: Verify Checkpoint Was Created

**Exit Claude Code** (type `quit` or Ctrl+D)

```bash
# Check for checkpoints
claudepoint list
```

**Expected Output:**
```
Name: auto_before_edit_2025-11-16T19-XX-XX
Description: Auto: Before Edit
Files: 1
Size: XXX bytes
```

**Also check conversation metadata:**

```bash
cat .claudepoint/conversation_metadata.json | jq
```

**Expected Output:**
```json
{
  "auto_before_edit_2025-11-16T19-XX-XX": {
    "agent": "claude-code",
    "sessionId": "some-uuid",
    "messageUuid": "msg-uuid",
    "userPrompt": "Edit app.js and change..."
  }
}
```

---

## Test 6: Anti-Spam Check

**Start Claude again:**
```bash
claude
```

**Make 3 rapid edits:**
```
"Edit app.js and change version 2 to version 3"
```

**Wait 5 seconds**

```
"Edit app.js and change version 3 to version 4"
```

**Wait 5 seconds**

```
"Edit app.js and change version 4 to version 5"
```

**Exit Claude, then check:**
```bash
claudepoint list | grep -c "auto_before"
```

**Expected:** Should see **1-2 checkpoints**, not 3!  
**Why:** Anti-spam (30s cooldown) prevented rapid-fire checkpoints.

---

## Test 7: Code Restore

```bash
# View checkpoints
claudepoint list

# Restore to first checkpoint
claudepoint undo

# Check file content
cat app.js
```

**Expected:** File shows `version 1` or `version 2` (earlier version)

---

## 🎉 Success Criteria

If all tests passed:

✅ Installation completed without errors  
✅ Hooks registered in `~/.claude/settings.json`  
✅ Tier config exists in `~/.config/checkpoint-rewind/tiers/`  
✅ Automatic checkpoint created on edit  
✅ Conversation metadata stored  
✅ Anti-spam prevents duplicate checkpoints  
✅ Code restore works  

**YOUR SYSTEM IS WORKING!** 🚀

---

## 🔥 Quick Troubleshooting

### "No checkpoints created"

Check if hooks are active:
```bash
cat ~/.claude/settings.json | jq '.hooks'
```

Should show `PreToolUse` and `SessionStart` hooks.

### "ClaudePoint not found"

Install it:
```bash
npm install -g claudepoint
```

### "smart-checkpoint.sh not found"

Re-run installer:
```bash
./bin/install-hooks.sh balanced
```

### "Config not found" warning

Check tier config exists:
```bash
ls ~/.config/checkpoint-rewind/tiers/
cat ~/.config/checkpoint-rewind/tiers/balanced-tier.json
```

---

## 📊 What's Actually Happening

```
1. You type: "Edit app.js"
   ↓
2. Claude creates Edit tool call
   ↓
3. PreToolUse hook fires (from ~/.claude/settings.json)
   ↓
4. Runs: ~/.local/bin/smart-checkpoint.sh pre-modify "Edit" "$SESSION_ID"
   ↓
5. Script checks anti-spam (30s cooldown)
   ↓
6. Script calls: claudepoint create -d "Auto: Before Edit"
   ↓
7. Script gets conversation context (via SessionParser)
   ↓
8. Script stores metadata (via ConversationMetadata)
   ↓
9. Hook completes, Edit proceeds
   ↓
10. File modified ✅
```

---

## 🎯 Next Steps After Testing

Once basic checkpointing works:

1. **Try aggressive tier:**
   ```bash
   export CHECKPOINT_TIER=aggressive
   # Restart Claude
   ```

2. **Test conversation rewind** (Phase 2 - not yet implemented)

3. **Test tmux auto-resume** (Phase 3 - not yet implemented)

---

## ⏱️ Time Required

- **Prerequisites check:** 2 minutes
- **Installation:** 1 minute
- **Testing:** 5 minutes
- **Total:** ~8 minutes

---

**Questions? Issues?**

Check `ARCHITECTURE.md` for how it all works, or `UNFUCK_SUMMARY.md` for what was changed.
