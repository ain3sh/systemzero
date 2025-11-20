# Quick Test Guide: Rewind-Native Hooks

## ✅ Status: READY TO TEST

Claude/Droid hooks now run entirely on the vendored Rewind engine (no ClaudePoint dependency). Follow these steps to verify installation, checkpoint creation, and rewind behaviour.

---

## 0. Prerequisites

```bash
# Node.js (v18+ recommended)
node --version

# jq for tier parsing
jq --version
```

---

## 1. Installation

Use the new unified installer:

```bash
# From this directory
./install.sh
```

Select "1" (Project Mode) for the default test experience.
Restart your shell afterwards to pick up the `rewind` command.

---

## 2. Prep a Test Project + Start Claude/Droid

```bash
mkdir -p ~/test-checkpoint-demo
cd ~/test-checkpoint-demo

# Initialize (optional, defaults to project mode anyway)
rewind init

echo "console.log('version 1');" > app.js

claude   # or `droid`
```

Keep the agent running for the next steps.

---

## 3. Trigger Automatic Checkpoints

In chat:
```
"Edit app.js and change 'version 1' to 'version 2'"
```

What happens:
1. SessionStart + PreToolUse hooks fire.
2. `smart-checkpoint.sh` delegates to `hook-runner.js`.
3. A snapshot is created in `.rewind/code/snapshots/<name>`.

---

## 4. Inspect Snapshots

After at least one edit, exit the agent.

```bash
# List checkpoints
rewind list
```

You should see entries like `auto_before_edit_... [just now]`.

---

## 5. Code Restore

```bash
rewind list            # choose a checkpoint
rewind restore <name>

cat app.js             # confirm rollback
```

---

## 6. Full Rewind (Code + Conversation)

```bash
rewind restore <name> --mode both
```

If conversation metadata was captured (agent running in detected project path), this will truncate the session log.

---

## ✅ Success Checklist

- `install.sh` runs without errors.
- `rewind` command is available.
- Automatic snapshots appear when agent edits files.
- `rewind restore` correctly reverts files.

If all of the above pass, the Rewind integration is healthy. 🚀
