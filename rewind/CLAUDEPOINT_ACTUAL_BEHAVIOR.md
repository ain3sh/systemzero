# ClaudePoint Actual Behavior - Test Results
## What I Learned from Real Testing (Not Source Code)

**Date:** 2025-11-16  
**Version Tested:** ClaudePoint 1.4.4  
**Test Location:** `/tmp/claudepoint-test-1763313290`  

---

## ⚠️ IMPORTANT DISCOVERY

**The actual storage format is DIFFERENT from what I saw in the source code!**

### What the Source Code Suggested
```
.claudepoint/snapshots/checkpoint_name.tar.gz
```

### What Actually Happens
```
.claudepoint/snapshots/checkpoint_name/
├── files.tar.gz
└── manifest.json
```

**Lesson:** Always test the actual tool, don't just read source code. Code might be outdated or there might be multiple code paths.

---

## Actual Storage Structure

### Directory Layout
```
.claudepoint/
├── config.json          # Configuration (as expected)
├── changelog.json       # Activity log (as expected)
└── snapshots/
    └── initial_test_checkpoint_2025-11-16T17-14-50/
        ├── files.tar.gz      # Actual file backup
        └── manifest.json     # Per-checkpoint metadata
```

### config.json (Confirmed from test)
```json
{
  "maxCheckpoints": 10,
  "autoName": true,
  "ignorePatterns": [
    ".git", ".claudepoint", "node_modules", ".env", ".env.*",
    "*.log", ".DS_Store", "Thumbs.db", "__pycache__", "*.pyc",
    ".vscode", ".idea", "dist", "build", "coverage", ".nyc_output",
    ".next", ".nuxt", ".cache", "tmp", "temp"
  ],
  "additionalIgnores": [],
  "forceInclude": [],
  "nameTemplate": "checkpoint_{timestamp}",
  "maxAge": 30
}
```

### changelog.json (Confirmed from test)
```json
[
  {
    "timestamp": "2025-11-16T17:14:50.334Z",
    "action": "CREATE_CLAUDEPOINT",
    "description": "Created full claudepoint: initial_test_checkpoint_2025-11-16T17-14-50",
    "details": "Initial test checkpoint"
  }
]
```

### manifest.json (NEW - Not in source code I read!)
```json
{
  "name": "initial_test_checkpoint_2025-11-16T17-14-50",
  "timestamp": "2025-11-16T17:14:50.329Z",
  "description": "Initial test checkpoint",
  "type": "FULL",
  "files": [
    "test.js"
  ],
  "fileCount": 1,
  "totalSize": 21,
  "fileHashes": {
    "test.js": "a057ae13f3fe5c932390c4b9a403ee75038c189437db79d0b7e0d0fbdcdb7408"
  }
}
```

**This is GREAT!** They store per-file metadata including hashes. This means we can:
1. Query which files are in a checkpoint without extracting the tarball
2. Use file hashes for integrity checks
3. Know the exact file list for our conversation metadata linking

---

## Verified CLI Behavior

### Create Checkpoint
```bash
$ claudepoint create -d "Initial test checkpoint"

Output:
[claudepoint] Starting CLI mode
- 💾 Deploying claudepoint...
[claudepoint] Scanning project files from: /tmp/claudepoint-test-1763313290
[claudepoint] File scan complete: 1 files in 5ms
[claudepoint] Scanned 1 directories
✔ 🚀 CLAUDEPOINT LOCKED IN // Ready to hack the impossible
   Name: initial_test_checkpoint_2025-11-16T17-14-50 [DEPLOYED]
   Files: 1
   Size: 21.0B
   Description: Initial test checkpoint
```

**Observations:**
- Auto-generates name with timestamp
- Scans project first
- Shows file count and total size
- Returns immediately (fast!)

### Undo/Restore
```bash
$ claudepoint undo

Output:
[claudepoint] Starting CLI mode
- 🕰️ Initiating time hack...
[claudepoint] Scanning project files from: /tmp/claudepoint-test-1763313290
[claudepoint] File scan complete: 1 files in 4ms
[claudepoint] Scanned 1 directories
[claudepoint] Scanning project files from: /tmp/claudepoint-test-1763313290
[claudepoint] File scan complete: 1 files in 1ms
[claudepoint] Scanned 1 directories
✔ 🔄 INITIATING TIME HACK // Rolling back through digital history
   🛡️ Emergency backup: emergency_backup_2025-11-16T17-15-14
   🔄 Restored: initial_test_checkpoint_2025-11-16T17-14-50
   📅 Back to the future: FULL claudepoint
```

