#!/bin/bash
# System Zero Rewind - Unified Installer (Python v4)
# Installs rewind globally and sets up user environment.

set -euo pipefail

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Paths
INSTALL_DIR="$HOME/.rewind/system"
BIN_DIR="$HOME/.local/bin"
GLOBAL_CONFIG="$HOME/.rewind/config.json"

# Detect if running from curl/pipe or local script
if [ -z "${BASH_SOURCE:-}" ] || [ "${BASH_SOURCE:-}" = "-" ]; then
    REPO_ROOT="/tmp/systemzero-rewind-install"
    IS_LOCAL_INSTALL=false
else
    REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    IS_LOCAL_INSTALL=true
fi

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}🚀 System Zero Rewind Installer (v4.0)${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# =============================================================================
# 1. Prerequisites Check
# =============================================================================
echo -e "${YELLOW}Checking prerequisites...${NC}"

# Check Python version (3.9+)
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}❌ Python 3 not found. Please install Python 3.9 or later.${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [[ "$PYTHON_MAJOR" -lt 3 ]] || [[ "$PYTHON_MAJOR" -eq 3 && "$PYTHON_MINOR" -lt 9 ]]; then
    echo -e "${RED}❌ Python 3.9+ required. Found: Python $PYTHON_VERSION${NC}"
    exit 1
fi

if ! command -v git &>/dev/null; then
    echo -e "${RED}❌ git not found. Please install git first.${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Prerequisites met (Python $PYTHON_VERSION)${NC}"

# =============================================================================
# 1.5 Clone repo if remote install
# =============================================================================
if [ "$IS_LOCAL_INSTALL" = false ]; then
    echo -e "\n${YELLOW}Downloading System Zero Rewind...${NC}"
    rm -rf "$REPO_ROOT"
    git clone --depth 1 https://github.com/ain3sh/systemzero.git "$REPO_ROOT"
    
    # Navigate to rewind directory
    if [ -d "$REPO_ROOT/rewind/src" ]; then
        REPO_ROOT="$REPO_ROOT/rewind"
    elif [ -d "$REPO_ROOT/src" ]; then
        REPO_ROOT="$REPO_ROOT"
    else
        echo -e "${RED}❌ Could not locate rewind directory${NC}"
        exit 1
    fi
fi

# =============================================================================
# 2. Check for existing installation
# =============================================================================
IS_UPDATE=false
CURRENT_TIER=""

if [ -f "$GLOBAL_CONFIG" ]; then
    IS_UPDATE=true
    CURRENT_TIER=$(python3 -c "
import json
try:
    with open('$GLOBAL_CONFIG') as f:
        print(json.load(f).get('tier', 'balanced'))
except:
    print('balanced')
" 2>/dev/null || echo "balanced")
    
    echo -e "\n${YELLOW}Existing installation detected (tier: $CURRENT_TIER)${NC}"
fi

# =============================================================================
# 3. Install system files
# =============================================================================
echo -e "\n${YELLOW}Installing system files...${NC}"
mkdir -p "$INSTALL_DIR"
mkdir -p "$HOME/.rewind"

# Copy Python package
cp -r "$REPO_ROOT/src" "$INSTALL_DIR/"
cp -r "$REPO_ROOT/tiers" "$INSTALL_DIR/"

# Copy hook entry point (flattened - no hooks/ subdir)
cp "$REPO_ROOT/bin/smart-checkpoint" "$INSTALL_DIR/"

# Copy CLI entry point
cp "$REPO_ROOT/bin/rewind" "$INSTALL_DIR/bin-rewind"

# Copy ignore config
if [ -f "$REPO_ROOT/bin/rewind-checkpoint-ignore.json" ]; then
    cp "$REPO_ROOT/bin/rewind-checkpoint-ignore.json" "$INSTALL_DIR/"
fi

# Make executable
chmod +x "$INSTALL_DIR/smart-checkpoint"
chmod +x "$INSTALL_DIR/bin-rewind"

echo -e "${GREEN}✓ System files installed to $INSTALL_DIR${NC}"

# =============================================================================
# 4. Symlink management
# =============================================================================
echo -e "\n${YELLOW}Configuring CLI...${NC}"
mkdir -p "$BIN_DIR"

# Remove old symlink if exists
if [ -L "$BIN_DIR/rewind" ] || [ -f "$BIN_DIR/rewind" ]; then
    rm -f "$BIN_DIR/rewind"
fi

ln -s "$INSTALL_DIR/bin-rewind" "$BIN_DIR/rewind"

# Check PATH
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo -e "${YELLOW}⚠️  $BIN_DIR is not in your PATH.${NC}"
    echo "   Add to ~/.bashrc or ~/.zshrc: export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo -e "${GREEN}✓ 'rewind' command linked${NC}"

# =============================================================================
# 5. Tier Selection
# =============================================================================
echo -e "\n${YELLOW}Tier Configuration${NC}"

if [ "$IS_UPDATE" = true ]; then
    echo -e "Current tier: ${BOLD}$CURRENT_TIER${NC}"
    read -p "Change tier? [y/N]: " CHANGE_TIER
    
    if [[ "$CHANGE_TIER" =~ ^[Yy]$ ]]; then
        SELECT_TIER=true
    else
        SELECT_TIER=false
        SELECTED_TIER="$CURRENT_TIER"
    fi
else
    SELECT_TIER=true
fi

if [ "$SELECT_TIER" = true ]; then
    echo -e "\nSelect checkpoint tier:"
    echo -e "  [1] ${GREEN}Minimal${NC}    - Session start only (lowest overhead)"
    echo -e "  [2] ${GREEN}Balanced${NC}   - Before file edits, 30s cooldown ${BOLD}(recommended)${NC}"
    echo -e "  [3] ${GREEN}Aggressive${NC} - Edits + bash + prompts + session end"
    read -p "Select [1/2/3] (default: 2): " TIER_SELECTION

    case "$TIER_SELECTION" in
        1) SELECTED_TIER="minimal" ;;
        3) SELECTED_TIER="aggressive" ;;
        *) SELECTED_TIER="balanced" ;;
    esac
