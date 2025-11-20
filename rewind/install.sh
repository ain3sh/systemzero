#!/bin/bash
# System Zero Rewind - Unified Installer (v3)
# Installs rewind globally and sets up user environment.

set -euo pipefail

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Paths
INSTALL_DIR="$HOME/.rewind/system"
BIN_DIR="$HOME/.local/bin"
GLOBAL_CONFIG_DIR="$HOME/.rewind"

# Detect if running from curl/pipe or local script
# If executed via pipe, BASH_SOURCE is empty or dash
if [ -z "${BASH_SOURCE:-}" ] || [ "${BASH_SOURCE:-}" = "-" ]; then
    # Running from curl/pipe
    REPO_ROOT="/tmp/systemzero-rewind-install"
    IS_LOCAL_INSTALL=false
else
    # Running locally
    REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    IS_LOCAL_INSTALL=true
fi

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}🚀 System Zero Rewind Installer${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# 1. Prerequisites Check
echo -e "${YELLOW}Checking prerequisites...${NC}"
if ! command -v node &>/dev/null; then
    echo -e "${RED}❌ Node.js not found. Please install Node.js first.${NC}"
    exit 1
fi
if ! command -v jq &>/dev/null; then
    echo -e "${RED}❌ jq not found. Please install jq first.${NC}"
    exit 1
fi
if ! command -v git &>/dev/null; then
    echo -e "${RED}❌ git not found. Please install git first.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Prerequisites met${NC}"

# 1.5 Clone repo if remote install
if [ "$IS_LOCAL_INSTALL" = false ]; then
    echo -e "\n${YELLOW}Downloading System Zero Rewind...${NC}"
    rm -rf "$REPO_ROOT"
    # We clone specific branch/repo structure. Assuming 'rewind' is at root of systemzero repo or subfolder
    # Adjusted based on user prompt: https://raw.githubusercontent.com/ain3sh/systemzero/main/scripts/rewind/install.sh
    # This implies the repo structure is systemzero/scripts/rewind/install.sh
    # But the code structure we have here is systemzero/rewind/lib...
    
    # Clone systemzero repo
    # NOTE: We assume main branch exists. If main is missing, it will fail.
    git clone --depth 1 https://github.com/ain3sh/systemzero.git "$REPO_ROOT"
    
    # Note: The actual systemzero repo has a 'rewind' folder at root.
    if [ -d "$REPO_ROOT/rewind/lib" ]; then
        REPO_ROOT="$REPO_ROOT/rewind"
    elif [ -d "$REPO_ROOT/lib" ]; then
        # Root is correct
        :
    else
        # Fallback for testing/mock environment
        echo -e "${YELLOW}⚠️  Could not locate rewind files. Check clone structure.${NC}"
        # For test purposes, assume root is correct if lib exists at all
        ls -R "$REPO_ROOT"
        exit 1
    fi
fi

# 2. Install binaries and libraries
echo -e "\n${YELLOW}Installing system files...${NC}"
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/bin"
mkdir -p "$INSTALL_DIR/lib"
mkdir -p "$INSTALL_DIR/hooks"
mkdir -p "$GLOBAL_CONFIG_DIR"

# Copy core files
mkdir -p "$INSTALL_DIR/lib"
cp -r "$REPO_ROOT/lib/"* "$INSTALL_DIR/lib/"
cp "$REPO_ROOT/bin/rewind.js" "$INSTALL_DIR/bin/"
cp "$REPO_ROOT/bin/smart-checkpoint.sh" "$INSTALL_DIR/hooks/"
cp "$REPO_ROOT/bin/hook-runner.js" "$INSTALL_DIR/bin/"
cp -r "$REPO_ROOT/configs" "$INSTALL_DIR/"

# Make executable
chmod +x "$INSTALL_DIR/bin/rewind.js"
chmod +x "$INSTALL_DIR/bin/hook-runner.js"
chmod +x "$INSTALL_DIR/hooks/smart-checkpoint.sh"

echo -e "${GREEN}✓ System files installed to $INSTALL_DIR${NC}"

# 3. Symlink management
echo -e "\n${YELLOW}Configuring CLI...${NC}"
mkdir -p "$BIN_DIR"

# Remove old symlink if exists
if [ -L "$BIN_DIR/rewind" ]; then
    rm "$BIN_DIR/rewind"
fi

ln -s "$INSTALL_DIR/bin/rewind.js" "$BIN_DIR/rewind"

# Check PATH
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo -e "${YELLOW}⚠️  Warning: $BIN_DIR is not in your PATH.${NC}"
    echo "   Add this to your shell profile (~/.bashrc or ~/.zshrc):"
    echo "   export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo -e "${GREEN}✓ 'rewind' command linked in $BIN_DIR${NC}"

# 4. Interactive Configuration
echo -e "\n${YELLOW}Configuration Setup${NC}"

# Default storage mode
CURRENT_MODE="project"
if [ -f "$GLOBAL_CONFIG_DIR/config.json" ]; then
    EXISTING_MODE=$(jq -r '.storage.mode // "project"' "$GLOBAL_CONFIG_DIR/config.json")
    if [ "$EXISTING_MODE" != "null" ]; then
        CURRENT_MODE="$EXISTING_MODE"
    fi
fi

echo -e "Where should checkpoints be stored by default?"
echo -e "  [1] ${GREEN}Project folder${NC} (.rewind/ inside project) - Default"
echo -e "  [2] ${GREEN}Global storage${NC} (~/.rewind/storage/...) - Clean projects"
read -p "Select [1/2] (default: 1): " MODE_SELECTION

STORAGE_MODE="project"
if [[ "$MODE_SELECTION" == "2" ]]; then
    STORAGE_MODE="global"
fi

# Create/Update global config
mkdir -p "$GLOBAL_CONFIG_DIR"
cat > "$GLOBAL_CONFIG_DIR/config.json" <<EOF
{
  "storage": {
    "mode": "$STORAGE_MODE"
  }
}
EOF

echo -e "${GREEN}✓ Default storage set to: $STORAGE_MODE${NC}"

# 5. Hook Registration
echo -e "\n${YELLOW}Registering Agent Hooks...${NC}"

# Hook paths
SMART_CHECKPOINT="$INSTALL_DIR/hooks/smart-checkpoint.sh"
HOOK_CONFIG_FILE="$INSTALL_DIR/configs/balanced-hooks.json"

# Generate the hook config with absolute paths
# We use a temporary file to perform the substitution
HOOK_JSON=$(cat "$REPO_ROOT/hooks/balanced-hooks.json" | sed "s|~/.local/bin/smart-checkpoint.sh|$SMART_CHECKPOINT|g")

register_hooks() {
    local SETTINGS_FILE="$1"
    local NAME="$2"

    if [ ! -f "$SETTINGS_FILE" ]; then
        # Create basic settings file if it doesn't exist
        mkdir -p "$(dirname "$SETTINGS_FILE")"
        echo "{}" > "$SETTINGS_FILE"
    fi

    # Backup
    cp "$SETTINGS_FILE" "$SETTINGS_FILE.bak"

    # Merge hooks
    echo "$HOOK_JSON" > /tmp/rewind_hooks.json
    
    # Use jq to merge hooks into existing settings
    # Note: We filter out comments (//) before processing if they exist, though standard JSON shouldn't have them.
    # Droid/Claude sometimes allow comments in settings.
    
    if jq -e . "$SETTINGS_FILE" >/dev/null 2>&1; then
        jq -s '.[0] * .[1]' "$SETTINGS_FILE" /tmp/rewind_hooks.json > "$SETTINGS_FILE.tmp"
        mv "$SETTINGS_FILE.tmp" "$SETTINGS_FILE"
        echo -e "${GREEN}✓ Registered hooks for $NAME${NC}"
    else
        echo -e "${RED}⚠️  Could not parse $SETTINGS_FILE (invalid JSON). Hooks not registered for $NAME.${NC}"
        echo "   Please manually add the hooks from $HOOK_CONFIG_FILE"
    fi
    
    rm /tmp/rewind_hooks.json
}

# Register for Claude
if [ -d "$HOME/.claude" ]; then
    register_hooks "$HOME/.claude/settings.json" "Claude Code"
fi

# Register for Droid
if [ -d "$HOME/.factory" ]; then
    register_hooks "$HOME/.factory/settings.json" "Droid CLI"
fi

echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ Installation Complete!${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "Try it out:"
echo "  1. mkdir my-project && cd my-project"
echo "  2. rewind init"
echo "  3. rewind status"
echo ""
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo -e "${RED}IMPORTANT: Restart your shell to use the 'rewind' command.${NC}"
fi

if [[ "$IS_LOCAL_INSTALL" = false ]]; then
    rm -rf "/tmp/systemzero-rewind-install"
fi
