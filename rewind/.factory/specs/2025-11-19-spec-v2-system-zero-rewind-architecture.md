# Specification v2: "System Zero" Rewind & Checkpoint Architecture

## 1. Vision & Design Philosophy
Move from a "script-based utility" to a **robust, cohesive application state management system**. The system will treat Code and Conversation Context as a single, atomic unit of "State".
- **Elegance:** Single source of truth for configuration and logic (Node.js), minimizing brittle shell scripts.
- **Performance:** Zero-copy checks. We only create artifacts when state creates a distinct signature.
- **Safety:** Atomic restores. Code and Context must move together or not at all.

## 2. Architectural Refactoring

### A. The `RewindController` (New Core Orchestrator)
A new central class replacing ad-hoc logic in `rewind.js` and `hook-entry.js`.
*   **Responsibilities:**
    *   Coordinating `CheckpointStore` (Code) and `ContextManager` (Conversation).
    *   Transactional `restore(checkpointId, mode)`:
        1.  Create "Safety Point" (Undo buffer).
        2.  Restore Code (via Store).
        3.  Restore Context (via Manager).
        4.  If any step fails -> Rollback to Safety Point.
    *   Calculating diff summaries between checkpoints for the UI.

### B. Elimination of `smart-checkpoint.sh` Logic
The shell script is currently responsible for anti-spam logic and config parsing using `jq`/`grep`. This is fragile and slow.
*   **Change:** `smart-checkpoint.sh` becomes a dumb pass-through shim.
*   **New Logic:** Move all decision logic (Debounce, "Significant Change" detection, Config loading) into `lib/hooks/HookHandler.js`.
*   **Benefit:** Unified config handling in JS, better testing, faster execution (hot VM for repeated calls if we were server-based, but even as CLI, cleaner than shell forking).

### C. Enhanced `CheckpointEngine` -> `CheckpointStore`
*   **Algorithmic Improvement (Signature-First):**
    *   *Current:* Scans, Stats, Hashes, *then* compares.
    *   *Refinement:* Maintain a persistent `head_signature` (lightweight file).
    *   **Optimization:** During `pre-tool-use`, we do a "Fast Scan" (mtime + size only). If matches `head_signature`, return immediately (0ms latency). Only read/hash content if mtime changed.
*   **Storage:** Continue using `tar.gz` for simplicity/portability, but ensure strictly atomic writes (write `temp.tar.gz` -> rename).

### D. `ContextManager` (Evolution of `ConversationTruncator`)
*   Integrate `ConversationMetadata` and `ConversationTruncator` into one cohesive unit.
*   **New Feature:** `validateContext(sessionId)`: Checks if the running agent's session file on disk matches the expected signature.
*   **Handling Reloads:** Since we cannot force the *running* agent process to reload memory, the `restore` command must output a standardized "Action Required" message (e.g., `\n> 🔄 State restored. Please run /clear or restart session to apply context changes.`).

## 3. Implementation Plan

### Step 1: Core Refactor (`lib/core`)
1.  Create `RewindController.js`: The API surface.
2.  Refactor `CheckpointEngine.js` to `CheckpointStore.js`:
    *   Implement "Fast Scan" logic.
    *   Implement `getDiffSummary(checkpointA, checkpointB)`.
3.  Refactor `ConversationTruncator` + `Metadata` into `ContextManager.js`.

### Step 2: Hook Optimization (`lib/hooks`)
1.  Create `HookHandler.js`:
    *   Handles `pre-tool-use`, `post-bash`, etc.
    *   Implements the "Anti-Spam" / Debounce logic internally.
    *   Reads `rewind-checkpoint-ignore.json` directly.
2.  Simplify `bin/smart-checkpoint.sh` to just: `exec node "$LIB/hooks/entry.js" "$@"`

### Step 3: The UI (`bin/rewind.js`)
1.  Implement **Interactive Mode**:
    *   List checkpoints with rich metadata: `[Time] [User Prompt] [Files Changed]`
    *   Use `enquirer` or `prompts` (or simple raw readline for zero-dep) for selection.
2.  Implement `restore` with modes:
    *   `--mode both` (Default): Atomic restore of both.
    *   `--mode code`: Files only (current behavior).
    *   `--mode context`: JSONL truncate only (experimental).

### Step 4: Verification
1.  **Unit Tests:** Mock file system for `CheckpointStore`.
2.  **Integration Test:**
    *   Start dummy session (create JSONL).
    *   Trigger hook (create checkpoint).
    *   Modify files.
    *   Run `rewind restore`.
    *   Verify files *and* JSONL content.

## 4. Directory Structure (Revised)
```text
rewind/
├── bin/
│   ├── rewind.js           # CLI entry point (User facing)
│   ├── hook-runner.js      # Hook entry point (System facing)
│   └── install-hooks.sh    # Installer
├── lib/
│   ├── core/
│   │   ├── RewindController.js  # Coordinator
│   │   ├── CheckpointStore.js   # File system snapshots
│   │   ├── ContextManager.js    # Conversation JSONL handling
│   │   └── ConfigLoader.js      # Centralized config
│   ├── hooks/
│   │   └── HookHandler.js       # Logic for "Should I checkpoint?"
│   └── utils/
│       └── fs-utils.js          # Atomic writes, safe scanning
└── configs/                    # Default tier configs
```

This architecture is cleaner, separates concerns, handles the missing "Context" piece, and optimizes performance by moving logic out of bash.
