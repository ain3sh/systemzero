# System Zero Rewind: v3 "Seamless" Architecture

You are absolutely right. The current requirement to "run an installer" for every project to get isolation is a failure of systems design. We need to decouple **Execution** (the tool) from **State** (the checkpoints).

## The UX Problem
Currently, the user conflates "Installing the tool" with "Configuring where data lives".
- **Current State**: To store data locally, users feel they must "install" the tool locally (vendoring).
- **Desired State**: Install the tool **ONCE** (globally). It automatically detects the project context and stores data locally by default. Zero setup per project.

## The "Works Backwards" Solution

### 1. One-Time Global Install
The user runs the installer **once** on their machine.
```bash
./install.sh
```
**System Actions:**
1.  Installs the engine/CLI to `~/.rewind/system/`.
2.  Symlinks `rewind` to `~/.local/bin/rewind` (or equivalent PATH).
3.  Registers **Global Hooks** in Claude/Droid settings (`~/.claude/settings.json`).

### 2. Zero-Setup Usage (Default Flow)
The user creates a new directory and just starts working.
```bash
mkdir my-new-project && cd my-new-project
claude
> "Create a generic hello world"
```
**System Logic:**
1.  Global hook fires.
2.  Hook checks for project-level config. None found.
3.  Hook falls back to **Default Mode**: `PROJECT_STORAGE`.
4.  System automatically creates `.rewind/` in `my-new-project/`.
**User Experience:** It just works. No `rewind init`, no scripts to run.

### 3. The `rewind init` Command (Optional Overrides)
If the user *wants* specific behavior for a project (e.g., "Store this project's history globally" or "Vendor the tool for CI"), they use the CLI.

```bash
cd my-secure-project
rewind init --mode global
```
**System Actions:**
- Creates `.rewind/config.json` with `{ "storage": "global" }`.
- Future snapshots for this project go to `~/.rewind/storage/...`.

### 4. Vendoring (The "Self-Contained" Edge Case)
If a team *must* ship the rewind engine with the repo (so it works in CI or for version locking):
```bash
rewind vendor
```
**System Actions:**
- Copies the engine to `.rewind/system/`.
- Outputs instructions: "To enable these vendored hooks, run: `rewind register-local`".
*(Note: We cannot automatically enable local hooks for security reasons—agents shouldn't blindly execute code found in a cloned repo).*

## Implementation Plan (Refactoring for v3)

1.  **Unified Installer (`install.sh`)**: 
    - Replaces `install-hooks.sh`. 
    - Focuses on Global Install + PATH registration.
    - Prompts for default preference: "Where should checkpoints live by default? [Project/Global]".

2.  **Smart Runtime (`ConfigLoader` 2.0)**:
    - Already implemented but needs to become the "Brain".
    - Logic: `Local Config` > `Global Config` > `Hardcoded Defaults`.

3.  **CLI Enhancements**:
    - `rewind config`: Read/Write global/local configs easily.
    - `rewind init`: scaffolding for new projects.
    - `rewind status`: Explicitly show "Using Global Binary -> Local Storage".

4.  **Symlink Management**:
    - Ensure `rewind` is a first-class citizen in the shell.

This architecture solves the friction: **Install once, run anywhere.**

## Confirmation
Shall I proceed with refactoring the installer and CLI to support this **"Install Once, Run Everywhere"** model? This will deprecate the confusing `--project` flag in the installer in favor of runtime configuration.