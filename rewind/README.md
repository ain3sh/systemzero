# System Zero - Agent Rewind

Rewind is a checkpoint + jump tool for AI coding agents (Claude Code, Factory Droid).

It snapshots **code** and (when available) the agent **conversation transcript**, so you can:

- roll your repo back to a known-good state
- jump to a prior conversation state by creating a **forked agent session** (safe by default)

## What it does

- **Automatic checkpoints** via hooks before file-modifying tools
- **Manual checkpoints** anytime
- **Jump back**: restore code + create a forked session transcript you can select in your agent UI/CLI
- **Zero deps**: Python 3.9+ stdlib only

## Install

```bash
./install.sh
```

`install.sh`:

- installs to `~/.rewind/system/`
- symlinks `~/.local/bin/rewind`
- lets you pick a tier (minimal/balanced/aggressive)
- can register hooks into `~/.claude/settings.json` and/or `~/.factory/settings.json`

## Quickstart

```bash
# Make a manual checkpoint
rewind save "before refactor"

# Jump back (interactive picker)
rewind

# Or jump non-interactively
rewind jump last
rewind jump prev
rewind jump 3

# Rewind the last prompt (non-interactive, fast)
rewind back 1

# Rewind the last 2 prompts and also restore code
rewind back 2 --both

# See recent checkpoints
rewind list
```

## How “chat rewind” works

Rewind does not try to mutate your current session transcript by default.

Instead, it creates a **new forked session JSONL** next to the original transcript file and (best-effort) prefixes the session title with `[Fork] `.
Then you switch sessions using your agent’s normal session selector.

If you want to rewind by conversation turns (user prompts) without using the TUI, use:

```bash
rewind back <n>
```

To rewrite the current transcript in-place (destructive), use:

```bash
rewind back <n> --in-place
```

This always writes a safety backup to `.agent/rewind/transcript-backup/`.

## Docs

- `docs/USAGE.md`
- `docs/ARCHITECTURE.md`

## Extending agent support

Agent-specific behavior is defined in `src/schemas/agents/` (JSON). Adding a new agent is intended to be mostly schema work.

## Development

```bash
python3 -m pytest tests/ -v
```
