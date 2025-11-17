#!/bin/bash
# install-hooks.sh
# Install checkpoint hooks for Claude Code and/or Droid CLI
#
# Usage: install-hooks.sh [--dry-run] [--project] [tier]
#   --project: Install to project directories (.claude/hooks, .factory/hooks)
#              Default: Install to user directories (~/.claude/hooks, ~/.factory/hooks)
#   tier: minimal, balanced (default), aggressive

set -euo pipefail

# Configuration
TIER="balanced"
DRY_RUN=false
PROJECT_INSTALL=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --project)
            PROJECT_INSTALL=true
            shift
            ;;
        minimal|balanced|aggressive)
            TIER="$1"
            shift
            ;;
        *)
            echo "Usage: $0 [--dry-run] [--project] [minimal|balanced|aggressive]" >&2
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
echo "Scope: $([ "$PROJECT_INSTALL" == "true" ] && echo "PROJECT-LEVEL" || echo "USER-LEVEL")"
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

# Determine installation paths based on scope
if [[ "$PROJECT_INSTALL" == "true" ]]; then
    # Project-level install
    CLAUDE_HOOKS_DIR="./.claude/hooks"
    FACTORY_HOOKS_DIR="./.factory/hooks"
    LIB_BASE_DIR="./.checkpoint-rewind"
    CONFIG_DIR="./.checkpoint-rewind/tiers"
    # For JSON: need to escape the $ as \$ but bash will interpret it
    # So we use \\\$ which becomes \$ in the JSON string
    SCRIPT_PATH_VAR_CLAUDE="\\\$CLAUDE_PROJECT_DIR/.claude/hooks"
    SCRIPT_PATH_VAR_FACTORY="\\\$FACTORY_PROJECT_DIR/.factory/hooks"
else
    # User-level install
    CLAUDE_HOOKS_DIR="$HOME/.claude/hooks"
    FACTORY_HOOKS_DIR="$HOME/.factory/hooks"
    LIB_BASE_DIR="$HOME/.checkpoint-rewind"
    CONFIG_DIR="$HOME/.config/checkpoint-rewind/tiers"
    SCRIPT_PATH_VAR_CLAUDE="~/.claude/hooks"
    SCRIPT_PATH_VAR_FACTORY="~/.factory/hooks"
fi

