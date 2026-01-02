---
title: Architecture
---

# Rewind Architecture

Rewind is an automatic checkpointing system for AI coding agents that snapshots:

1. **Code state** (repo files)
2. **Conversation state** (agent transcript JSONL)

and makes it easy to jump back to a previous point in time.

The core design choice is that the **agent transcript JSONL is the source of truth** for “chat rewind”. Rewind does not invent its own conversation format.

## High-level workflow

### Checkpoint creation
Triggered either manually (`rewind save`) or via hooks.

1. Gather files under `project_root` respecting ignore patterns.
2. Create `snapshot.tar.gz` under a new checkpoint directory.
3. If a transcript path is known, store a compressed transcript snapshot `transcript.jsonl.gz` + cursor metadata.
4. Write `metadata.json`.

### Jump / restore
Rewind supports independent restore of:

- code
- chat

The default “chat restore” is safe: it creates a **forked session file** rather than rewriting the current session.

## Repository layout

```
rewind/
  bin/
    rewind                 # python entry point
    smart-checkpoint       # hook shell shim
    rewind-checkpoint-ignore.json
  src/
    agents/                # agent profiles + hook normalization (JSON schemas)
    cli.py                 # redesigned CLI
    core/
      controller.py        # orchestrates code + transcript
      checkpoint_store.py  # tar.gz snapshots + metadata
      transcript_manager.py# transcript snapshots + fork creation
    hooks/
      __main__.py          # hook entry
      handler.py           # decisions: when to checkpoint
      io.py, types.py      # typed hook IO
    utils/
      fs.py, env.py, hook_merger.py
  tiers/                   # tier + hook templates
  tests/
  install.sh
```

## Storage model

### Install (system-wide)
`install.sh` installs to:

- `~/.rewind/system/`

and links:

- `~/.local/bin/rewind` → `~/.rewind/system/bin-rewind`

### Project-local runtime state
Rewind runtime state lives in the project as:

- `.agent/rewind/`

Key files:

- `.agent/rewind/checkpoints/<checkpoint>/`
- `.agent/rewind/session.json` (best-effort: agent + transcript_path + session_id + env_file)
- `.agent/rewind/restore-history.json` (best-effort history of restores)

## Checkpoint structure

```
.agent/rewind/checkpoints/<checkpoint>/
  snapshot.tar.gz
  metadata.json
  transcript.jsonl.gz          # present when chat captured
```

### `metadata.json`
Metadata includes:

- file counts and sizes
- `hasTranscript`
- `transcript.cursor` (byte offset + fingerprints)

## Agent abstraction

Rewind keeps core logic agent-agnostic by normalizing hook inputs and transcript behaviors via bundled agent schemas:

- `src/agents/schemas/claude.json`
- `src/agents/schemas/droid.json`

These schemas define:

- how to detect the agent (best-effort)
- which env vars to read for `project_dir` and `env_file`
- transcript-specific details like the last-event-id field (`uuid` vs `id`) and whether title prefixing is enabled

## Transcript handling

### Why snapshots + cursors
We store a full `transcript.jsonl.gz` snapshot for correctness, but also record a cursor so we can usually create forks without decompressing.

### Cursor
The cursor represents “conversation state at checkpoint time” as:

- `byte_offset_end`: end of the last complete JSONL line
- `prefix_sha256`: sha256 of the first 64KB
- `tail_sha256`: sha256 of the last 64KB
- `last_event_id`: best-effort (`uuid` for Claude, `id` for Droid)

### Fork creation algorithm
When restoring chat (default):

1. Create a new session file next to the current transcript: `<uuid>.jsonl`.
2. Prefer the **fast path**:
   - if the current transcript’s `prefix_sha256` matches the checkpoint’s, copy only the first `byte_offset_end` bytes into the fork file.
3. Otherwise **fallback**:
   - inflate `transcript.jsonl.gz` into the fork file.
4. Ensure a trailing newline.
5. Best-effort: prefix the first JSON object with a `title` field by `[Fork] `.

This gives “branching” via the agent’s native session selector, without rewriting ids/parents.

### Rewind by turns (`rewind back <n>`)
`rewind back <n>` is a non-interactive, chat-first rewind designed for agent CLIs that don’t support interactive commands.

Semantics:
- A “turn” is one **user prompt**.
- Rewind is to **before** the Nth-most-recent user prompt.

Implementation:
- Rewind performs a **tail-scan** over the transcript JSONL to find the byte offset of the relevant user message line.
- Forking copies bytes `[0:boundary_offset)` into a new `*.jsonl` session file (best-effort title prefixing still applies).
- `--in-place` rewrites the current transcript to `[0:boundary_offset)` and always writes a safety backup first.

`--both`:
- After computing the boundary offset, Rewind selects the newest checkpoint whose saved transcript cursor has `cursor.byte_offset_end <= boundary_offset` (and matches the current transcript path), restores code to that checkpoint, then performs the chat rewind.

## Hooks

Hooks run `~/.rewind/system/smart-checkpoint <action>` which calls `python3 -m src.hooks <action>`.

Hook responsibilities:

- Decide whether to checkpoint for an event.
- Persist `.agent/rewind/session.json` with `transcript_path` and `session_id`.
- On `SessionStart`, if the agent provides an env-file path, append `REWIND_*` exports so later commands can discover context.
- On `SessionStart`, best-effort append an expanded `PATH` that prepends `~/.local/bin` (some agents parse env-files rather than shell-sourcing them).
- Stay non-blocking: checkpoint failure should not break the agent.

Tier selection:

- Tier hook templates are in `tiers/*.json`.
- Runtime tier choice is stored in `~/.rewind/config.json`.

## Design constraints

- **No external dependencies**.
- **Safe default behavior**: never destroy the current agent transcript.
- **Portable**: works in constrained hook subprocess environments.

## Extension points

- Better diff (`rewind diff`): not currently exposed in the redesigned CLI.
- Smarter GC policies.
- Enhanced checkpoint list UX (show last_event_id, transcript size) while keeping the main CLI minimal.
