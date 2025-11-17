#!/bin/bash
# smart-checkpoint.sh
# Integration layer: ClaudePoint + SessionParser + ConversationMetadata
#
# Called by hooks to create code checkpoints with conversation context
#
# Usage: smart-checkpoint.sh <action> [args]
#   Actions: pre-tool-use, session-start, post-bash, stop

set -euo pipefail

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Configuration - read from installed location
TIER="${CHECKPOINT_TIER:-balanced}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/checkpoint-rewind"
CONFIG_FILE="$CONFIG_DIR/tiers/${TIER}-tier.json"

# State directories for anti-spam tracking
STATE_DIR_CLAUDE="$HOME/.claude-checkpoints"
STATE_DIR_DROID="$HOME/.factory-checkpoints"

# Detect which agent we're running in
detect_agent() {
    # Check which agent directories or env vars exist
    if [[ -d "$HOME/.claude/projects" ]] || [[ -n "${CLAUDE_PROJECT_DIR:-}" ]]; then
        echo "claude-code"
    elif [[ -d "$HOME/.factory/sessions" ]] || [[ -n "${FACTORY_PROJECT_DIR:-}" ]]; then
        echo "droid-cli"
    else
        echo "unknown"
    fi
}

AGENT=$(detect_agent)
STATE_DIR="$STATE_DIR_CLAUDE"
[[ "$AGENT" == "droid-cli" ]] && STATE_DIR="$STATE_DIR_DROID"

mkdir -p "$STATE_DIR"

# Load configuration from tier config file
load_config() {
    if [[ ! -f "$CONFIG_FILE" ]]; then
        echo "[smart-checkpoint] WARNING: Config not found: $CONFIG_FILE" >&2
        echo "[smart-checkpoint] Using default values (balanced tier)" >&2
        ANTI_SPAM_ENABLED=1
        ANTI_SPAM_INTERVAL=30
        MIN_CHANGE_SIZE=50
        return
    fi
    
    # Load from tier config using jq if available
    if command -v jq &>/dev/null; then
        ANTI_SPAM_ENABLED=$(jq -r '.antiSpam.enabled // true' "$CONFIG_FILE")
        [[ "$ANTI_SPAM_ENABLED" == "true" ]] && ANTI_SPAM_ENABLED=1 || ANTI_SPAM_ENABLED=0
        ANTI_SPAM_INTERVAL=$(jq -r '.antiSpam.minIntervalSeconds // 30' "$CONFIG_FILE")
        MIN_CHANGE_SIZE=$(jq -r '.significance.minChangeSize // 50' "$CONFIG_FILE")
    else
        # Fallback: use grep/sed
        echo "[smart-checkpoint] WARNING: jq not found, using grep fallback" >&2
        ANTI_SPAM_ENABLED=$(grep -o '"enabled"[[:space:]]*:[[:space:]]*true' "$CONFIG_FILE" | head -1 | wc -l)
        ANTI_SPAM_INTERVAL=$(grep -o '"minIntervalSeconds"[[:space:]]*:[[:space:]]*[0-9]*' "$CONFIG_FILE" | grep -o '[0-9]*$' || echo "30")
        MIN_CHANGE_SIZE=50
    fi
}

load_config

# Anti-spam: check if enough time has passed since last checkpoint
should_checkpoint() {
    local session_id="${SESSION_ID:-unknown}"
    local last_checkpoint_file="$STATE_DIR/${session_id}.last"
    
    # If anti-spam disabled, always allow
    [[ "$ANTI_SPAM_ENABLED" -eq 0 ]] && return 0
    
    # If no previous checkpoint, allow
    [[ ! -f "$last_checkpoint_file" ]] && return 0
    
    local last_time=$(cat "$last_checkpoint_file")
    local current_time=$(date +%s)
    local elapsed=$((current_time - last_time))
    
    if [[ $elapsed -lt $ANTI_SPAM_INTERVAL ]]; then
        echo "[smart-checkpoint] Anti-spam: Only ${elapsed}s since last checkpoint (need ${ANTI_SPAM_INTERVAL}s)" >&2
        return 1
    fi
    
    return 0
}