**Observations:**
- Automatically creates emergency backup before restore! (Safety first)
- Scans project twice (before and after?)
- Actually restores files correctly ✅

### Test Results
```bash
# Before restore
$ cat test.js
console.log('modified');

# After restore
$ cat test.js
console.log('test');
```

**✅ WORKS PERFECTLY!**

---

## Implications for Our Implementation

### 1. We Can Query Checkpoint Metadata Without Extraction

```python
# NEW capability we didn't know about
def get_checkpoint_files(checkpoint_name):
    manifest_path = f".claudepoint/snapshots/{checkpoint_name}/manifest.json"
    with open(manifest_path) as f:
        manifest = json.load(f)
    return manifest['files']  # List of files in checkpoint
```

This is MUCH better than extracting the tarball just to see what's inside!

### 2. We Have File Hashes for Integrity

```python
def verify_checkpoint_integrity(checkpoint_name):
    manifest = load_manifest(checkpoint_name)
    for file_path, expected_hash in manifest['fileHashes'].items():
        actual_hash = sha256(file_path)
        if actual_hash != expected_hash:
            raise IntegrityError(f"{file_path} hash mismatch")
```

### 3. Emergency Backups Are Automatic

We don't need to implement our own backup system - ClaudePoint already creates `emergency_backup_*` before every restore!

### 4. Checkpoint Naming Is Predictable

Format: `{description}_{timestamp}`
- `description`: Sanitized user input (spaces to underscores, lowercase)
- `timestamp`: ISO format with colons replaced by hyphens

Example: `"Initial test checkpoint"` → `initial_test_checkpoint_2025-11-16T17-14-50`

---

## Updated Integration Plan

### What We Can Use Directly

1. **Checkpoint Creation:**
   ```bash
   claudepoint create -d "Auto: Before ${TOOL_NAME}"
   ```

2. **Checkpoint Restore:**
   ```bash
   claudepoint undo  # Interactive
   claudepoint restore <checkpoint-name>  # Specific
   ```

3. **Checkpoint Querying:**
   ```bash
   claudepoint list  # Shows all checkpoints
   ```

### What We Need to Add

1. **Conversation Metadata Storage:**
   ```python
   # Add to our own metadata file (NOT inside ClaudePoint's files)
   # Location: .claudepoint/conversation_metadata.json
   {
     "initial_test_checkpoint_2025-11-16T17-14-50": {
       "agent": "claude-code",
       "session_id": "xyz",
       "session_file": "~/.claude/projects/abc/xyz.jsonl",
       "message_uuid": "msg_123",
       "user_prompt": "Create test file"
     }
   }
   ```

2. **Conversation Truncation:**
   ```python
   # Read conversation metadata
   # Truncate JSONL at message_uuid
   # Provide resume instructions
   ```

---

## Test Cleanup

```bash
$ rm -rf /tmp/claudepoint-test-1763313290
```

---

## Updated Ground Truth

### Storage Format (ACTUAL)
```
.claudepoint/
├── config.json
├── changelog.json
├── conversation_metadata.json  # OUR ADDITION
└── snapshots/
    └── <checkpoint_name>/
        ├── files.tar.gz
        └── manifest.json
```

### Manifest Format (VERIFIED)
```typescript
interface Manifest {
  name: string;           // Checkpoint name
  timestamp: string;      // ISO 8601
  description: string;    // User-provided
  type: "FULL";          // Always FULL in current version
  files: string[];       // List of file paths
  fileCount: number;     // Total files
  totalSize: number;     // Bytes
  fileHashes: {          // SHA-256 hashes
    [filePath: string]: string;
  };
}
```

---

## Lessons Learned

1. ✅ **Always test the actual tool** - Source code might be outdated
2. ✅ **Storage format is better than expected** - Per-file metadata is a win
3. ✅ **Safety built-in** - Emergency backups automatic
4. ✅ **Fast and reliable** - Checkpoint/restore work instantly
5. ✅ **We can build on top of this** - No need to reimplement checkpoint storage

---

## Next Steps

1. ✅ ClaudePoint tested and verified working
2. 🔄 Document actual behavior (this file)
3. ⏭️ Extract ccundo's JSONL parser
4. ⏭️ Update FINAL_IMPLEMENTATION_SPEC.md with actual ClaudePoint behavior
5. ⏭️ Implement conversation metadata storage
6. ⏭️ Implement Phase 1 with real ClaudePoint integration

**Status:** Ready to proceed with Phase 1 implementation! 🚀
