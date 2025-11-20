# Spec: Fix smart-checkpoint.sh to Read Hook Input from stdin

## The Core Problem

**Current implementation is fundamentally broken.** The script expects `$SESSION_ID`, `$TOOL_NAME`, etc. as environment variables, but according to BOTH Claude Code and Droid CLI documentation, hooks receive this data as **JSON via stdin**.

## What's Actually Broken

### 1. **Wrong Input Method**
- ❌ Script reads: `$SESSION_ID`, `$TOOL_NAME` (env vars)
- ✅ Hooks provide: JSON stdin with `session_id`, `tool_name`, etc.

**Lines affected:**
- Line 83: `local session_id="${SESSION_ID:-unknown}"`
- Line 106: `local session_id="${SESSION_ID:-unknown}"`
- Line 234: `local tool_name="${TOOL_NAME:-unknown}"`

### 2. **Missing stdin Parser**
The script takes a positional argument (`$1`) for action, but **never reads stdin** for the hook JSON input.

### 3. **Agent Detection Logic is Wrong**
Lines 27-32: Script checks for `$CLAUDE_SESSION_ID` and `$DROID_SESSION_ID` env vars that don't exist. Should read from stdin JSON instead.

### 4. **Error We're Seeing**
```
bash: line 1: session_id:01ca7c12-3554-4bc3-bee3-48921b56f2d9: command not found
```

This is bash trying to execute `session_id:UUID` as a command, which suggests the JSON is being parsed incorrectly somewhere in the hook execution pipeline.

## The Fix

### **Rewrite smart-checkpoint.sh to:**

1. **Read JSON from stdin at script start**
```bash
# Read hook input JSON from stdin
HOOK_INPUT=$(cat)
```

2. **Parse relevant fields using jq**
```bash
SESSION_ID=$(echo "$HOOK_INPUT" | jq -r '.session_id // "unknown"')
TOOL_NAME=$(echo "$HOOK_INPUT" | jq -r '.tool_name // "unknown"')
HOOK_EVENT=$(echo "$HOOK_INPUT" | jq -r '.hook_event_name // "unknown"')
```

3. **Detect agent from JSON, not env vars**
```bash
# Agent detection is already correct via directory check
# But could also read from hook input if needed
```

4. **Keep action parameter for backward compat**
```bash
# Action can still come from $1, OR derive from hook_event_name
ACTION="${1:-$(echo "$HOOK_INPUT" | jq -r '.hook_event_name' | tr 'A-Z' 'a-z')}"
```

5. **Remove all references to $SESSION_ID and $TOOL_NAME env vars**

## Files to Modify

### `bin/smart-checkpoint.sh`
- Add stdin reader at top of `main()`
- Parse JSON with jq
- Replace all `${SESSION_ID:-...}` with parsed variable
- Replace all `${TOOL_NAME:-...}` with parsed variable
- Update usage message

## Testing Plan

1. ✅ Hook templates already correct (just call `script.sh pre-tool-use`)
2. ✅ Script receives JSON via stdin automatically from hook system
3. ✅ Parse and use data correctly
4. ✅ Verify checkpoint creation works
5. ✅ Verify metadata storage works

## Key Insight

**The hook templates are actually CORRECT** - they just pass the action name:
```json
{
  "command": "~/.claude/hooks/smart-checkpoint.sh pre-tool-use"
}
```

The hook system itself pipes JSON to stdin. We just need to **read it**!

## Implementation

Rewrite `main()` function to:
1. Read stdin into `HOOK_INPUT` variable
2. Parse JSON fields
3. Use parsed data throughout
4. Keep existing logic for checkpointing

**Estimated changes:** ~50 lines modified in smart-checkpoint.sh