---
title: Usage
---

# Rewind Usage

Rewind is designed to stay out of your way.

Most of the time you only need:

- `rewind save` (optional)
- `rewind` (interactive jump)
- `rewind jump …` (non-interactive jump)
- `rewind back <n>` (non-interactive rewind by turns)

## Key concepts

### Checkpoint
A checkpoint is a saved **code snapshot** plus (when available) a saved **agent transcript snapshot**.

### Chat rewind is a fork
By default, rewinding chat creates a **new forked session file** (a new `*.jsonl` next to your current transcript). It does not overwrite your current session.

You then switch to the fork using Claude/Droid’s normal session selector.

### Visual cue: does a checkpoint include chat?
`rewind list` shows `💬` for checkpoints that captured chat; blank means code-only.

## Common flows

### Flow: “I sent a prompt too early; rewind 1 turn” (fast, non-interactive)
```bash
rewind back 1
```

Result:
- no repo files change
- a forked session is created from before your last prompt
- the reverted prompt is printed so you can re-run it

To also restore code:

```bash
rewind back 1 --both
```

### Flow: “I broke things; take me back” (recommended)
1. Run `rewind`.
2. Pick a checkpoint.
3. Pick `Jump`.

Result:
- code is restored in your repo
- a forked chat session is created
- select the forked session in Claude/Droid

### Flow: restore code only
1. Run `rewind`.
2. Pick a checkpoint.
3. Pick `Code only`.

Result:
- repo files are restored
- chat is unchanged

### Flow: rewind chat only
1. Run `rewind`.
2. Pick a checkpoint.
3. Pick `Chat fork`.

Result:
- no repo files change
- a forked session is created

### Flow: jump without thinking (keyboard muscle-memory)
```bash
rewind jump last
rewind jump prev
rewind jump 3
```

Selector rules:
- `last` = newest checkpoint
- `prev` = second newest
- `N` = Nth newest (1-based)
- or pass an exact checkpoint name

### Flow: destructive chat rewrite (avoid unless you know why)
If you truly want to rewrite the current transcript in-place:

```bash
rewind back 1 --in-place
```

Rewind will write a safety backup to:

- `.agent/rewind/transcript-backup/`

The legacy `rewind rewrite-chat <selector>` still exists, but `rewind back <n> --in-place` is the preferred interface.

## Listing checkpoints

```bash
rewind list
```

This shows the last few checkpoints with:

- an index you can use for `rewind jump N`
- `💬` if chat was captured
- checkpoint name + description

For older checkpoints, use `rewind` and type to filter.

## Garbage collection

```bash
rewind gc
```

This asks how many checkpoints to keep (default: 50), shows a preview, then asks for confirmation.

## Troubleshooting

### “Chat fork created, but I don’t see it in my session list”
- Ensure you’re running the same agent installation that owns the transcript directory.
- The fork path printed by Rewind is the exact `*.jsonl` that was created; confirm it exists.

### “My checkpoint has no chat”
- Ensure hooks are installed and running in a session (they capture `transcript_path`).
- `rewind save` outside an agent session will still snapshot code, but may not know your transcript.

If your agent provides an env-file on SessionStart, Rewind also appends `REWIND_TRANSCRIPT_PATH` there; that can help CLI runs discover the transcript later.

Rewind also best-effort prepends `~/.local/bin` to `PATH` in that env-file so `rewind` is available even when the agent subprocess PATH is minimal.

### Debug
```bash
REWIND_DEBUG=1 rewind
```
