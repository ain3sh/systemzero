# System Zero Rewind: Dual-Mode Storage Guide

Rewind supports two distinct storage modes to accommodate different security and workflow requirements: **Project-Level** and **User-Level (Global)**.

This flexibility ensures that users who prefer not to have `.rewind` directories cluttering their source code (or for security reasons) can store checkpoints externally, while teams that want to commit configs or share checkpoints (via other means) can keep them local.

## 1. Project-Level Mode (Default)

This is the standard behavior, mirroring how systems like git work.

### How it works
- **Storage Location**: `<project-root>/.rewind/`
- **Contents**:
  - `code/snapshots/`: Tarballs of file states
  - `conversation/`: Metadata about agent conversations
  - `head_signature`: Fast-scan state tracking

### Usage Flow
1. **User**: Navigates to project folder.
2. **User**: Runs `rewind save "My feature"`.
3. **System**: Creates `.rewind` folder in the current directory.
4. **Result**: Checkpoints are self-contained within the project. If you move the project folder, the checkpoints go with it.

### Pros & Cons
- ✅ **Portable**: Moving the folder moves the history.
- ✅ **Transparent**: You see exactly where the data is.
- ❌ **Intrusive**: Adds a `.rewind` folder to your project (must be `.gitignore`'d).
- ❌ **Risk**: `rm -rf project` deletes the project AND its rewind history.

---

## 2. User-Level (Global) Mode

This mode stores checkpoints in a centralized directory in your home folder, keeping your source directories clean.

### Configuration
To enable global mode, create a user-level config file at `~/.rewind/config.json`:

```json
{
  "storage": {
    "mode": "global"
  }
}
```

(Or optionally set `"path": "/custom/secure/location"` if you want them elsewhere).

### How it works
- **Storage Location**: `~/.rewind/storage/<project_name>_<hash>/`
- **Mapping**: The system uniquely identifies projects by hashing their absolute path.
- **Contents**: Same structure as Project-Level, just externalized.

### Usage Flow
1. **User**: Selects "Global Mode" during installation (or runs `rewind init --mode global` later).
2. **User**: Navigates to ANY project folder.
3. **User**: Runs `rewind save`.
4. **System**: 
   - Calculates hash of current path (e.g., `/src/my-app` -> `my-app_a1b2c3...`).
   - Saves data to `~/.rewind/storage/my-app_a1b2c3...`.
5. **Result**: Source directory remains pristine. No `.rewind` folder appears.

### Pros & Cons
- ✅ **Clean**: No "foreign" code or folders in your project.
- ✅ **Safe**: Deleting the project folder does NOT delete the history (unduable!).
- ✅ **Secure**: Can map storage to an encrypted drive via `"path"`.
- ❌ **Fixed**: Moving the project folder breaks the link (hash changes).

---

## Comparison Table

| Feature | Project-Level (Default) | User-Level (Global) |
| :--- | :--- | :--- |
| **Setup** | Zero config required | Requires `~/.rewind/config.json` |
| **Directory Impact** | Creates `.rewind/` in project | Zero impact on project dir |
| **Portability** | Moves with project | Tied to absolute path |
| **Deletion Safety** | Deleted with project | Persists after project deletion |
| **Best For** | Ephemeral experiments, self-contained repos | Corporate environments, high-value code, strict folder policies |

## Switching Modes

You can switch modes at any time by changing the configuration. 

> ⚠️ **Note**: Checkpoints are NOT automatically migrated between modes. If you switch from Project to Global, `rewind list` will show an empty history for that project until you create new checkpoints in the new location.
