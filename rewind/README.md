# System Zero Rewind ⏪

> **Seamless, atomic checkpointing for AI coding agents.**  
> Instantly roll back mistakes—both code AND conversation context—without leaving your flow.

## 🚀 Install

One command. No dependencies (except Node.js + jq).

```bash
curl -fsSL https://raw.githubusercontent.com/ain3sh/systemzero/main/rewind/install.sh | bash
```

This will:
1.  Install the rewind engine to `~/.rewind/system`.
2.  Link the `rewind` command to `~/.local/bin/rewind`.
3.  Register hooks in Claude/Droid settings.
4.  Ask if you prefer **Project** (default) or **Global** storage.

---

## ✨ Usage

Once installed, **you don't need to do anything.** Checkpoints happen automatically when your agent makes edits.

### 1. Just Work
Use Claude or Droid as normal.
> "Refactor the authentication logic."

The system automatically snapshots code + context before changes are applied.

### 2. Undo a mistake
If the agent goes off the rails:
```bash
rewind undo
```

### 3. Restore a specific point
```bash
rewind list
rewind restore <name> --mode both
```
*(Modes: `both` [default], `code`, `context`)*

---

## 🛠 Configuration

### Storage Modes
Rewind supports two storage strategies. The installer sets your default, but you can switch per-project.

1.  **Project Mode** (Default)
    *   Checkpoints stored in `<project>/.rewind/`
    *   Portable with the repo.
    *   Best for: Self-contained projects.

2.  **Global Mode**
    *   Checkpoints stored in `~/.rewind/storage/<project_hash>/`
    *   Keeps your project directory clean.
    *   Best for: Sensitive/Work repos where you can't add folders.

**Switching Modes:**
No need to edit files manually.
```bash
cd my-project
rewind init --mode global
```

### Settings
View or edit configuration:
```bash
rewind config
rewind config antiSpam.minIntervalSeconds 60
```

---

## 🤖 Supported Agents
- **Claude Code**: Full support (hooks + context).
- **Droid CLI**: Full support.

## 🏗 Architecture
System Zero Rewind separates **Execution** (the tool) from **State** (the data).
- **Engine**: Global (`~/.rewind/system`). Updates independently of your projects.
- **Hooks**: Lightweight shims pointing to the global engine.
- **Data**: Local or Global, your choice.

## License
MIT