# Update last checkpoint timestamp
update_checkpoint_time() {
    local session_id="${SESSION_ID:-unknown}"
    date +%s > "$STATE_DIR/${session_id}.last"
}

# Create checkpoint via ClaudePoint
create_checkpoint() {
    local description="$1"
    
    # Check if ClaudePoint is installed
    if ! command -v claudepoint &>/dev/null; then
        echo "[smart-checkpoint] ERROR: claudepoint not found. Install with: npm install -g claudepoint" >&2
        return 1
    fi
    
    # Create checkpoint and capture output
    local output
    if ! output=$(claudepoint create -d "$description" 2>&1); then
        echo "[smart-checkpoint] ERROR: claudepoint create failed:" >&2
        echo "$output" >&2
        return 1
    fi
    
    # Extract checkpoint name from output
    # Format: "Name: checkpoint_name_2025-11-16T17-14-50 [DEPLOYED]"
    local checkpoint_name
    checkpoint_name=$(echo "$output" | grep -o 'Name: [^ ]*' | cut -d' ' -f2)
    
    if [[ -z "$checkpoint_name" ]]; then
        echo "[smart-checkpoint] ERROR: Could not extract checkpoint name from output:" >&2
        echo "$output" >&2
        return 1
    fi
    
    echo "$checkpoint_name"
}

# Auto-detect library base directory
detect_lib_dir() {
    # Try project-level first (for project installs)
    if [[ -n "${CLAUDE_PROJECT_DIR:-}" ]] && [[ -d "${CLAUDE_PROJECT_DIR}/.checkpoint-rewind" ]]; then
        echo "${CLAUDE_PROJECT_DIR}/.checkpoint-rewind"
    elif [[ -n "${FACTORY_PROJECT_DIR:-}" ]] && [[ -d "${FACTORY_PROJECT_DIR}/.checkpoint-rewind" ]]; then
        echo "${FACTORY_PROJECT_DIR}/.checkpoint-rewind"
    # Fall back to user-level install
    elif [[ -d "$HOME/.checkpoint-rewind" ]]; then
        echo "$HOME/.checkpoint-rewind"
    # Legacy location
    elif [[ -d "$HOME/.local/lib/checkpoint-rewind" ]]; then
        echo "$HOME/.local/lib/checkpoint-rewind"
    else
        echo ""
    fi
}

LIB_BASE_DIR=$(detect_lib_dir)

# Get conversation context for current session
get_conversation_context() {
    local session_parser="${LIB_BASE_DIR}/parsers/SessionParser.js"
    
    # Check if SessionParser exists
    if [[ -z "$LIB_BASE_DIR" ]] || [[ ! -f "$session_parser" ]]; then
        echo "[smart-checkpoint] WARNING: SessionParser not found at $session_parser" >&2
        echo "null"
        return
    fi
    
    # Try to get current session
    local session_file
    session_file=$(node "$session_parser" current-session 2>/dev/null || echo "")
    
    if [[ -z "$session_file" ]] || [[ "$session_file" == "No session found" ]]; then
        echo "[smart-checkpoint] No active session found (code-only checkpoint)" >&2
        echo "null"
        return
    fi
    
    # Get latest user message
    local latest_msg
    latest_msg=$(node "$session_parser" latest-user 2>/dev/null || echo "null")
    
    if [[ "$latest_msg" == "null" ]] || [[ -z "$latest_msg" ]]; then
        echo "[smart-checkpoint] Could not get latest user message" >&2
        echo "null"
        return
    fi
    
    # Return JSON with session info
    echo "$latest_msg" | jq -c "{
        agent: \"$AGENT\",
        sessionId: .sessionId,
        sessionFile: \"$session_file\",
        messageUuid: .uuid,
        userPrompt: .content,
        timestamp: .timestamp
    }" 2>/dev/null || echo "null"
}

