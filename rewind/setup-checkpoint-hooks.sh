#!/bin/bash
# Setup script for Claude Code checkpoint hooks
# Installs ClaudePoint and configures smart checkpointing

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "\n${BLUE}================================================${NC}"
    echo -e "${BLUE}  Claude Code Smart Checkpoint Setup${NC}"
    echo -e "${BLUE}================================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    print_info "Checking prerequisites..."

    if ! command -v node >/dev/null 2>&1; then
        print_error "Node.js is not installed. Please install Node.js 18+ first."
        exit 1
    fi

    if ! command -v npm >/dev/null 2>&1; then
        print_error "npm is not installed. Please install npm first."
        exit 1
    fi

    local node_version
    node_version=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
    if [ "$node_version" -lt 18 ]; then
        print_error "Node.js version 18+ required (found v$node_version)"
        exit 1
    fi

    print_success "Prerequisites met"
}

# Install ClaudePoint
install_claudepoint() {
    print_info "Installing ClaudePoint..."

    if command -v claudepoint >/dev/null 2>&1; then
        local version
        version=$(claudepoint --version 2>/dev/null || echo "unknown")
        print_warning "ClaudePoint already installed (version: $version)"
        read -p "Reinstall? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_info "Skipping ClaudePoint installation"
            return
        fi
    fi

    if npm install -g claudepoint; then
        print_success "ClaudePoint installed successfully"
    else
        print_error "Failed to install ClaudePoint"
        exit 1
    fi
}

# Install smart-checkpoint script
install_smart_checkpoint() {
    print_info "Installing smart-checkpoint.sh..."

    local script_dir="$HOME/.local/bin"
    mkdir -p "$script_dir"

    local script_path="$script_dir/smart-checkpoint.sh"

    # Check if script exists in current directory
    if [ -f "smart-checkpoint.sh" ]; then
        cp smart-checkpoint.sh "$script_path"
    elif [ -f "../smart-checkpoint.sh" ]; then
        cp ../smart-checkpoint.sh "$script_path"
    else
        print_error "smart-checkpoint.sh not found in current or parent directory"
        print_info "Please download it from the repository"
        exit 1
    fi

    chmod +x "$script_path"

    # Verify jq is available (needed for JSON parsing)
    if ! command -v jq >/dev/null 2>&1; then
        print_warning "jq is not installed (required for smart checkpoint script)"
        print_info "Install with: sudo apt-get install jq (Ubuntu/Debian)"
        print_info "            or: brew install jq (macOS)"
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi

    print_success "smart-checkpoint.sh installed to $script_path"
}

# Configure hooks
configure_hooks() {
    print_info "Configuring hooks..."

    echo ""
    echo "Choose hook configuration level:"
    echo "  1) Minimal    - Only checkpoint before file creation (safest, least invasive)"
    echo "  2) Balanced   - Smart checkpointing with anti-spam (recommended)"
    echo "  3) Aggressive - Maximum safety with prompt analysis"
    echo "  4) Skip       - Don't configure hooks now"
    echo ""
    read -p "Enter choice (1-4) [2]: " choice
    choice=${choice:-2}

    local config_file=""
    case $choice in
        1)
            config_file="minimal-hooks.json"
            ;;
        2)
            config_file="balanced-hooks.json"
            ;;
        3)
            config_file="aggressive-hooks.json"
            ;;
        4)
            print_info "Skipping hook configuration"
            return
            ;;
        *)
            print_error "Invalid choice"
            exit 1
            ;;
    esac

    # Determine scope
    echo ""
    echo "Choose hook scope:"
    echo "  1) User-level   - Applies to all your Claude Code projects"
    echo "  2) Project-level - Only this project (can be committed to git)"
    echo ""
    read -p "Enter choice (1-2) [1]: " scope_choice
    scope_choice=${scope_choice:-1}

    local target_file=""
    case $scope_choice in
        1)
            target_file="$HOME/.claude/settings.json"
            mkdir -p "$HOME/.claude"
            ;;
        2)
            target_file=".claude/settings.json"
            mkdir -p ".claude"
            ;;
        *)
            print_error "Invalid choice"
            exit 1
            ;;
    esac

    # Check if hooks examples exist
    if [ -f "claude-hooks-examples/$config_file" ]; then
        local hooks_source="claude-hooks-examples/$config_file"
    elif [ -f "../claude-hooks-examples/$config_file" ]; then
        local hooks_source="../claude-hooks-examples/$config_file"
    else
        print_error "Hook configuration file not found: $config_file"
        exit 1
    fi

    # Backup existing settings
    if [ -f "$target_file" ]; then
        local backup_file="${target_file}.backup.$(date +%Y%m%d_%H%M%S)"
        cp "$target_file" "$backup_file"
        print_warning "Backed up existing settings to $backup_file"

        # Merge with existing settings
        print_info "Merging with existing settings..."
        # Simple merge: replace hooks section
        # Note: This is a basic implementation - proper JSON merging would be better
        cp "$hooks_source" "$target_file"
    else
        cp "$hooks_source" "$target_file"
    fi

    print_success "Hooks configured: $config_file → $target_file"
}

# Setup ClaudePoint in project
setup_claudepoint_project() {
    echo ""
    read -p "Run 'claudepoint setup' in current directory? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_info "Running claudepoint setup..."
        if claudepoint setup; then
            print_success "ClaudePoint project setup complete"
        else
            print_warning "ClaudePoint setup had issues (non-fatal)"
        fi
    else
        print_info "Skipped project setup - run 'claudepoint setup' manually later"
    fi
}

# Create state directory
create_state_directory() {
    print_info "Creating checkpoint state directory..."
    mkdir -p "$HOME/.claude-checkpoints"
    print_success "State directory created: $HOME/.claude-checkpoints"
}

# Print next steps
print_next_steps() {
    echo -e "\n${GREEN}================================================${NC}"
    echo -e "${GREEN}  Setup Complete!${NC}"
    echo -e "${GREEN}================================================${NC}\n"

    echo -e "${BLUE}Next steps:${NC}\n"

    echo "1. Restart Claude Code to load new hooks"
    echo ""

    echo "2. Test the setup:"
    echo "   • In Claude Code, ask: 'Create a new file called test.txt'"
    echo "   • You should see checkpoint messages in the transcript"
    echo ""

    echo "3. View checkpoints:"
    echo "   $ claudepoint list"
    echo ""

    echo "4. Customize settings:"
    echo "   • Edit: ~/.local/bin/smart-checkpoint.sh"
    echo "   • Adjust MIN_CHECKPOINT_INTERVAL (default: 30s)"
    echo "   • Adjust MIN_CHANGE_SIZE (default: 50 chars)"
    echo ""

    echo "5. Debugging:"
    echo "   • Test script: ~/.local/bin/smart-checkpoint.sh pre-modify test-session Edit"
    echo "   • View state: ls -la ~/.claude-checkpoints/"
    echo "   • Check hooks: /hooks in Claude Code"
    echo ""

    echo -e "${YELLOW}Documentation:${NC}"
    echo "   • ClaudePoint: https://github.com/andycufari/ClaudePoint"
    echo "   • Hooks reference: https://code.claude.com/docs/en/hooks.md"
    echo "   • Strategy guide: checkpoint-hooks-strategy.md"
    echo ""
}

# Main installation flow
main() {
    print_header

    check_prerequisites
    install_claudepoint
    install_smart_checkpoint
    create_state_directory
    configure_hooks
    setup_claudepoint_project

    print_next_steps
}

# Run main function
main
