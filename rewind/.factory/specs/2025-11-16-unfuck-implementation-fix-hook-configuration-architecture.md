# Spec: Unfuck the Checkpoint/Rewind Implementation

## 🎯 **THE CORE PROBLEM**

The intern confused **WHAT** goes in `settings.json` (hook registration) vs **WHAT** goes in `configs/` (tier parameters for the hook script).

### **What's Wrong:**

1. **Configs are HYBRID MONSTERS** 🧟
   - `configs/*.json` files contain BOTH:
     - ✅ Hook registrations (belongs in settings.json)
     - ✅ Tier parameters (belongs in script config)
   - These get COPIED DIRECTLY to `~/.claude/settings.json` by installer
   - But `smart-checkpoint.sh` ALSO tries to read them for parameters!
   - **Result:** Confusion about source of truth

2. **Install Script Does the WRONG Thing** 🔥
   - Copies entire `configs/balanced.json` → `~/.claude/settings.json`
   - Includes `antiSpam`/`significance` fields that Claude Code IGNORES
   - Should only copy the `hooks` object!

3. **Missing Actual Hook Format** 📋
   - Configs use simplified format: `"PreToolUse": true` 
   - But actual hooks need: `matcher`, `hooks[]`, `type`, `command`, `args`
   - The examples in `claude-hooks-examples/` are CORRECT format
   - The configs in `configs/` are WRONG format

## ✅ **THE FIX (Clean Architecture)**

### **File Responsibilities:**

```
┌─────────────────────────────────────────────────────┐
│ ~/.claude/settings.json (OR ~/.factory/settings.json)│
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│ PURPOSE: Hook registration (Claude/Droid reads this) │
│                                                       │
│ {                                                     │
│   "hooks": {                                          │
│     "PreToolUse": [{                                  │
│       "matcher": "Edit|Write",                        │
│       "hooks": [{                                     │
│         "type": "command",                            │
│         "command": "bash",                            │
│         "args": ["-c", "~/.local/bin/smart..."]      │
│       }]                                              │
│     }]                                                │
│   }                                                   │
│ }                                                     │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ ~/.config/checkpoint-rewind/tiers/balanced.json      │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│ PURPOSE: Tier parameters (script reads this)         │
│                                                       │
│ {                                                     │
│   "tier": "balanced",                                 │
│   "antiSpam": {                                       │
│     "enabled": true,                                  │
│     "minIntervalSeconds": 30                          │
│   },                                                  │
│   "significance": {                                   │
│     "enabled": true,                                  │
│     "minChangeSize": 50                               │
│   }                                                   │
│ }                                                     │
│ NO HOOKS FIELD!                                       │
└─────────────────────────────────────────────────────┘
```

---

## 🛠️ **IMPLEMENTATION PLAN**

### **Phase 1: Restructure Config Files (30 min)**

#### **1.1: Create NEW Hook Templates**

Create `hooks/` directory with PROPER hook JSON:

```
hooks/
├── minimal-hooks.json      # Hook registration only
├── balanced-hooks.json     # Hook registration only  
├── aggressive-hooks.json   # Hook registration only
└── README.md               # Explains format
```

**Content of `hooks/balanced-hooks.json`:**
```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Edit|Write|NotebookEdit",
      "hooks": [{
        "type": "command",
        "command": "bash",
        "args": ["-c", "~/.local/bin/smart-checkpoint.sh pre-modify \"$TOOL_NAME\" \"$SESSION_ID\""],
        "timeout": 10
      }]
    }],
    "SessionStart": [{
      "hooks": [{
        "type": "command",
        "command": "bash",
        "args": ["-c", "~/.local/bin/smart-checkpoint.sh session-start \"$SESSION_ID\""],
        "timeout": 5
      }]
    }]
  }
}
```

**Use `claude-hooks-examples/` as template** - they're already correct!

#### **1.2: Fix Tier Config Files**

