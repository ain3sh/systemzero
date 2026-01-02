# Direct answer
Yes—under my earlier “branch refs” approach, **branch switching would mean writing a chosen transcript version back into the single source-of-truth file** at `transcript_path` (either truncate or overwrite-from-snapshot). That works, but it’s inherently destructive (even with backups).

Given your note that **both Droid and Claude Code already support conversation forks** that appear as separate sessions, the more elegant approach is:

> On restore/branch switch, **create a new forked transcript file** (new session) rather than overwriting the existing one.

This lets users use the agent’s built-in session selector to switch branches, and it keeps the original session intact.

You generally **do not need Option C** (full DAG rewrite) for this. Option C is only required if you want *in-file* branching with parent-pointer rewrites or “virtual branching” (editing within a single assistant message’s blocks).

---

# Proposed final spec: Option B-Fork (recommended)
## Goal
Make conversation rewind work by:
1) checkpointing code + transcript
2) restoring code + producing a **forked session JSONL** reflecting the rewound transcript

## Core idea
- Treat `transcript_path` as the authoritative log.
- Each checkpoint stores:
  - code snapshot (already)
  - transcript snapshot + cursor + fingerprints
- `rewind restore <checkpoint>` **creates a new session file** next to the original transcript file that contains the transcript state at the checkpoint.

This is “branching” in the UI-native sense: multiple session JSONLs.

---

# Why this is safe with the schemas
## We avoid risky operations
- We **do not rewrite** `uuid/parentUuid` (Claude) or `id/parentId` (Droid).
- We do not attempt to splice tool blocks or partially edit messages.
- We only create a new JSONL file consisting of a valid prefix of an existing valid transcript.

## Minimal parsing needed
We only need enough parsing to:
- identify agent kind (Claude vs Droid) for diagnostics
- read the last complete JSON line to compute cursor + sanity id
Optional parsing (best-effort) for UX:
- detect a “session start” entry with a `title` field and prefix it with `[Fork] `.

Even if title rewriting fails, the fork still functions (it’s still a selectable session file; naming may vary by CLI).

---

# Transcript checkpoint format (unchanged from Option B)
Each checkpoint’s `metadata.json` gains:
```json
{
  "transcript": {
    "agent": "claude"|"droid"|"unknown",
    "original_path": "/.../session.jsonl",
    "snapshot": "transcript.jsonl.gz",
    "cursor": {
      "byte_offset_end": 12345,
      "last_event_id": "...",
      "prefix_sha256": "...",
      "tail_sha256": "..."
    }
  }
}
```

Snapshot is stored as `transcript.jsonl.gz` (stdlib gzip) for space efficiency.

---

# Restore behavior (fork creation)
## Default behavior
`rewind restore <checkpoint>` performs:
1. Restore code (as today).
2. Create a **new fork transcript file** (new session) corresponding to the checkpoint transcript.
3. Print explicit next steps: “Select the new forked session in your agent UI/CLI.”

## Fork file placement
- Fork path is created next to the original `transcript_path`:
  - `dir = dirname(transcript_path)`
  - `new_session_id = uuid4()`
  - `fork_path = dir / f"{new_session_id}.jsonl"`

This matches how both systems store sessions (directory of many `*.jsonl` files).

## How fork content is generated (efficiency-first)
We generate fork content using a 2-tier strategy:

### Fast path: copy-truncate from current transcript
If current transcript prefix matches checkpoint prefix (`prefix_sha256`), then:
- open current `transcript_path` and copy only the first `byte_offset_end` bytes into `fork_path`.
- ensure fork ends with newline (append if needed).

This avoids decompressing snapshots and is O(size of prefix) with a single sequential read.

### Fallback: materialize from checkpoint snapshot
If prefix mismatch or transcript missing:
- decompress `checkpoints/<cp>/transcript.jsonl.gz` into `fork_path`.

This guarantees correctness even if the current session transcript has diverged.

## UX: making the fork appear as “[Fork] …”
Best-effort title rewrite:
- After fork creation, read the first N lines (e.g. 50) and look for a JSON object with a `title` field.
- If found, prefix it with `[Fork] ` (stacking naturally if already prefixed).
- Rewrite just that line, leaving rest unchanged.

If no title field exists, we still keep the fork session usable.

---

# Branch switching semantics under Option B-Fork
Branch switching becomes “select a different session”:
- The **original session file remains unchanged**.
- Each rewind/restore produces another fork session file.
- User switches by choosing the desired session in Claude/Droid’s session selector.

This aligns with your desired “always go back to un-rewinded version” with minimal moving parts.

---

# CLI design
## `rewind restore` defaults to fork
- `rewind restore <checkpoint>`: restore code + create fork transcript session.
- `--in-place`: overwrite/truncate the current transcript file instead (see Option B-InPlace below).
- `--code-only` / `--context-only` preserved.

## Convenience
- `rewind forks list` (optional): list fork sessions created by rewind (tracked in `.agent/rewind/restore-history.json`).
- `rewind forks show <id>` (optional): print fork path.

We don’t need complex branch refs because the agent already provides a UI.

---

# Hook adjustments (minimal but important)
- Fix hook entry to load tier from config (not hardcoded balanced).
- Always write/update `.agent/rewind/session.json` from hook input (`transcript_path`, `session_id`, agent detect).
- Keep hooks non-blocking; no stdout except SessionStart context injection.

---

# Option B-InPlace (alternative)
If you prefer to avoid creating many session files:
- `rewind restore --in-place` truncates/overwrites the single `transcript_path` (still using cursor fast-path + snapshot fallback) and saves backups.
- Branch switching is done by writing a different saved transcript version back to the same path.

This is simpler operationally but more destructive and less aligned with your native fork UX.

---

# Known risks / caveats
1. **Session discoverability**: We assume the session list is derived from `*.jsonl` presence in the directory (consistent with your observation). If either tool also maintains an index, we may need an additional metadata update.
2. **Title rewriting is best-effort**: schema variance may mean we can’t always inject `[Fork]` cleanly; the fork can still exist and be usable.
3. **Cross-session references**: If logs ever reference external session IDs, copying prefixes might carry stale references. Based on the schemas you provided, the primary linkage is intra-file (`parentUuid/parentId`). We are not altering those.

---

# Confirmation questions
1. Confirm default behavior: should `rewind restore` **create a forked session** by default?
2. Do you want title rewriting as best-effort (add `[Fork] `) or skip it entirely?
3. Should we garbage-collect old fork sessions automatically (e.g., keep last N), or never delete?

If you confirm Option B-Fork, implementation stays “Option B-level parsing” (cursor + light sniffing) and avoids Option C complexity while giving you robust branching.