#!/bin/bash
# smart-checkpoint.sh - System Zero Shim
# 
# This is now a simple pass-through to the Node.js hook system.
# All the complex logic has been moved to lib/hooks/HookHandler.js
# for better performance, testing, and maintainability.

set -euo pipefail

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Find the hook-runner.js entry point
find_hook_runner() {
    # Try to resolve hook-runner.js relative to this script first
    # This handles symlinked installs and vendored copies
    local real_script_path
    if command -v realpath >/dev/null 2>&1; then
        real_script_path=$(realpath "$SCRIPT_DIR")
    else
        real_script_path="$SCRIPT_DIR"
    fi

    # 1. Check adjacent to this script (common in installation)
    if [[ -f "$real_script_path/../bin/hook-runner.js" ]]; then
        echo "$real_script_path/../bin/hook-runner.js"
        return 0
    fi

    # 2. Check adjacent (in case we are in bin/ ourselves)
    if [[ -f "$real_script_path/hook-runner.js" ]]; then
        echo "$real_script_path/hook-runner.js"
        return 0
    fi
    
    # 3. Check global installation path (standard location)
    if [[ -f "$HOME/.rewind/system/bin/hook-runner.js" ]]; then
        echo "$HOME/.rewind/system/bin/hook-runner.js"
        return 0
    fi

    # 4. Legacy fallbacks for development
    local candidates=(
        "$SCRIPT_DIR/hook-runner.js"
        "$SCRIPT_DIR/../bin/hook-runner.js"
        "$SCRIPT_DIR/../../bin/hook-runner.js"
    )
    
    for candidate in "${candidates[@]}"; do
        if [[ -f "$candidate" ]]; then
            echo "$candidate"
            return 0
        fi
    done
    
    return 1
}

# Main execution
main() {
    local action="${1:-pre-tool-use}"
    
    # Find the hook runner
    local hook_runner
    if ! hook_runner=$(find_hook_runner); then
        echo "[smart-checkpoint] ERROR: hook-runner.js not found" >&2
        echo "[smart-checkpoint] Please run install-hooks.sh to install the System Zero implementation" >&2
        exit 1
    fi
    
    # Execute the Node.js hook system
    exec node "$hook_runner" "$action"
}

main "$@"