**Update `configs/balanced-tier.json`:**
```json
{
  "tier": "balanced",
  "description": "Smart checkpointing with 30s cooldown",
  "antiSpam": {
    "enabled": true,
    "minIntervalSeconds": 30
  },
  "significance": {
    "enabled": true,
    "minChangeSize": 50,
    "criticalFiles": [
      "package.json",
      "requirements.txt",
      "Dockerfile"
    ]
  }
}
```

**NO `hooks` FIELD** - tier configs are for script parameters only!

---

### **Phase 2: Fix Install Script (30 min)**

#### **2.1: Update `bin/install-hooks.sh`**

**OLD (WRONG):**
```bash
# Install tier configuration
cp "$CONFIG_DIR/tiers/${TIER}.json" "$SETTINGS_FILE"
```

**NEW (CORRECT):**
```bash
# Step 5: Install hooks for each agent
for agent in "${AGENTS[@]}"; do
    case "$agent" in
        claude-code)
            SETTINGS_FILE="$HOME/.claude/settings.json"
            HOOK_TEMPLATE="$SCRIPT_DIR/../hooks/${TIER}-hooks.json"
            ;;
        droid-cli)
            SETTINGS_FILE="$HOME/.factory/settings.json"
            HOOK_TEMPLATE="$SCRIPT_DIR/../hooks/${TIER}-hooks.json"
            ;;
    esac
    
    # Backup existing settings
    if [[ -f "$SETTINGS_FILE" ]]; then
        cp "$SETTINGS_FILE" "${SETTINGS_FILE}.backup.$(date +%s)"
    fi
    
    # Merge hooks with existing settings (or create new)
    if [[ -f "$SETTINGS_FILE" ]]; then
        # Merge: preserve existing settings, add/replace hooks
        jq -s '.[0] * .[1]' "$SETTINGS_FILE" "$HOOK_TEMPLATE" > "$SETTINGS_FILE.tmp"
        mv "$SETTINGS_FILE.tmp" "$SETTINGS_FILE"
    else
        # New file: just copy hook template
        cp "$HOOK_TEMPLATE" "$SETTINGS_FILE"
    fi
    
    echo "✅ Installed $TIER hooks for $agent"
done

# Step 6: Copy tier configs (separate from hooks!)
cp "$SCRIPT_DIR/../configs/"*-tier.json "$CONFIG_DIR/tiers/"
echo "✅ Tier configurations copied to $CONFIG_DIR/tiers/"
```

#### **2.2: Set CHECKPOINT_TIER Environment Variable**

**Add to install script:**
```bash
# Step 7: Set default tier in user's shell profile
SHELL_PROFILE="$HOME/.bashrc"
[[ -f "$HOME/.zshrc" ]] && SHELL_PROFILE="$HOME/.zshrc"

if ! grep -q "CHECKPOINT_TIER" "$SHELL_PROFILE"; then
    echo "" >> "$SHELL_PROFILE"
    echo "# Checkpoint/Rewind System" >> "$SHELL_PROFILE"
    echo "export CHECKPOINT_TIER=${TIER}" >> "$SHELL_PROFILE"
    echo "✅ Added CHECKPOINT_TIER to $SHELL_PROFILE"
fi
```

---

### **Phase 3: Fix smart-checkpoint.sh (30 min)**

#### **3.1: Update Config Loading**

**OLD (tries to load from wrong place):**
```bash
TIER_CONFIG="$CONFIG_DIR/tiers/$TIER.json"

if [[ -f "$TIER_CONFIG" ]]; then
    ANTI_SPAM_INTERVAL=$(jq -r '.antiSpam.minIntervalSeconds // 30' "$TIER_CONFIG")
    MIN_CHANGE_SIZE=$(jq -r '.significance.minChangeSize // 50' "$TIER_CONFIG")
```

