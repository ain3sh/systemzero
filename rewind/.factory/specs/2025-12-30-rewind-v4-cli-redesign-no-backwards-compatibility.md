# Goals (first principles)
1. **1–2 commands max in muscle memory** for 95% of cases.
2. **Safe by default**: never destroy the current agent session transcript.
3. **High power remains available** but discoverable, not memorizable.
4. **Agent-first ergonomics**: fast to run from a split shell while mid-session.
5. **No flags-as-UX**: flags only for rare/advanced operations.

# Core primitives (what Rewind actually does)
- **Snapshot**: capture (a) code state, (b) transcript state.
- **Fork**: materialize a transcript state as a *new agent session* (new `*.jsonl`) so user can pick it via the agent session selector.
- **Apply**: restore code state into the working directory.

Everything else is just composition.

# UX model
Rewind is a “checkpoint + jump” tool.

- Users think in terms of: “**Take a checkpoint**” and “**Jump back**”.
- Rewind implements “jump back” as:
  - restore code into the repo
  - create a forked session transcript

# Proposed CLI (new, clean, no legacy)
## Commands
### 1) `rewind` (the default interactive launcher)
Runs an interactive picker (no external deps) and guides through 2 steps:
1. **Pick a checkpoint** (recent first; searchable by typing substring).
2. **Pick an intent**:
   - `Jump` (default): restore code + create forked session
   - `Code only`: restore code only
   - `Chat fork only`: create forked session only

It then executes and prints the single most important next action:
- For `Jump`/`Chat fork only`: prints fork path + “Select `[Fork] …` in your agent session list.”

### 2) `rewind save [message…]`
Manual checkpoint. No flags.
- If running in hook context, transcript is known.
- If running outside, uses `.agent/rewind/session.json` and, if absent, still saves code.

### 3) `rewind jump [selector]`
Non-interactive “I already know what I want” escape hatch.

Selector forms:
- `rewind jump last` (default if omitted)
- `rewind jump prev` (2nd newest)
- `rewind jump <N>` (Nth newest, 1-based)
- `rewind jump <checkpoint-name>`

Behavior: same as `Jump` intent above: restore code + fork chat.

### 4) `rewind list`
Shows a compact table:
- index number
- checkpoint name
- description
- code files count
- `💬` if transcript captured
- timestamp

No extra flags. Always shows a sane window (e.g. last 20). Provide: “Use `rewind` to search older checkpoints.”

### 5) `rewind gc`
Safe garbage collection.
- Defaults: keep last 50.
- Interactively asks for confirmation and shows what would be deleted.

## Advanced/rare command (explicitly scary)
### `rewind rewrite-chat [selector]`
The destructive in-place transcript rewrite.
- Always requires a typed confirmation string, e.g. `REWRITE`.
- Writes backup to `.agent/rewind/transcript-backup/`.

Rationale: keep power but remove accidental usage.

# What disappears (to reduce cognitive load)
- Remove `restore` as a verb entirely; users think “jump”.
- Remove `--code-only` / `--context-only` flags; replace with intents.
- Remove `--in-place` flag; replace with explicit `rewrite-chat` command.
- Remove `undo` as a headline feature; it’s confusing. If desired later, implement `rewind jump prev`.

# Output UX (what user sees)
## After `save`
- `Saved: <checkpoint>  (code: N files, chat: yes/no)`

## After `jump`
- `Jumped to: <checkpoint>`
- `Chat fork: <fork_path>`
- `Next: select the forked session in Claude/Droid session list`

## After `code only`
- `Code restored to: <checkpoint>`

No multi-line dumps unless `REWIND_DEBUG=1`.

# Feasibility against current implementation
This redesign is feasible with minimal underlying changes because:
- We already have:
  - checkpoint list + metadata
  - code restore
  - transcript snapshot + fork creation
- We only need to:
  1. Replace argparse wiring in `src/cli.py`
  2. Add a small interactive picker (stdin prompt) in stdlib
  3. Add selector parsing (`last|prev|N|name`)
  4. Add `rewrite-chat` wrapper calling existing in-place path

# Interactive picker design (stdlib-only)
- On `rewind`:
  - Print numbered list of last K checkpoints.
  - Allow user to type:
    - a number
    - a substring to filter
    - `q` to quit
  - After selection, print intent menu with 1/2/3.

No curses; keep it robust inside agent shells.

# Visual cue: “what session state does this checkpoint correspond to?”
- The list includes `💬` for transcript presence.
- The checkpoint name is timestamp-based.
- Optional future enhancement: store `transcript.last_event_id` in metadata and show a short suffix like `…id:m2` (best-effort), but not required for UX.

# Open decisions
1. Default retention for `gc`: keep 50 vs 100?
2. Default `list` size: 20 vs 30?
3. Should `rewind jump` default to `last` when omitted? (recommended)

If you approve, I’ll implement the new CLI surface area (and remove legacy commands) while keeping the underlying controller APIs stable.