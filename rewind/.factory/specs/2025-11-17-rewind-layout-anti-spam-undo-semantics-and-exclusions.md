Here’s a concrete design that addresses all four points while staying aligned with ClaudePoint’s expectations and your current architecture.

**1. Directory Layout: introduce a `.rewind` nexus without breaking ClaudePoint**

- Keep ClaudePoint’s own layout intact:
  - `.claudepoint/` remains the canonical code-snapshot store and metadata location, as required by the `claudepoint` CLI (per README: it owns `.claudepoint/config.json`, `snapshots/`, `changelog.json`, etc.).
  - We should not attempt to rename or move this directory, since the CLI assumes that project root.
- Consolidate your project-owned pieces under a new, single coordination root:
  - `.rewind/` (new top-level directory at project root) containing three clear subtrees:
    - `.rewind/code/` → purely *pointers* to ClaudePoint’s world, not a second copy:
      - `code/claudepoint` → symlink or small README-style stub pointing at `../.claudepoint` so humans can discover “this is where code snapshots live.”
      - Optionally `code/config.json` → symlink to `.claudepoint/config.json` for easier discovery.
    - `.rewind/conversation/` → your metadata + helpers:
      - `conversation/metadata.json` → becomes the canonical place where `ConversationMetadata.js` writes the checkpoint→message mapping, instead of `.claudepoint/conversation_metadata.json`.
      - `conversation/tools/` → any Rewind-specific JS utilities for conversation (today that’s `ConversationMetadata.js` and `ConversationTruncator.js`, see below).
    - `.rewind/system/` → the project-level library and scripts you install today:
      - `system/bin/` → `smart-checkpoint.sh`, `checkpoint-rewind-full.sh` (for project installs, with user-level still using `$HOME/.checkpoint-rewind`).
      - `system/lib/parsers/SessionParser.js`, `system/lib/metadata/ConversationMetadata.js`, `system/lib/rewind/ConversationTruncator.js`.
      - `system/tiers/` → your tier JSONs for anti-spam/significance logic.
- Migration in code (conceptual, not yet implemented):
  - `install-hooks.sh --project` writes your assets under `.rewind/system/*` instead of `.checkpoint-rewind/*`, and updates paths in `smart-checkpoint.sh`/`checkpoint-rewind-full.sh` to resolve via a “project root → .rewind/system” lookup first, with `$HOME/.checkpoint-rewind` as a fallback.
  - `checkpoint-rewind-full.sh` looks for conversation metadata under `.rewind/conversation/metadata.json` first, falling back to `.claudepoint/conversation_metadata.json` for backward compatibility.
- Result: users see *one* conceptual tree (`.rewind`) that clearly separates "code snapshots (owned by ClaudePoint)" from "Rewind orchestration + conversation state", but you never fight ClaudePoint’s own `.claudepoint` contract.

**2. Anti-spam semantics: structural events should never eat the cooldown**

- Current behavior (from `smart-checkpoint.sh`):
  - `pre-tool-use` (Edit/Write, etc.) → `should_checkpoint(session_id)` and `update_checkpoint_time(session_id)`.
  - `session-start` → also calls `update_checkpoint_time(session_id)`, which explains why your first PreToolUse checkpoint was occasionally skipped.
  - `stop` and potential future subagent events would behave similarly if wired the same way.
- Target behavior:
  - **Structural events (always worth saving)**: `SessionStart`, session `Stop`, future `SubagentStart`, `SubagentStop`.
  - **Volumetric events (spam-prone)**: `PreToolUse` on Edit/Write/NotebookEdit, `post-bash` (if you keep it).
- Proposed rule set:
  - `pre-tool-use` and `post-bash`:
    - Continue using `should_checkpoint(session_id)` + `update_checkpoint_time(session_id)` exactly as today.
    - These are the only actions that move the anti-spam clock.
  - `session-start`, `stop`, `subagent-start`, `subagent-stop` (once you hook them up):
    - **Always attempt a checkpoint**, regardless of elapsed time, *but do not call* `update_checkpoint_time`.
    - The only guard is your tier config significance logic (if/when you add it for structural events), not time-based anti-spam.
- Hook wiring (conceptual):
  - Extend your `hooks/*-hooks.json` templates so that:
    - `SessionStart` → `smart-checkpoint.sh session-start` (already done).
    - `SessionEnd` → `smart-checkpoint.sh stop`.
    - `SubagentStart` → `smart-checkpoint.sh subagent-start`.
    - `SubagentStop` → `smart-checkpoint.sh subagent-stop`.
  - In `smart-checkpoint.sh`, add new cases `subagent-start`/`subagent-stop` that:
    - Call `create_checkpoint` with descriptions like `"Subagent start: ${tool_name}"` / `"Subagent stop: ${tool_name}"`.
    - Capture conversation context and store metadata as with other actions.
    - **Do not** touch `update_checkpoint_time` in these branches.