**NEW (correct path and validation):**
```bash
# Get tier from environment or default to balanced
TIER="${CHECKPOINT_TIER:-balanced}"

# Construct config path
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/checkpoint-rewind"
TIER_CONFIG="$CONFIG_DIR/tiers/${TIER}-tier.json"

# Validate config exists
if [[ ! -f "$TIER_CONFIG" ]]; then
    echo "[smart-checkpoint] WARNING: Config not found: $TIER_CONFIG" >&2
    echo "[smart-checkpoint] Using default values (balanced tier)" >&2
    ANTI_SPAM_INTERVAL=30
    MIN_CHANGE_SIZE=50
else
    # Load from tier config
    if command -v jq &>/dev/null; then
        ANTI_SPAM_INTERVAL=$(jq -r '.antiSpam.minIntervalSeconds // 30' "$TIER_CONFIG")
        MIN_CHANGE_SIZE=$(jq -r '.significance.minChangeSize // 50' "$TIER_CONFIG")
    else
        echo "[smart-checkpoint] WARNING: jq not found, using defaults" >&2
        ANTI_SPAM_INTERVAL=30
        MIN_CHANGE_SIZE=50
    fi
fi
```

#### **3.2: Remove Hook Registration Logic**

**DELETE these sections** (hooks don't belong in tier configs):
```bash
# DELETE: No more reading hooks from tier config
# This was the confusion - hooks are in settings.json!
```

---

### **Phase 4: Move Node.js to Installed Location (20 min)**

#### **4.1: Fix Path References**

**Update `smart-checkpoint.sh`:**
```bash
# OLD (brittle - breaks if repo deleted):
SESSION_PARSER="$PROJECT_ROOT/lib/parsers/SessionParser.js"

# NEW (uses installed location):
SESSION_PARSER="$HOME/.local/lib/checkpoint-rewind/parsers/SessionParser.js"
METADATA_TOOL="$HOME/.local/lib/checkpoint-rewind/metadata/ConversationMetadata.js"
TRUNCATOR="$HOME/.local/lib/checkpoint-rewind/rewind/ConversationTruncator.js"
```

#### **4.2: Update Install Script to Copy JS Files**

```bash
# Copy Node.js modules to installed location
mkdir -p "$HOME/.local/lib/checkpoint-rewind/parsers"
mkdir -p "$HOME/.local/lib/checkpoint-rewind/metadata"
mkdir -p "$HOME/.local/lib/checkpoint-rewind/rewind"

cp "$PROJECT_ROOT/lib/parsers/SessionParser.js" \
   "$HOME/.local/lib/checkpoint-rewind/parsers/"

cp "$PROJECT_ROOT/lib/metadata/ConversationMetadata.js" \
   "$HOME/.local/lib/checkpoint-rewind/metadata/"

cp "$PROJECT_ROOT/lib/rewind/ConversationTruncator.js" \
   "$HOME/.local/lib/checkpoint-rewind/rewind/"

echo "✅ Installed Node.js modules"
```

---

### **Phase 5: Clean Up Orphaned Files (10 min)**

#### **5.1: Delete or Archive**

**Delete (not used):**
- `lib/parsers/ClaudeSessionParser.js` - Never imported
- `lib/parsers/Operation.js` - Never used
- `lib/adapters/` - Empty directory

**Keep but fix:**
- `lib/parsers/SessionParser.js` - Used by smart-checkpoint.sh
- `lib/metadata/ConversationMetadata.js` - Used by smart-checkpoint.sh
- `lib/rewind/ConversationTruncator.js` - Used by checkpoint-rewind-full.sh

---

### **Phase 6: Update Documentation (20 min)**

#### **6.1: Update FINAL_IMPLEMENTATION_SPEC.md**

**Section 1.1: Three-Tier Configuration Files**

Replace with:
```markdown
#### 1.1: Three-Tier Hook Configurations

**IMPORTANT:** Hooks are registered in `settings.json`, NOT in tier configs!

**File:** `hooks/minimal-hooks.json` (hook registration)
```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Write",
      "hooks": [{
        "type": "command",
        "command": "claudepoint",
        "args": ["create", "-d", "Auto: Before creating file"],
        "timeout": 5
      }]
    }]
  }
}
```

**File:** `configs/minimal-tier.json` (script parameters)
```json
{
  "tier": "minimal",
  "description": "Only checkpoint on file creation",
  "antiSpam": {"enabled": false},
  "significance": {"enabled": false}
}
```
```

---

## 📁 **NEW FILE STRUCTURE**

