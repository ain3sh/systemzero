# Python Rewrite Specification: System Zero Rewind

## Problem Statement
The current JS implementation fails in hook contexts because `node` (installed via nvm) is not in the subprocess PATH. Rather than patching this, we're doing a full Python rewrite for long-term stability and cross-system compatibility.

## Architecture

### New Directory Structure
```
rewind/
├── bin/
│   └── rewind                    # Entry point (#!/usr/bin/env python3)
├── rewind/                       # Python package
│   ├── __init__.py               # Version, package metadata
│   ├── cli.py                    # CLI commands (argparse)
│   ├── hooks/
│   │   ├── __init__.py
│   │   ├── handler.py            # Hook decision logic
│   │   ├── types.py              # Hook input dataclasses (borrowed from ~/.factory/hooks)
│   │   └── io.py                 # Hook I/O helpers (borrowed from ~/.factory/hooks)
│   ├── core/
│   │   ├── __init__.py
│   │   ├── controller.py         # RewindController - main orchestrator
│   │   ├── checkpoint_store.py   # File snapshots via tarfile
│   │   └── context_manager.py    # JSONL conversation tracking
│   ├── config/
│   │   ├── __init__.py
│   │   ├── loader.py             # Config file discovery/loading
│   │   └── schemas.py            # Config dataclasses (tiers, ignores)
│   └── utils/
│       ├── __init__.py
│       ├── fs.py                 # Atomic writes, path helpers
│       └── env.py                # Environment detection (borrowed from ~/.factory/hooks)
├── hooks/
│   ├── smart-checkpoint          # Minimal shell shim → python3 -m rewind.hooks
│   ├── balanced-hooks.json       # Hook registration templates
│   ├── aggressive-hooks.json
│   └── minimal-hooks.json
├── configs/
│   ├── balanced-tier.json
│   ├── aggressive-tier.json
│   ├── minimal-tier.json
│   └── rewind-checkpoint-ignore.json
├── install.sh                    # Updated for Python
├── pyproject.toml                # Modern Python packaging
└── tests/
    ├── test_checkpoint_store.py
    ├── test_context_manager.py
    └── test_hooks.py
```

## Components to Port

### 1. Hook System (Priority: Critical)
**Current**: `smart-checkpoint.sh` → `hook-runner.js` → `HookHandler.js`
**New**: `hooks/smart-checkpoint` → `python3 -m rewind.hooks <action>`

Key changes:
- Borrow typed I/O from `~/.factory/hooks/utils/` (proven, working)
- **Fix hook protocol**: No stdout for PreToolUse (just exit 0), only emit for SessionStart context
- Proper exit codes: 0=allow, 2=block+stderr, 1=error
- Handle all hook events: `session-start`, `pre-tool-use`, `post-bash`, `stop`

### 2. Checkpoint Store
**Current**: `CheckpointStore.js` using child_process tar
**New**: `checkpoint_store.py` using Python's `tarfile` module

Key changes:
- Native Python tarfile (no subprocess spawn)
- Add streaming extraction for large projects
- Preserve all functionality: save, restore, list, delete, prune

### 3. Context Manager
**Current**: `ContextManager.js` - JSONL conversation tracking
**New**: `context_manager.py` - Same format, Python implementation

Key changes:
- Streaming JSONL read/write (memory efficient)
- Same truncation logic for long contexts
- Add session isolation

### 4. Controller
**Current**: `RewindController.js` - Orchestrates store + context
**New**: `controller.py` - Same responsibility

Features to preserve:
- Dual storage modes (project/global)
- Atomic checkpoint creation
- Restore with optional code-only/context-only
- Undo (restore to previous + delete current)
- System validation

### 5. Config System
**Current**: `ConfigLoader.js` + JSON config files
**New**: `config/loader.py` + `config/schemas.py`

Config files (preserve as-is):
- `~/.rewind/config.json` - Global settings
- `.rewind/config.json` - Project settings
- Tier configs: balanced, aggressive, minimal

### 6. CLI
**Current**: `rewind.js` with custom arg parsing
**New**: `cli.py` with argparse

Commands to preserve:
- `rewind init [--mode project|global]`
- `rewind save [description]`
- `rewind list`
- `rewind restore <checkpoint> [--code-only|--context-only]`
- `rewind undo`
- `rewind status`
- `rewind validate`
- `rewind diff <checkpoint1> [checkpoint2]`

## Improvements to Integrate

### A. Performance Optimizations
1. **Lazy loading** - Don't import everything on hook invocation
2. **mmap for hashing** - Faster file change detection for large files
3. **Compiled ignore patterns** - Parse gitignore-style patterns once, reuse
4. **Metadata caching** - Cache checkpoint list in memory during session

### B. Correctness Fixes
1. **Proper hook protocol** - Fix stdout/stderr/exit code semantics
2. **Atomic operations** - Use tempfile + rename pattern everywhere
3. **Race condition handling** - File locking for concurrent access
4. **Clean error handling** - Typed exceptions, proper stack traces in debug mode

### C. New Features
1. **`--dry-run` flag** - Preview what would be checkpointed/restored
2. **`rewind gc`** - Garbage collect orphaned checkpoints
3. **Checkpoint tagging** - `rewind save --tag "before-refactor"`
4. **Better diff output** - Colored diff, file-by-file summary

### D. Developer Experience
1. **Debug mode** - `REWIND_DEBUG=1` for verbose logging
2. **Structured logging** - JSON logs for machine parsing
3. **Shell completions** - Bash/Zsh completions for CLI

## Dependencies
**Zero external dependencies** - Python 3.9+ stdlib only:
- `tarfile` - Archive creation/extraction
- `json` - Config and context files
- `pathlib` - Path operations
- `dataclasses` - Typed structures
- `argparse` - CLI parsing
- `hashlib` - File hashing for change detection
- `tempfile` - Atomic writes
- `shutil` - File operations
- `datetime` - Timestamps
- `os`, `sys` - Environment

## Installation Changes
- Remove node/npm checks
- Add Python 3.9+ version check
- Install to `~/.rewind/system/` (same location)
- Update PATH instructions for `~/.local/bin/rewind`

## Testing Strategy
1. **Unit tests** - pytest for core modules
2. **Integration tests** - Port existing v3-suite.js and integration-test.js
3. **Hook tests** - Mock stdin/stdout for hook I/O testing

## Migration Path
1. Create new `rewind-py/` directory alongside existing code
2. Implement and test incrementally
3. Update install.sh to use Python version
4. Keep JS version for reference, remove after validation

## Estimated Effort
- **Hook system**: ~200 lines (borrow from ~/.factory/hooks)
- **Checkpoint store**: ~300 lines
- **Context manager**: ~200 lines
- **Controller**: ~400 lines
- **Config**: ~150 lines
- **CLI**: ~300 lines
- **Utils**: ~100 lines
- **Tests**: ~400 lines
- **Total**: ~2000 lines Python (vs ~1500 lines JS)

## Success Criteria
1. All existing CLI commands work identically
2. Hooks work reliably in Droid/Claude Code subprocess environment
3. Zero external dependencies
4. All existing tests pass (ported to pytest)
5. No regression in checkpoint/restore performance