- This gives you the behavior you want: structural milestones always get a checkpoint; only rapid tool invocations are throttled.

**3. Undoing an undo via emergency backups (ClaudePoint semantics)**

- From `checkpoint-rewind-full.sh` and your logs, the flow is:
  - `claudepoint undo`:
    - Creates an emergency backup claudepoint named like `emergency_backup_YYYY-MM-DDTHH-MM-SS`.
    - Restores code to the previous claudepoint in the chain.
  - `checkpoint-rewind-full.sh` treats this as a regular `claudepoint undo` and reports the emergency backup in its footer.
- According to ClaudePoint’s README + manifest structure:
  - Emergency backups are **just regular claudepoints** with a special `name` and entry in `.claudepoint/snapshots/*` and the changelog.
- Practical recipe to “undo the undo” (what we’d document / rely on):
  - Run `claudepoint list` to find the emergency backup name (e.g., `emergency_backup_2025-11-17T14-15-51`).
  - Run `claudepoint restore emergency_backup_2025-11-17T14-15-51` (or via whatever restore command your installed version supports).
  - If you want Rewind to offer a one-shot helper, `checkpoint-rewind-full.sh` could in the future accept a flag like `--undo-undo` that:
    - Greps the most recent `emergency_backup_*` in `.claudepoint/changelog.json` or `snapshots/`, then
    - Calls `claudepoint restore` on it.
- For now, the important semantic guarantee is: *you always have a first-class checkpoint object for the pre-undo state*, so reverting the undo is just another restore.

**4. Directory exclusions: clean, user-facing configuration living in your hooks**

Given ClaudePoint’s config (from README and your `.claudepoint/config.json`):

```json
{
  "ignorePatterns": [
    "node_modules", ".git", ".env", "*.log",
    ".DS_Store", "dist", "build", ".next", ".claudepoint"
  ],
  "additionalIgnores": [],
  "forceInclude": []
}
```

we don’t need to reimplement ignore logic in Bash; we should **configure ClaudePoint itself** during install in a way that’s fully managed by your hooks.

Proposed model:

- **Single source of truth for ignores in your repo**
  - Add a new file `configs/claudepoint-ignore.json` in this project with structure:
    ```json
    {
      "additionalIgnores": [".git", "dist", "coverage"],
      "forceInclude": [".env.example"],
      "overrideIgnorePatterns": null
    }
    ```
  - Semantics:
    - `additionalIgnores`: merged into ClaudePoint’s `additionalIgnores` array (append-only).
    - `forceInclude`: merged into ClaudePoint’s `forceInclude` array.
    - `overrideIgnorePatterns`: when non-null, **replaces** ClaudePoint’s `ignorePatterns`; when `null`, we leave the base patterns from ClaudePoint as-is.
- **Installer responsibility (`install-hooks.sh`)**
  - On install, after creating `.claudepoint/config.json` (or confirming it exists), `install-hooks.sh` would:
    - Read `.claudepoint/config.json` with `jq`.
    - If `configs/claudepoint-ignore.json` exists in the project, load it and apply:
      - If `.overrideIgnorePatterns` is non-null and is an array, set `config.ignorePatterns` to that array.
      - Append entries from `.additionalIgnores` to `config.additionalIgnores` (deduplicated).
      - Append entries from `.forceInclude` to `config.forceInclude` (deduplicated).
    - Write the merged result back to `.claudepoint/config.json`.
  - For project-level installs, this is done in the project’s `.claudepoint/` only; user-level installs respect the user’s global config unless you explicitly detect and apply a global variant.
- **At runtime**
  - `smart-checkpoint.sh` and `checkpoint-rewind-full.sh` don’t need to know about ignore lists; they just call `claudepoint create/undo/restore` and rely on ClaudePoint to apply the configured patterns.
  - The only Rewind-visible effect is that snapshots shrink and avoid noisy directories (e.g., `node_modules`, `dist`, `.cache`, test artifacts) according to the configured patterns.
- **User experience**
  - Repo authors configure *project-local* excludes by editing `configs/claudepoint-ignore.json` and re-running `install-hooks.sh`.
  - Individual users don’t have to touch `.claudepoint/config.json` directly or copy core files around; your installer remains the single entrypoint.

---

If you’re happy with this design, next step would be:
- Implement the `.rewind` consolidation plus config lookups in the scripts and installer.
- Wire structural events (SessionEnd/SubagentStart/SubagentStop) into hooks using the anti-spam rules above.
- Add the `configs/claudepoint-ignore.json` contract and corresponding merge logic in `install-hooks.sh`.
- Optionally add a small helper around emergency backups (e.g., `checkpoint-rewind-full.sh --undo-undo`) if you want an ergonomic “panic button.”