# Install files function
install_files() {
    echo "Installing checkpoint system files..."
    
    # Determine which agents we're installing for
    local install_claude=false
    local install_factory=false
    
    for agent in "${AGENTS[@]}"; do
        [[ "$agent" == "claude-code" ]] && install_claude=true
        [[ "$agent" == "droid-cli" ]] && install_factory=true
    done
    
    # Create directories
    if [[ "$DRY_RUN" == "false" ]]; then
        [[ "$install_claude" == "true" ]] && mkdir -p "$CLAUDE_HOOKS_DIR"
        [[ "$install_factory" == "true" ]] && mkdir -p "$FACTORY_HOOKS_DIR"
        mkdir -p "$LIB_BASE_DIR/parsers"
        mkdir -p "$LIB_BASE_DIR/metadata"
        mkdir -p "$LIB_BASE_DIR/rewind"
        mkdir -p "$CONFIG_DIR"
        mkdir -p "$HOME/.claude-checkpoints"
        mkdir -p "$HOME/.factory-checkpoints"
    else
        echo "[DRY RUN] Would create directories:"
        [[ "$install_claude" == "true" ]] && echo "  - $CLAUDE_HOOKS_DIR"
        [[ "$install_factory" == "true" ]] && echo "  - $FACTORY_HOOKS_DIR"
        echo "  - $LIB_BASE_DIR/{parsers,metadata,rewind}"
        echo "  - $CONFIG_DIR"
        echo "  - $HOME/.claude-checkpoints"
        echo "  - $HOME/.factory-checkpoints"
    fi
    
    # Copy main script to appropriate location(s)
    if [[ "$DRY_RUN" == "false" ]]; then
        if [[ "$install_claude" == "true" ]]; then
            cp "$SCRIPT_DIR/smart-checkpoint.sh" "$CLAUDE_HOOKS_DIR/"
            chmod +x "$CLAUDE_HOOKS_DIR/smart-checkpoint.sh"
            echo "✓ Installed smart-checkpoint.sh to $CLAUDE_HOOKS_DIR/"
        fi
        
        if [[ "$install_factory" == "true" ]]; then
            cp "$SCRIPT_DIR/smart-checkpoint.sh" "$FACTORY_HOOKS_DIR/"
            chmod +x "$FACTORY_HOOKS_DIR/smart-checkpoint.sh"
            echo "✓ Installed smart-checkpoint.sh to $FACTORY_HOOKS_DIR/"
        fi
        
        # Copy rewind script
        cp "$SCRIPT_DIR/checkpoint-rewind-full.sh" "$LIB_BASE_DIR/"
        chmod +x "$LIB_BASE_DIR/checkpoint-rewind-full.sh"
        echo "✓ Installed checkpoint-rewind-full.sh to $LIB_BASE_DIR/"
    else
        [[ "$install_claude" == "true" ]] && echo "[DRY RUN] Would copy: smart-checkpoint.sh → $CLAUDE_HOOKS_DIR/"
        [[ "$install_factory" == "true" ]] && echo "[DRY RUN] Would copy: smart-checkpoint.sh → $FACTORY_HOOKS_DIR/"
        echo "[DRY RUN] Would copy: checkpoint-rewind-full.sh → $LIB_BASE_DIR/"
    fi
    
    # Copy Node.js modules
    if [[ "$DRY_RUN" == "false" ]]; then
        cp "$PROJECT_ROOT/lib/parsers/SessionParser.js" "$LIB_BASE_DIR/parsers/"
        cp "$PROJECT_ROOT/lib/metadata/ConversationMetadata.js" "$LIB_BASE_DIR/metadata/"
        cp "$PROJECT_ROOT/lib/rewind/ConversationTruncator.js" "$LIB_BASE_DIR/rewind/"
        echo "✓ Installed Node.js modules to $LIB_BASE_DIR/"
    else
        echo "[DRY RUN] Would copy Node.js modules to $LIB_BASE_DIR/"
    fi
    
    # Copy tier configuration files
    if [[ "$DRY_RUN" == "false" ]]; then
        cp "$PROJECT_ROOT/configs/"*-tier.json "$CONFIG_DIR/"
        echo "✓ Installed tier configs to $CONFIG_DIR/"
    else
        echo "[DRY RUN] Would copy tier configs to $CONFIG_DIR/"
    fi
    
    echo ""
}

# Generate hook template with correct paths
generate_hook_template() {
    local agent="$1"
    local script_path_var=""
    
    case "$agent" in
        claude-code)
            script_path_var="$SCRIPT_PATH_VAR_CLAUDE"
            ;;
        droid-cli)
            script_path_var="$SCRIPT_PATH_VAR_FACTORY"
            ;;
    esac
    
    # Read the base template and substitute the path
    cat "$PROJECT_ROOT/hooks/${TIER}-hooks.json" | \
        sed "s|~/.local/bin/smart-checkpoint.sh|${script_path_var}/smart-checkpoint.sh|g"
}

