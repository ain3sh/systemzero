Got it: no backwards compatibility, no runtime dependency on ClaudePoint, and no legacy maintenance. Here’s a revised, ClaudePoint‑free spec.

**1. Clean break from ClaudePoint**
- Remove all usages of the `claudepoint` binary and its output parsing:
  - Delete / rewrite any `claudepoint create`, `claudepoint undo`, `claudepoint list` calls in `smart-checkpoint.sh`, `checkpoint-rewind-full.sh`, and tests.
  - Remove path fallbacks to `.claudepoint` and any assumptions that directory exists.
- Strip ClaudePoint-specific references from our Node libs:
  - Update `ConversationMetadata.js` and `ConversationTruncator.js` so they no longer mention `.claudepoint`; they should treat Rewind’s own layout as the only source of truth.
- Keep ClaudePoint’s repo as design inspiration only: we may copy algorithms/structures, but there will be no direct npm dependency and no need to match their config or hooks.

**2. New Rewind checkpoint engine (vendored, trimmed, and renamed)**
- Add a new internal module, e.g. `lib/rewind/CheckpointEngine.js`:
  - Implemented in Node (ESM), structurally inspired by `CheckpointManager` but with a **minimal, Rewind‑centric API**.
  - Public API (all async):
    - `constructor({ projectRoot })` → stores `projectRoot`, sets `this.baseDir = path.join(projectRoot, '.rewind', 'code')`.
    - `loadConfig()` / `saveConfig(config)` → manages `.rewind/code/config.json` with fields: `maxCheckpoints`, `maxAgeDays`, `ignorePatterns`, `additionalIgnores`, `forceInclude`, `nameTemplate`.
    - `scanProject()` → returns filtered list of relative file paths using `ignore` patterns plus `.gitignore` rules.
    - `createCheckpoint({ description, name, force })` → snapshots all files, writes `snapshots/<name>/manifest.json` plus `files.tar.gz`; returns `{ success, name, description, fileCount, totalBytes, noChanges }`.
    - `listCheckpoints()` → reads manifests and returns a sorted array `{ name, timestamp, description, fileCount, totalSize }`.
    - `restoreCheckpoint({ name })` → restores code from a single full snapshot, and always creates an emergency backup checkpoint first (with a name like `rewind_backup_<timestamp>`).
    - `undoLastCheckpoint()` → helper that finds most recent checkpoint and calls `restoreCheckpoint` for it.
    - `cleanupOldCheckpoints()` → enforces `maxCheckpoints` and `maxAgeDays` on `.rewind/code/snapshots/*`.
  - Explicitly **remove** features we don’t need from ClaudePoint:
    - No MCP server or slash-command logic.
    - No incremental checkpoint chain logic.
    - No ClaudePoint‑style hooks config (`.claudepoint/hooks.json`).
    - No emoji/slogan UX inside the engine; CLI can decide how much flair to show.
  - Internal behavior:
    - Anti‑spam: engine’s own 30s cooldown will be used only for the human CLI (see below); hooks will opt into `force: true` when appropriate.
    - Ignore handling: same basic algorithm as ClaudePoint (using `ignore` + `.gitignore` + `forceInclude`), but driven by our own `config.json` schema.

**3. New `.rewind` layout (Rewind is the single source of truth)**
- Define a simple, Rewind‑owned tree at project root:
  - `.rewind/`
    - `code/`
      - `config.json` → engine config.
      - `snapshots/<checkpoint-name>/manifest.json` and `files.tar.gz` → full snapshots.
      - `changelog.json` → optional lightweight history of create/restore operations.
    - `conversation/`
      - `metadata.json` → mapping `checkpointName → { agent, sessionId, sessionFile, messageUuid, userPrompt, timestamp }`.
    - `system/`
      - `bin/` → installed scripts (`smart-checkpoint.sh`, `checkpoint-rewind-full.sh`) for project scope.
      - `lib/parsers/SessionParser.js`.
      - `lib/metadata/ConversationMetadata.js`.
      - `lib/rewind/ConversationTruncator.js`.
      - `tiers/*.json` → anti‑spam/significance configs.
- There will be **no `.claudepoint/` dependency** in our code, and no requirement that such a directory exist in new installs.

**4. Rewind CLI design (intuitive, minimal commands)**
- Introduce a new Node CLI entrypoint, e.g. `bin/rewind.js` (with `#!/usr/bin/env node` and bin mapping in package.json):
  - Commands (all project‑root aware):
    - `rewind save [--name <name>] [--description <text>] [--force]`
      - Calls `CheckpointEngine.createCheckpoint`.
      - No description/name → auto name like `auto_before_edit_<timestamp>`.
    - `rewind list`
      - Calls `listCheckpoints()` and prints an index, name, timestamp, file count, size.
    - `rewind undo`
      - Calls `undoLastCheckpoint()`.
    - `rewind restore <name>`
      - Calls `restoreCheckpoint({ name })`.
    - `rewind status`
      - Prints config summary + last few changelog entries.
  - CLI will be intentionally small and intuitive—no need to support every ClaudePoint command.