```
checkpoint-rewind/
├── bin/
│   ├── smart-checkpoint.sh              # Reads configs/
│   ├── install-hooks.sh                 # Writes to settings.json
│   └── checkpoint-rewind-full.sh
│
├── hooks/                                # ← NEW: Proper hook templates
│   ├── minimal-hooks.json               # Just hook registration
│   ├── balanced-hooks.json              # Just hook registration
│   ├── aggressive-hooks.json            # Just hook registration
│   └── README.md
│
├── configs/                              # ← FIXED: Script params only
│   ├── minimal-tier.json                # No "hooks" field!
│   ├── balanced-tier.json               # No "hooks" field!
│   ├── aggressive-tier.json             # No "hooks" field!
│   └── README.md
│
├── lib/
│   ├── parsers/
│   │   └── SessionParser.js             # KEEP (used)
│   ├── metadata/
│   │   └── ConversationMetadata.js      # KEEP (used)
│   └── rewind/
│       └── ConversationTruncator.js     # KEEP (used)
│
├── claude-hooks-examples/                # ← REFERENCE (already correct!)
│   ├── minimal-hooks.json
│   ├── balanced-hooks.json
│   └── aggressive-hooks.json
│
└── docs/
    ├── FINAL_IMPLEMENTATION_SPEC.md      # UPDATE
    └── ARCHITECTURE.md                   # NEW (explains separation)
```

---

## 🧪 **TESTING PLAN**

### **Test 1: Clean Install**
```bash
# Remove old installation
rm -rf ~/.claude-checkpoints ~/.config/checkpoint-rewind ~/.local/bin/smart-checkpoint.sh

# Fresh install
./bin/install-hooks.sh balanced

# Verify:
# 1. ~/.claude/settings.json has ONLY hooks (no antiSpam/significance)
# 2. ~/.config/checkpoint-rewind/tiers/ has tier configs
# 3. CHECKPOINT_TIER=balanced in .bashrc
```

### **Test 2: Hook Execution**
```bash
# Start Claude
claude

# Make a change
# Trigger: "Edit app.js"

# Verify:
# 1. Hook fires (check stderr output)
# 2. smart-checkpoint.sh reads ~/.config/checkpoint-rewind/tiers/balanced-tier.json
# 3. Checkpoint created with correct parameters
```

### **Test 3: Tier Switching**
```bash
# Change tier
export CHECKPOINT_TIER=aggressive

# Restart Claude
claude

# Verify:
# 1. Script loads aggressive-tier.json
# 2. 15s cooldown instead of 30s
# 3. Prompt analysis works
```

---

## ⚡ **MIGRATION GUIDE**

### **For Existing Users:**

```bash
# 1. Backup current setup
cp ~/.claude/settings.json ~/.claude/settings.json.pre-unfuck

# 2. Pull latest changes
cd ~/rewind
git pull

# 3. Re-run installer (it will detect and migrate)
./bin/install-hooks.sh balanced

# 4. Restart Claude
# Done!
```

---

## 🎯 **SUCCESS CRITERIA**

After this fix:

✅ **Clear separation of concerns:**
- `hooks/*.json` = Hook registration (for settings.json)
- `configs/*-tier.json` = Script parameters (for smart-checkpoint.sh)

✅ **Install script only writes hooks to settings.json:**
- No antiSpam/significance pollution
- Clean JSON structure

✅ **smart-checkpoint.sh reads tier configs correctly:**
- From `~/.config/checkpoint-rewind/tiers/`
- Via CHECKPOINT_TIER environment variable

✅ **Repos can be deleted after install:**
- All files copied to system locations
- No broken references to `$PROJECT_ROOT`

✅ **Documentation matches reality:**
- Examples show actual hook format
- Tier configs show actual parameters

---

## 📝 **SUMMARY**

**The Problem:** Intern mixed hook registration (settings.json) with script parameters (tier configs).

**The Solution:** Separate them completely:
- `hooks/` = What Claude/Droid reads (hook registration)
- `configs/` = What smart-checkpoint.sh reads (behavior params)

**The Win:** Clean architecture, no confusion, works as designed!