fi

TIER_FILE="$INSTALL_DIR/tiers/${SELECTED_TIER}.json"

# Extract runtime config to global config
python3 << EOF
import json
from pathlib import Path

tier_path = Path("$TIER_FILE")
config_path = Path("$GLOBAL_CONFIG")

with open(tier_path) as f:
    tier = json.load(f)

config = {
    "tier": tier["tier"],
    "runtime": tier["runtime"],
    "storage": {"mode": "project"}
}

# Preserve existing storage mode if present
if config_path.exists():
    try:
        with open(config_path) as f:
            existing = json.load(f)
        if "storage" in existing:
            config["storage"] = existing["storage"]
    except:
        pass

config_path.parent.mkdir(parents=True, exist_ok=True)
with open(config_path, "w") as f:
    json.dump(config, f, indent=2)
EOF

echo -e "${GREEN}✓ Tier set to: $SELECTED_TIER${NC}"

# =============================================================================
# 6. Hook Registration
# =============================================================================
echo -e "\n${YELLOW}Hook Registration${NC}"

register_hooks() {
    local SETTINGS_FILE="$1"
    local AGENT_NAME="$2"

    # Use our smart hook merger
    PYTHONPATH="$INSTALL_DIR" python3 -m src.utils.hook_merger "$SETTINGS_FILE" "$TIER_FILE"
}

# Determine if we should register hooks
REGISTER_HOOKS=false

if [ "$IS_UPDATE" = true ]; then
    read -p "Re-register hooks in settings.json? [y/N]: " REREG
    if [[ "$REREG" =~ ^[Yy]$ ]]; then
        REGISTER_HOOKS=true
    fi
else
    read -p "Register hooks for your AI agents? [Y/n]: " REG
    if [[ ! "$REG" =~ ^[Nn]$ ]]; then
        REGISTER_HOOKS=true
    fi
fi

if [ "$REGISTER_HOOKS" = true ]; then
    # Register for Claude Code
    if [ -d "$HOME/.claude" ]; then
        CLAUDE_SETTINGS="$HOME/.claude/settings.json"
        [ ! -f "$CLAUDE_SETTINGS" ] && echo "{}" > "$CLAUDE_SETTINGS"
        register_hooks "$CLAUDE_SETTINGS" "Claude Code"
        echo -e "${GREEN}✓ Registered hooks for Claude Code${NC}"
    fi

    # Register for Droid
    if [ -d "$HOME/.factory" ]; then
        DROID_SETTINGS="$HOME/.factory/settings.json"
        [ ! -f "$DROID_SETTINGS" ] && echo "{}" > "$DROID_SETTINGS"
        register_hooks "$DROID_SETTINGS" "Droid CLI"
        echo -e "${GREEN}✓ Registered hooks for Droid CLI${NC}"
    fi
    
    if [ ! -d "$HOME/.claude" ] && [ ! -d "$HOME/.factory" ]; then
        echo -e "${YELLOW}No Claude Code or Droid installation found.${NC}"
        echo "  Hooks can be registered manually later with: rewind config --register-hooks"
    fi
else
    echo -e "${YELLOW}Skipped hook registration.${NC}"
    if [ "$IS_UPDATE" = false ]; then
        echo "  Register later with: rewind config --register-hooks"
    fi
fi

# =============================================================================
# 7. Completion
# =============================================================================
echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ Installation Complete!${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "Quick start:"
echo "  1. cd your-project"
echo "  2. rewind init"
echo "  3. rewind save 'Initial checkpoint'"
echo ""
echo "Commands:"
echo "  rewind status              Show status"
echo "  rewind list                List checkpoints"
echo "  rewind restore <name>      Restore checkpoint"
echo "  rewind undo                Undo last change"
echo "  rewind config --tier X     Change tier"
echo ""

if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo -e "${RED}NOTE: Restart your shell or run: export PATH=\"\$HOME/.local/bin:\$PATH\"${NC}"
fi

# Cleanup temp files for remote install
if [ "$IS_LOCAL_INSTALL" = false ]; then
    rm -rf "/tmp/systemzero-rewind-install"
fi