**5. Hook integration: direct engine usage (no claudepoint subprocess)**
- Replace the current `claudepoint create` subprocess in hooks with a small Node shim dedicated to hook calls, e.g. `lib/rewind/hook-entry.js`:
  - Input contract: reads the standard hook JSON from stdin (same as now) and accepts a single CLI arg for action: `pre-tool-use`, `session-start`, `post-bash`, `stop`, etc.
  - Behavior:
    - Derive `sessionId`, `toolName`, and event type from hook input.
    - Decide `force` flag:
      - Structural events (`session-start`, `stop`, future `subagent-start`, `subagent-stop`) → `force: true`, no time-based anti‑spam checks.
      - Volumetric events (`pre-tool-use`, `post-bash`) → respect tier/anti‑spam decisions still implemented in Bash.
    - Call `CheckpointEngine.createCheckpoint({ description, name, force })`.
    - If a checkpoint is created, immediately gather conversation context via `SessionParser` and record it via `ConversationMetadata.add` into `.rewind/conversation/metadata.json`.
    - Print **machine-readable JSON** to stdout: `{ success, checkpointName, noChanges, error }` and exit 0/1 appropriately.
  - `smart-checkpoint.sh` will be simplified:
    - No more parsing of ClaudePoint’s text banners.
    - For each action, it just decides whether to skip based on anti‑spam, then pipes hook JSON into `node .rewind/system/lib/rewind/hook-entry.js <action>` and interprets the JSON result minimally for logging.

**6. Anti‑spam semantics (no session start penalties)**
- Encode the rules you requested explicitly:
  - Only these actions move the anti‑spam timer: `pre-tool-use` for Edit/Write/NotebookEdit and `post-bash` (or whichever we keep).
  - Structural events: `session-start`, session `stop`, `subagent-start`, `subagent-stop` (when wired) **never** update the anti‑spam timestamp and always attempt a checkpoint (tier logic can still decide to skip by description/filtering later if we add that).
- Implementation division:
  - Bash `smart-checkpoint.sh` keeps the interval tracking in its own state dir (as today), keyed by session id and tier config.
  - Node `CheckpointEngine` exposes a `force` flag for cases where we explicitly want to bypass its internal timing; hooks always pass `force` for structural events and never rely on engine anti‑spam.

**7. Conversation metadata and full rewind integration**
- `ConversationMetadata.js` updates:
  - Use `.rewind/conversation/metadata.json` as the only path.
  - Provide simple `add`, `get`, `list`, `remove`, and `cleanup` APIs exactly as today but pointing at `.rewind`.
- `checkpoint-rewind-full.sh` updates (conceptually):
  - Resolve `metadataFile` to `.rewind/conversation/metadata.json`.
  - Given a checkpoint name, read session id + message UUID from metadata.
  - Call `rewind restore <checkpoint>` (our CLI) instead of any ClaudePoint command.
  - Invoke `ConversationTruncator` (unchanged) with the session JSONL path + target UUID.

**8. Directory exclusion configuration (Rewind-owned)**
- Introduce `configs/rewind-checkpoint-ignore.json` in this repo with schema:
  ```json
  {
    "ignorePatterns": [".git", "node_modules", "dist", "build", "coverage"],
    "additionalIgnores": [".cache", "tmp", "temp"],
    "forceInclude": [".env.example"]
  }
  ```
- `CheckpointEngine.loadConfig` will:
  - Start from built‑in defaults (similar to ClaudePoint’s, but we own them).
  - If `.rewind/code/config.json` exists, merge it.
  - If `configs/rewind-checkpoint-ignore.json` exists at project root, overlay its values (with `ignorePatterns` replacing the default list and `additionalIgnores` / `forceInclude` being unioned).
- `install-hooks.sh` responsibility:
  - Ensure `.rewind/code/config.json` exists (creating with defaults if needed).
  - Optionally run a small Node helper to apply `configs/rewind-checkpoint-ignore.json` into `.rewind/code/config.json` once at install time.

---

If you’re happy with this spec (no legacy ClaudePoint, finalized project name "Agent Rewind" as sole owner of the checkpoint format, and a small intuitive CLI), we can proceed to implementation next: adding `CheckpointEngine`, the `rewind` CLI, the hook-entry Node shim, updating `smart-checkpoint.sh`/`checkpoint-rewind-full.sh`, and wiring the installer to create the new `.rewind` structure and config.
