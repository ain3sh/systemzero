Here’s the implementation plan to replace ClaudePoint entirely with a Rewind-native checkpoint engine & CLI.

**1. New `.rewind` layout and ownership**
- Introduce a Rewind-owned project tree:
  - `.rewind/code/` → code checkpoint engine data:
    - `config.json` (engine config: `maxCheckpoints`, `maxAgeDays`, `ignorePatterns`, `additionalIgnores`, `forceInclude`, `nameTemplate`).
    - `snapshots/<checkpoint-name>/manifest.json` and `files.tar.gz` for each checkpoint.
    - `changelog.json` for create/restore history.
  - `.rewind/conversation/` → `metadata.json` storing `checkpointName → { agent, sessionId, sessionFile, messageUuid, userPrompt, timestamp }`.
  - `.rewind/system/` (for project installs) → our installed assets:
    - `bin/smart-checkpoint.sh`, `bin/checkpoint-rewind-full.sh`.
    - `lib/parsers/SessionParser.js`, `lib/metadata/ConversationMetadata.js`, `lib/rewind/ConversationTruncator.js`.
    - `tiers/*.json` for anti-spam and significance rules.
- Remove all reliance on `.claudepoint/` and the `claudepoint` CLI from our code and docs; any existing references get deleted or migrated to use `.rewind` instead.

**2. Rewind-native checkpoint engine (`CheckpointEngine`)**
- Add `lib/rewind/CheckpointEngine.js` (ESM Node module) that encapsulates all code snapshot logic:
  - `constructor({ projectRoot })` → sets `this.projectRoot` and `this.baseDir = path.join(projectRoot, '.rewind', 'code')`.
  - `loadConfig()` / `saveConfig(config)` → manage `.rewind/code/config.json` with defaults and overrides.
  - `scanProject()` → crawl `projectRoot`, honoring `ignorePatterns`, `additionalIgnores`, `forceInclude`, and `.gitignore`.
  - `createCheckpoint({ description, name, force })` → build manifest (name, timestamp, description, file list, fileCount, totalSize), write tarball, update changelog, and run cleanup; returns `{ success, name, description, fileCount, totalBytes, noChanges }`.
  - `listCheckpoints()` → read all manifests under `snapshots/` and return a time-sorted list.
  - `restoreCheckpoint({ name })` → create an emergency backup checkpoint (e.g. `rewind_backup_<timestamp>`) and restore the requested checkpoint’s tarball into the project.
  - `undoLastCheckpoint()` → resolve latest checkpoint via `listCheckpoints()` and delegate to `restoreCheckpoint`.
  - `cleanupOldCheckpoints()` → enforce `maxCheckpoints` and `maxAgeDays` by deleting older snapshot dirs.
- Keep anti-spam *inside the CLI only*: `CheckpointEngine` itself does not enforce cooldown; it just exposes `createCheckpoint`, leaving hook-level anti-spam to Bash and optional CLI cooldown logic to a thin wrapper.

**3. Rewind CLI (`bin/rewind.js`)**
- Create a small, intuitive CLI that wraps `CheckpointEngine` for human use:
  - `rewind save [--name <name>] [--description <text>] [--force]` → calls `createCheckpoint`.
  - `rewind list` → prints index, name, timestamp, fileCount, size.
  - `rewind undo` → calls `undoLastCheckpoint()`.
  - `rewind restore <name>` → calls `restoreCheckpoint({ name })`.
  - `rewind status` → shows config summary (`maxCheckpoints`, `maxAgeDays`), last checkpoint, and config path.
- Resolve `projectRoot` as the current working directory; we’ll treat “directory with `.rewind` or git repo root” as the natural project boundary.

**4. Hook integration with Node shim (no `claudepoint` subprocess)**
- Add `lib/rewind/hook-entry.js` to act as the single entrypoint for hooks:
  - Reads hook JSON from stdin, plus a CLI arg specifying the action: `pre-tool-use`, `session-start`, `post-bash`, `stop`, and later `subagent-start`/`subagent-stop`.
  - Constructs a `CheckpointEngine` for the hook’s `cwd` (from hook input).
  - For each action, builds a description (e.g. `"Auto: Before Edit"`, `"Session start"`, `"Subagent start: ${toolName}"`) and decides `force`:
    - Structural events: `session-start`, `stop`, `subagent-start`, `subagent-stop` → `force: true`.
    - Volumetric events: `pre-tool-use`/`post-bash` → `force` set by Bash anti-spam logic (see next step).
  - Calls `createCheckpoint`, and if a new checkpoint is created, immediately:
    - Invokes `SessionParser` to get the current session/message.
    - Uses `ConversationMetadata.add(checkpointName, conversationData)` to update `.rewind/conversation/metadata.json`.
  - Prints JSON to stdout for Bash: `{ success, checkpointName, noChanges, error }`.
