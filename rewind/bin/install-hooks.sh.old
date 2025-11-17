#!/bin/bash
# install-hooks.sh
# Install checkpoint hooks for Claude Code and/or Droid CLI
#
# Usage: install-hooks.sh [--dry-run] [tier]
#   tier: minimal, balanced (default), aggressive

set -euo pipefail

# Configuration
TIER="balanced"
DRY_RUN=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        minimal|balanced|aggressive)
            TIER="$1"
            shift
            ;;
        *)
            echo "Usage: $0 [--dry-run] [minimal|balanced|aggressive]" >&2
            exit 1
            ;;
    esac
done

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔧 Checkpoint/Rewind Hook Installer"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Tier: $TIER"
[[ "$DRY_RUN" == "true" ]] && echo "Mode: DRY RUN (no changes will be made)"
echo ""

# Check prerequisites
echo "Checking prerequisites..."

if ! command -v node &>/dev/null; then
    echo "❌ Node.js not found. Please install Node.js first." >&2
    exit 1
fi
echo "✓ Node.js: $(node --version)"

if ! command -v jq &>/dev/null; then
    echo "❌ jq not found. Please install jq first (sudo apt install jq)" >&2
    exit 1
fi
echo "✓ jq: $(jq --version)"

if ! command -v claudepoint &>/dev/null; then
    echo "⚠️  ClaudePoint not found. Install with: npm install -g claudepoint"
    echo "   (Installation will continue, but checkpoints won't work without it)"
fi

echo ""

# Detect available agents
echo "Detecting AI coding agents..."
AGENTS=()

if [[ -d "$HOME/.claude" ]]; then
    AGENTS+=("claude-code")
    echo "✓ Claude Code detected"
fi

if [[ -d "$HOME/.factory" ]]; then
    AGENTS+=("droid-cli")
    echo "✓ Droid CLI detected"
fi