# Update settings for an agent
update_agent_settings() {
    local agent="$1"
    local settings_file=""
    
    case "$agent" in
        claude-code)
            if [[ "$PROJECT_INSTALL" == "true" ]]; then
                settings_file="./.claude/settings.json"
            else
                settings_file="$HOME/.claude/settings.json"
            fi
            ;;
        droid-cli)
            if [[ "$PROJECT_INSTALL" == "true" ]]; then
                settings_file="./.factory/settings.json"
            else
                settings_file="$HOME/.factory/settings.json"
            fi
            ;;
    esac
    
    echo "Configuring hooks for $agent..."
    echo "Settings file: $settings_file"
    
    # Create parent directory if needed
    local settings_dir="$(dirname "$settings_file")"
    if [[ "$DRY_RUN" == "false" ]] && [[ ! -d "$settings_dir" ]]; then
        mkdir -p "$settings_dir"
    fi
    
    # Generate hook template with correct paths
    local hook_template_content
    hook_template_content=$(generate_hook_template "$agent")
    
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
    
    # Merge or create settings
    if [[ "$DRY_RUN" == "false" ]]; then
        if [[ -f "$settings_file" ]]; then
            # Merge: preserve existing settings, add/replace hooks
            # Strip // comments before jq can process it (Droid adds comments)
            grep -v '^\s*//' "$settings_file" > "${settings_file}.clean"
            
            # Save hook template to temp file
            echo "$hook_template_content" > "${settings_file}.hooks"
            
            # Merge: existing settings get merged with hook template
            jq -s '.[0] * .[1]' "${settings_file}.clean" "${settings_file}.hooks" > "${settings_file}.tmp"
            mv "${settings_file}.tmp" "$settings_file"
            rm "${settings_file}.clean" "${settings_file}.hooks"
            echo "✓ Merged hooks into existing settings"
        else
            # New file: write hook template
            echo "$hook_template_content" > "$settings_file"
            echo "✓ Created new settings with hooks"
        fi
    else
        echo "[DRY RUN] Would merge/create settings with hooks"
    fi
    
    echo ""
}

# Set CHECKPOINT_TIER environment variable
set_tier_env() {
    # Skip for project-level installs (not needed)
    if [[ "$PROJECT_INSTALL" == "true" ]]; then
        echo "Skipping environment variable setup (project-level install)"
        echo ""
        return
    fi
    
    echo "Configuring CHECKPOINT_TIER environment variable..."
    
    # Determine shell profile
    local shell_profile=""
    if [[ -f "$HOME/.zshrc" ]]; then
        shell_profile="$HOME/.zshrc"
    elif [[ -f "$HOME/.bashrc" ]]; then
        shell_profile="$HOME/.bashrc"
    else
        echo "⚠️  No .bashrc or .zshrc found, skipping environment variable setup"
        echo "   You'll need to manually set: export CHECKPOINT_TIER=$TIER"
        return
    fi
    
    if [[ "$DRY_RUN" == "false" ]]; then
        # Check if already exists
        if grep -q "CHECKPOINT_TIER" "$shell_profile"; then
            echo "  CHECKPOINT_TIER already exists in $shell_profile"
        else
            echo "" >> "$shell_profile"
            echo "# Checkpoint/Rewind System" >> "$shell_profile"
            echo "export CHECKPOINT_TIER=$TIER" >> "$shell_profile"
            echo "✓ Added CHECKPOINT_TIER=$TIER to $shell_profile"
        fi
    else
        echo "[DRY RUN] Would add to $shell_profile:"
        echo "  export CHECKPOINT_TIER=$TIER"
    fi
    
    echo ""
}

# Install files
install_files

# Update each agent
for agent in "${AGENTS[@]}"; do
    update_agent_settings "$agent"
done

# Set environment variable
set_tier_env

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
    if [[ "$PROJECT_INSTALL" == "false" ]]; then
        echo "  1. Restart your shell (or run: source ~/.bashrc)"
    fi
    echo "  2. Restart your agent:"
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
    echo "Installed for: ${AGENTS[*]}"
    echo "Tier: $TIER"
    echo "Scope: $([ "$PROJECT_INSTALL" == "true" ] && echo "project-level" || echo "user-level")"
    echo ""
    echo "Configuration locations:"
    if [[ "$PROJECT_INSTALL" == "true" ]]; then
        echo "  • Hook scripts: ./.claude/hooks/ and/or ./.factory/hooks/"
        echo "  • Libraries: ./.checkpoint-rewind/"
        echo "  • Tier configs: ./.checkpoint-rewind/tiers/"
    else
        echo "  • Hook scripts: ~/.claude/hooks/ and/or ~/.factory/hooks/"
        echo "  • Libraries: ~/.checkpoint-rewind/"
        echo "  • Tier configs: ~/.config/checkpoint-rewind/tiers/"
    fi
else
    echo "Run without --dry-run to actually install."
fi
echo ""