- Update `smart-checkpoint.sh`:
  - Remove all `claudepoint` calls and output-parsing.
  - Keep tier-based anti-spam in Bash:
    - For `pre-tool-use` and `post-bash`, use `should_checkpoint(session_id)` and `update_checkpoint_time(session_id)` as today.
    - For `session-start` (and later `stop`/subagent events), **do not** call `update_checkpoint_time`.
  - For actions that should create a checkpoint, pipe hook JSON into `node .rewind/system/lib/rewind/hook-entry.js <action>` and interpret the JSON result for logging only.

**5. Conversation metadata and full rewind alignment**
- Update `ConversationMetadata.js` to be Rewind-only:
  - `claudepointDir`/`metadataFile` → replace with `this.baseDir = path.join(projectRoot, '.rewind', 'conversation')` and `metadataFile = baseDir + '/metadata.json'`.
  - Keep the same public API: `add`, `get`, `list`, `remove`, `cleanup`.
- Update `ConversationTruncator.js` only as needed to ensure paths passed in come from `.rewind/conversation/metadata.json`; its file-truncation semantics stay the same.
- Refactor `checkpoint-rewind-full.sh`:
  - Read metadata from `.rewind/conversation/metadata.json`.
  - Given a checkpoint name, obtain `sessionFile` and `messageUuid`.
  - Call `rewind restore <checkpointName>` to restore code.
  - Then call `ConversationTruncator` to truncate the session JSONL to `messageUuid`.

**6. Anti-spam semantics (structural vs volumetric events)**
- Encode the rules explicitly:
  - Volumetric events:
    - `pre-tool-use` for Edit/Write/NotebookEdit and `post-bash` → gated by Bash’s `should_checkpoint` and `update_checkpoint_time` using your tier config.
  - Structural events:
    - `session-start`, `stop`, `subagent-start`, `subagent-stop` → always attempt a checkpoint; **never** update anti-spam timestamps.
- Implementation:
  - Bash decides whether to call the hook-entry Node shim for volumetric events.
  - Node `CheckpointEngine` itself is stateless w.r.t anti-spam; if the CLI wants its own cooldown, it can add a separate timestamp file later.

**7. Directory exclusion configuration (Rewind-owned)**
- Define a project config file `configs/rewind-checkpoint-ignore.json` in this repo with schema:
  ```json
  {
    "ignorePatterns": [".git", "node_modules", "dist", "build", "coverage"],
    "additionalIgnores": [".cache", "tmp", "temp"],
    "forceInclude": [".env.example"]
  }
  ```
- `CheckpointEngine.loadConfig()` will:
  - Start from built-in defaults.
  - If `.rewind/code/config.json` exists, merge it.
  - If `configs/rewind-checkpoint-ignore.json` exists in the project root, overlay its values as the new defaults (with `ignorePatterns` replacing the base list; `additionalIgnores` and `forceInclude` unioned).
- `install-hooks.sh` will:
  - Ensure `.rewind/code/config.json` exists for the target scope (project/user) with defaults.
  - Optionally call a tiny Node helper to apply `configs/rewind-checkpoint-ignore.json` into that config during install, so snapshots automatically avoid noisy dirs.

**8. Cleanup of legacy ClaudePoint integration**
- Remove all remaining references to:
  - The `claudepoint` CLI or npm package.
  - `.claudepoint/` (config, snapshots, changelog, conversation metadata) in scripts and Node code.
  - Any ClaudePoint-specific hooks or MCP-related commands in docs or helper scripts.
- Ensure tests (or new smoke tests) hit the new Rewind engine and CLI directly rather than the old binary.

If this plan looks good, next step after spec mode is to implement `CheckpointEngine`, the `rewind` CLI, the Node hook-entry shim, update the Bash scripts and installer to use `.rewind`, and then add/adjust tests to exercise the new flow end-to-end (including anti-spam + ignore patterns).