if [[ ${#AGENTS[@]} -eq 0 ]]; then
    echo "❌ No compatible agents found (Claude Code or Droid CLI)" >&2
    exit 1
fi

echo ""

# Install files function
install_files() {
    echo "Installing checkpoint system files..."
    
    # Create directories
    if [[ "$DRY_RUN" == "false" ]]; then
        mkdir -p "$HOME/.local/bin"
        mkdir -p "$HOME/.local/lib/checkpoint-rewind/parsers"
        mkdir -p "$HOME/.local/lib/checkpoint-rewind/metadata"
        mkdir -p "$HOME/.claude-checkpoints"
        mkdir -p "$HOME/.factory-checkpoints"
    else
        echo "[DRY RUN] Would create directories:"
        echo "  - $HOME/.local/bin"
        echo "  - $HOME/.local/lib/checkpoint-rewind/{parsers,metadata}"
        echo "  - $HOME/.claude-checkpoints"
        echo "  - $HOME/.factory-checkpoints"
    fi
    
    # Copy main script
    if [[ "$DRY_RUN" == "false" ]]; then
        cp "$SCRIPT_DIR/smart-checkpoint.sh" "$HOME/.local/bin/"
        chmod +x "$HOME/.local/bin/smart-checkpoint.sh"
        echo "✓ Installed smart-checkpoint.sh to ~/.local/bin/"
    else
        echo "[DRY RUN] Would copy: smart-checkpoint.sh → ~/.local/bin/"
    fi
    
    # Copy Node.js modules
    if [[ "$DRY_RUN" == "false" ]]; then
        cp "$PROJECT_ROOT/lib/parsers/SessionParser.js" "$HOME/.local/lib/checkpoint-rewind/parsers/"
        cp "$PROJECT_ROOT/lib/metadata/ConversationMetadata.js" "$HOME/.local/lib/checkpoint-rewind/metadata/"
        echo "✓ Installed Node.js modules to ~/.local/lib/checkpoint-rewind/"
    else
        echo "[DRY RUN] Would copy:"
        echo "  - SessionParser.js → ~/.local/lib/checkpoint-rewind/parsers/"
        echo "  - ConversationMetadata.js → ~/.local/lib/checkpoint-rewind/metadata/"
    fi
    
    echo ""
}

# Update settings for an agent
update_agent_settings() {
    local agent="$1"
    local settings_file=""
    
    case "$agent" in
        claude-code)
            settings_file="$HOME/.claude/settings.json"
            ;;
        droid-cli)
            settings_file="$HOME/.factory/settings.json"
            ;;
    esac
    
    echo "Configuring hooks for $agent..."
    echo "Settings file: $settings_file"
    
    # Backup existing settings
    if [[ -f "$settings_file" ]]; then
        local backup_file="${settings_file}.backup.$(date +%s)"
        if [[ "$DRY_RUN" == "false" ]]; then
            cp "$settings_file" "$backup_file"
            echo "✓ Backed up existing settings to: $backup_file"
        else
            echo "[DRY RUN] Would backup to: $backup_file"
        fi
    else
        echo "  No existing settings.json found"
    fi
    
    # Create new settings with hooks
    local new_settings
    if [[ -f "$settings_file" ]]; then
        # Merge with existing settings (strip comments first - Droid uses JSON with comments)
        local existing_json=$(grep -v '^\s*//' "$settings_file" | grep -v '^\s*#')
        new_settings=$(echo "$existing_json" | jq '. + {
  "hooks": {
    "PreToolUse": [{
      "matcher": "Edit|Write|NotebookEdit",
      "hooks": [{
        "type": "command",
        "command": "bash",
        "args": ["-c", "~/.local/bin/smart-checkpoint.sh pre-tool-use"],
        "timeout": 10
      }]
    }],
    "SessionStart": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "bash",
        "args": ["-c", "~/.local/bin/smart-checkpoint.sh session-start"],
        "timeout": 5
      }]
    }]
  }
}')
    else
        # Create new settings file
        new_settings='{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Edit|Write|NotebookEdit",
      "hooks": [{
        "type": "command",
        "command": "bash",
        "args": ["-c", "~/.local/bin/smart-checkpoint.sh pre-tool-use"],
        "timeout": 10
      }]
    }],
    "SessionStart": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "bash",
        "args": ["-c", "~/.local/bin/smart-checkpoint.sh session-start"],
        "timeout": 5
      }]
    }]
  }
}'
    fi
    
    # Validate JSON
    if ! echo "$new_settings" | jq empty 2>/dev/null; then
        echo "❌ ERROR: Generated invalid JSON for $agent settings" >&2
        return 1
    fi
    
    # Write new settings
    if [[ "$DRY_RUN" == "false" ]]; then
        echo "$new_settings" > "$settings_file"
        echo "✓ Updated hooks in $settings_file"
    else
        echo "[DRY RUN] Would write new settings with hooks"
    fi
    
    echo ""
}

# Install files
install_files

# Update each agent
for agent in "${AGENTS[@]}"; do
    update_agent_settings "$agent"
done

# Print completion message
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ "$DRY_RUN" == "true" ]]; then
    echo "✓ Dry run complete - no changes made"
else
    echo "✅ Installation complete!"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [[ "$DRY_RUN" == "false" ]]; then
    echo "Next steps:"
    echo "  1. Restart your agent:"
    for agent in "${AGENTS[@]}"; do
        case "$agent" in
            claude-code)
                echo "     • Exit and restart Claude Code"
                ;;
            droid-cli)
                echo "     • Exit and restart Droid CLI"
                ;;
        esac
    done
    echo ""
    echo "  2. Test automatic checkpointing:"
    echo "     cd ~/test-project"
    echo "     claude  # (or droid)"
    echo "     # Make a code change (create/edit file)"
    echo "     # Exit agent"
    echo "     claudepoint list  # Should see 'Auto: Before Write/Edit' checkpoint"
    echo ""
    echo "  3. Check conversation metadata:"
    echo "     cat ~/test-project/.claudepoint/conversation_metadata.json | jq"
    echo ""
    echo "Installed for: ${AGENTS[*]}"
    echo "Tier: $TIER"
else
    echo "Run without --dry-run to actually install."
fi
echo ""