# Store conversation metadata for checkpoint
store_metadata() {
    local checkpoint_name="$1"
    local conversation_context="$2"
    
    local metadata_tool="${LIB_BASE_DIR}/metadata/ConversationMetadata.js"
    
    # Check if ConversationMetadata exists
    if [[ -z "$LIB_BASE_DIR" ]] || [[ ! -f "$metadata_tool" ]]; then
        echo "[smart-checkpoint] WARNING: ConversationMetadata not found at $metadata_tool" >&2
        return 1
    fi
    
    # If no conversation context, store minimal metadata
    if [[ "$conversation_context" == "null" ]] || [[ -z "$conversation_context" ]]; then
        conversation_context='{"agent":"'"$AGENT"'","sessionId":null}'
    fi
    
    # Store metadata
    if ! node "$metadata_tool" add "$checkpoint_name" "$conversation_context" >/dev/null 2>&1; then
        echo "[smart-checkpoint] WARNING: Failed to store conversation metadata" >&2
        return 1
    fi
    
    echo "[smart-checkpoint] Stored conversation metadata for $checkpoint_name" >&2
}

# Main workflow
main() {
    # Read hook input JSON from stdin
    local hook_input
    hook_input=$(cat)
    
    # Parse JSON fields using jq
    local session_id="unknown"
    local tool_name="unknown"
    local hook_event="unknown"
    
    if command -v jq &>/dev/null && [[ -n "$hook_input" ]]; then
        session_id=$(echo "$hook_input" | jq -r '.session_id // "unknown"')
        tool_name=$(echo "$hook_input" | jq -r '.tool_name // "unknown"')
        hook_event=$(echo "$hook_input" | jq -r '.hook_event_name // "unknown"')
    fi
    
    # Export for use in other functions
    export SESSION_ID="$session_id"
    export TOOL_NAME="$tool_name"
    
    # Determine action from argument or hook event
    local action="${1:-pre-tool-use}"
    
    case "$action" in
        pre-tool-use)
            # Check anti-spam
            if ! should_checkpoint; then
                exit 0  # Silent skip
            fi
            
            # Create checkpoint
            local description="Auto: Before ${tool_name}"
            local checkpoint_name
            if ! checkpoint_name=$(create_checkpoint "$description"); then
                echo "[smart-checkpoint] Failed to create checkpoint" >&2
                exit 1
            fi
            
            echo "[smart-checkpoint] Created checkpoint: $checkpoint_name" >&2
            
            # Get conversation context
            local context
            context=$(get_conversation_context)
            
            # Store metadata
            store_metadata "$checkpoint_name" "$context"
            
            # Update anti-spam tracker
            update_checkpoint_time
            ;;
            
        session-start)
            local description="Session start"
            local checkpoint_name
            if checkpoint_name=$(create_checkpoint "$description"); then
                echo "[smart-checkpoint] Created session-start checkpoint: $checkpoint_name" >&2
                local context=$(get_conversation_context)
                store_metadata "$checkpoint_name" "$context"
                update_checkpoint_time
            fi
            ;;
            
        post-bash)
            # For bash commands, we could check if files changed
            # For now, just create a checkpoint
            if should_checkpoint; then
                local description="Auto: After bash command"
                local checkpoint_name
                if checkpoint_name=$(create_checkpoint "$description"); then
                    echo "[smart-checkpoint] Created post-bash checkpoint: $checkpoint_name" >&2
                    local context=$(get_conversation_context)
                    store_metadata "$checkpoint_name" "$context"
                    update_checkpoint_time
                fi
            fi
            ;;
            
        stop)
            # Final checkpoint when session ends
            if should_checkpoint; then
                local description="Session end"
                local checkpoint_name
                if checkpoint_name=$(create_checkpoint "$description"); then
                    echo "[smart-checkpoint] Created session-end checkpoint: $checkpoint_name" >&2
                    local context=$(get_conversation_context)
                    store_metadata "$checkpoint_name" "$context"
                fi
            fi
            ;;
            
        *)
            echo "Usage: $0 {pre-tool-use|session-start|post-bash|stop}" >&2
            exit 1
            ;;
    esac
}

main "$@"
