## Goal
Add a non-interactive, blazing-fast CLI path to rewind the last **N user prompts** without using the TUI, designed for “oops, I sent that prompt too early” workflows inside agent CLIs that don’t support interactive commands.

## User-Facing CLI
### New subcommand
- `rewind back <n>`
  - Default behavior: **chat-only**, rewind to **before** the Nth-most-recent **user prompt**, and **fork** the transcript (safe by default).

### Flags
- `--both`
  - Also restore code to the nearest checkpoint **at or before** the computed chat boundary.
- `--in-place`
  - Rewrite the current transcript in-place to the boundary.
  - Always creates a safety backup under `.agent/rewind/transcript-backup/`.
- `--copy` (best-effort, optional)
  - Attempts to copy the reverted prompt(s) to clipboard; falls back to printing prompts.

### Output contract
- Always print: `Fork created: <session_id>` when forking.
  - `<session_id>` is derived from the fork file name (e.g. `fork_path.stem`).
- Print reverted prompt(s) for manual copy when `--copy` isn’t available/doesn’t work.
- For `--in-place`: print `Chat rewritten in-place` (and optionally the backup path).

## Semantics
### What is a “turn”?
- A “turn” is **one user prompt** (not user+assistant pair).

### Boundary definition
- The boundary is the byte offset to the **start of the JSONL line** corresponding to the Nth-most-recent user message.
- Rewind means: keep transcript content **strictly before** that byte offset.

### Modes
- `rewind back <n>`: chat-only fork
- `rewind back <n> --both`: chat boundary + code restore to nearest checkpoint at-or-before boundary
- `rewind back <n> --in-place`: chat rewrite only (no fork) + required backup
- `rewind back <n> --both --in-place`: allowed; applies code restore as in `--both` plus in-place chat rewrite

## Fast Path Implementation Strategy (Tail-scan + cursor match)
### 1) Discover transcript path + context
- Primary: load `.agent/rewind/session.json` (already persisted by hooks) to get `transcript_path`, `session_id`, `agent`.
- Optional improvement (if present): allow env overrides (e.g. `REWIND_TRANSCRIPT_PATH`, `REWIND_PROJECT_ROOT`) but keep defaults simple.

### 2) Tail-scan transcript to find boundary and prompts
Add `TranscriptManager.find_boundary_by_user_prompts(transcript_path: Path, n: int) -> BoundaryResult`:
- Read the file in reverse by fixed-size chunks.
- Split into lines, parse only the needed JSON lines until N user messages are found.
- Extract “prompt text” from a user message by concatenating `content[*].text` blocks (fallback to empty or raw JSON if unexpected shape).
- Compute the boundary byte offset as the byte index of the matched user-message line start.

Performance target: O(file tail scanned until N prompts found), not O(entire file).

### 3) Fork or rewrite transcript at boundary
Add transcript operations that avoid full re-parse:
- `create_fork_at_offset(...)`:
  - Create fork file next to current transcript.
  - Rewrite title prefix only if current agent schema allows it (reuse existing gating logic).
  - Copy bytes `[0:boundary_offset)` efficiently (stream copy).
- `rewrite_in_place_at_offset(..., backup_dir=.agent/rewind/transcript-backup/)`:
  - Write a backup copy first.
  - Atomically replace the transcript with the truncated content.

### 4) `--both`: pick checkpoint by cursor match
- Compute `boundary_offset`.
- From `controller.list_checkpoints()` (newest first), choose the first checkpoint where:
  - checkpoint has transcript metadata with `cursor.byte_offset_end <= boundary_offset`, and
  - transcript `original_path` matches the current transcript path (best-effort string/path compare).
- Restore code using `controller.restore(name=..., mode="code", skip_backup=False)`.
- Then perform chat fork/rewrite at boundary as above.

If no checkpoint qualifies: proceed with chat-only and print a note.

## Code Changes (planned files)
- `rewind/src/cli.py`
  - Add `back` subcommand parser and handler.
  - Ensure output contract (`Fork created: ...`) and prompt printing.
  - Deprecation cleanup: keep `rewrite-chat` as-is for now, but `back --in-place` is the recommended replacement going forward.
- `rewind/src/core/controller.py`
  - Add a new method like `rewind_back(n: int, both: bool, in_place: bool, copy: bool) -> dict[str, Any]` that orchestrates: session discovery → tail-scan boundary → optional code restore → fork/rewrite.
- `rewind/src/core/transcript_manager.py`
  - Add `BoundaryResult` + tail-scan boundary finder.
  - Add `create_fork_at_offset` and `rewrite_in_place_at_offset` helpers (reusing existing title-prefix gating).

## Error handling
- No transcript path available: print a clear error and exit non-zero.
- `n <= 0`: argparse validation error.
- Not enough user prompts in transcript: print a clear error and exit non-zero.
- JSON parse errors in tail-scan: skip invalid lines and keep scanning; if boundary can’t be found, fail gracefully.

## Tests (planned)
- Add focused unit tests in `rewind/tests/`:
  - Boundary computation for `n=1`, `n=2` on small synthetic JSONL transcripts.
  - Prompt extraction from `content` blocks.
  - Fork creation truncates to boundary and returns expected fork filename (session id).
  - `--both` checkpoint selection: verify it picks the correct checkpoint given cursor offsets.

## Non-goals (to keep it lean)
- No new TUI behavior.
- No code-only `--n` mode.
- Clipboard integration is best-effort and optional; core functionality works without it.

## Open choices (quick yes/no)
1) Do you want `rewind back <n>` to also accept `rewind back` as shorthand for `rewind back 1`?
  - Yes, for convenience.
2) For reverted prompt printing: prefer stdout or stderr? (I recommend prompts to stderr so stdout stays automation-friendly.)
  - Stderr sounds good.

## Tangent

Not for this rewind back <n>, but for the main usage commands, we should add a `--dry-run` flag if not already implemented.