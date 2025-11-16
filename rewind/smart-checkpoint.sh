#!/bin/bash
# Smart Checkpoint Hook for Claude Code
# Integrates with ClaudePoint or Rewind-MCP to create intelligent checkpoints
#
# Usage: smart-checkpoint.sh <action> <session_id> [additional_args]
# Actions: pre-modify, analyze-prompt, session-start, batch-detect

set -euo pipefail

# Configuration
STATE_DIR="${HOME}/.claude-checkpoints"
MIN_CHECKPOINT_INTERVAL=30  # seconds
MIN_CHANGE_SIZE=50          # characters
BATCH_WINDOW=60             # seconds
BATCH_THRESHOLD=3           # operations

# Ensure state directory exists
mkdir -p "$STATE_DIR"

# ============================================================================
# Utility Functions
# ============================================================================

log_info() {
    echo "ℹ️  $*" >&2
}

log_skip() {
    echo "⏭️  Skipped: $*" >&2
}

log_success() {
    echo "✅ $*" >&2
}

log_error() {
    echo "❌ Error: $*" >&2
}

log_warn() {
    echo "⚠️  Warning: $*" >&2
}

# ============================================================================
# Checkpoint Decision Logic
# ============================================================================

should_checkpoint_by_time() {
    local session_id="$1"
    local last_checkpoint_file="$STATE_DIR/$session_id.last"

    if [ ! -f "$last_checkpoint_file" ]; then
        return 0  # No previous checkpoint, allow
    fi

    local last_time
    last_time=$(cat "$last_checkpoint_file")
    local now
    now=$(date +%s)
    local elapsed=$((now - last_time))

    if [ "$elapsed" -lt "$MIN_CHECKPOINT_INTERVAL" ]; then
        log_skip "Too soon since last checkpoint (${elapsed}s < ${MIN_CHECKPOINT_INTERVAL}s)"
        return 1
    fi

    return 0
}

update_last_checkpoint_time() {
    local session_id="$1"
    local last_checkpoint_file="$STATE_DIR/$session_id.last"
    date +%s > "$last_checkpoint_file"
}

detect_significance() {
    local file_path="$1"
    local change_size="$2"

    # Critical configuration files always checkpoint
    if echo "$file_path" | grep -qE "(package\.json|requirements\.txt|Dockerfile|docker-compose\.yml|\.env\.example|tsconfig\.json|webpack\.config\.js|vite\.config\.|next\.config\.)"; then
        log_info "Critical config file detected: $file_path"
        return 0
    fi

    # Excluded patterns (generated/temp files)
    if echo "$file_path" | grep -qE "(node_modules/|\.git/|__pycache__/|\.next/|dist/|build/|\.log$|\.tmp$)"; then
        log_skip "Excluded file pattern: $file_path"
        return 1
    fi

    # Large changes always significant
    if [ "$change_size" -gt 500 ]; then
        log_info "Large change detected (${change_size} chars)"
        return 0
    fi

    # Skip tiny changes in test/doc files
    if echo "$file_path" | grep -qE "(test|spec|\.test\.|\.spec\.|\.md$|\.txt$|README)" && [ "$change_size" -lt 100 ]; then
        log_skip "Trivial change in test/doc file (${change_size} chars)"
        return 1
    fi

    # Default: significant enough to checkpoint
    return 0
}

# ============================================================================
# Batch Operation Detection
# ============================================================================

increment_operation_count() {
    local session_id="$1"
    local count_file="$STATE_DIR/$session_id.op_count"
    local timestamp_file="$STATE_DIR/$session_id.op_timestamp"

    local count=0
    local first_timestamp
    first_timestamp=$(date +%s)

    # Read existing count and timestamp
    if [ -f "$count_file" ]; then
        count=$(cat "$count_file")
        first_timestamp=$(cat "$timestamp_file")
    fi

    # Check if we're outside the batch window
    local now
    now=$(date +%s)
    local elapsed=$((now - first_timestamp))

    if [ "$elapsed" -gt "$BATCH_WINDOW" ]; then
        # Reset window
        count=0
        first_timestamp=$now
    fi

    # Increment count
    count=$((count + 1))
    echo "$count" > "$count_file"
    echo "$first_timestamp" > "$timestamp_file"

    # Return whether we've hit batch threshold
    if [ "$count" -ge "$BATCH_THRESHOLD" ]; then
        log_warn "Batch operation detected ($count operations in ${elapsed}s)"
        return 0  # Batch detected
    fi

    return 1
}

# ============================================================================
# Checkpoint Execution
# ============================================================================

create_checkpoint() {
    local description="$1"

    # Try ClaudePoint first (preferred - has persistence)
    if command -v claudepoint >/dev/null 2>&1; then
        if claudepoint create -d "$description" >/dev/null 2>&1; then
            log_success "Checkpoint created: $description"
            return 0
        else
            log_warn "ClaudePoint checkpoint failed"
        fi
    fi

    # Try MCP checkpoint tool (via stdio communication)
    # Note: This requires the Rewind-MCP server to be configured
    if [ -n "${CLAUDE_MCP_AVAILABLE:-}" ]; then
        # Output MCP tool call request
        # (This is a simplified version - actual MCP communication is more complex)
        cat <<EOF
{
  "tool": "checkpoint",
  "arguments": {
    "files": ["."],
    "description": "$description"
  }
}
EOF
        log_success "MCP checkpoint requested: $description"
        return 0
    fi

    log_error "No checkpoint tool available (install claudepoint or configure Rewind-MCP)"
    return 1
}

# ============================================================================
# Action Handlers
# ============================================================================

handle_pre_modify() {
    local session_id="$1"
    local tool_name="$2"

    # Read stdin for tool parameters (JSON)
    local input
    input=$(cat)

    # Extract relevant fields based on tool
    local file_path=""
    local change_size=0

    case "$tool_name" in
        Edit)
            file_path=$(echo "$input" | jq -r '.file_path // ""' 2>/dev/null || echo "")
            local new_string
            new_string=$(echo "$input" | jq -r '.new_string // ""' 2>/dev/null || echo "")
            change_size=${#new_string}
            ;;
        Write)
            file_path=$(echo "$input" | jq -r '.file_path // ""' 2>/dev/null || echo "")
            local content
            content=$(echo "$input" | jq -r '.content // ""' 2>/dev/null || echo "")
            change_size=${#content}
            ;;
        NotebookEdit)
            file_path=$(echo "$input" | jq -r '.notebook_path // ""' 2>/dev/null || echo "")
            local new_source
            new_source=$(echo "$input" | jq -r '.new_source // ""' 2>/dev/null || echo "")
            change_size=${#new_source}
            ;;
        *)
            log_info "Unknown tool: $tool_name"
            exit 0
            ;;
    esac

    # Check if change is too small
    if [ "$change_size" -lt "$MIN_CHANGE_SIZE" ]; then
        log_skip "Change too small ($change_size < $MIN_CHANGE_SIZE chars)"
        exit 0
    fi

    # Check time-based anti-spam
    if ! should_checkpoint_by_time "$session_id"; then
        exit 0
    fi

    # Check significance
    if [ -n "$file_path" ]; then
        if ! detect_significance "$file_path" "$change_size"; then
            exit 0
        fi
    fi

    # Check for batch operations
    if increment_operation_count "$session_id"; then
        # Batch detected - create checkpoint before continuing
        if create_checkpoint "Auto: Batch operation detected"; then
            update_last_checkpoint_time "$session_id"
        fi
        exit 0
    fi

    # Create checkpoint
    local file_basename
    file_basename=$(basename "$file_path" 2>/dev/null || echo "unknown")
    if create_checkpoint "Auto: Before $tool_name on $file_basename"; then
        update_last_checkpoint_time "$session_id"
    fi
}

handle_analyze_prompt() {
    local session_id="$1"

    # Read prompt from stdin (JSON)
    local input
    input=$(cat)
    local prompt
    prompt=$(echo "$input" | jq -r '.prompt // ""' 2>/dev/null || echo "")

    # Convert to lowercase for matching
    local prompt_lower
    prompt_lower=$(echo "$prompt" | tr '[:upper:]' '[:lower:]')

    # Risky keyword patterns
    local risky_patterns=(
        "refactor all"
        "entire codebase"
        "delete.*files"
        "remove all"
        "migrate all"
        "convert all"
        "update everything"
        "rewrite.*all"
        "change.*every"
        "replace.*all"
    )

    # Check for risky patterns
    for pattern in "${risky_patterns[@]}"; do
        if echo "$prompt_lower" | grep -qE "$pattern"; then
            log_warn "Risky prompt detected: matches '$pattern'"

            # Create checkpoint regardless of time
            local truncated_prompt="${prompt:0:50}"
            if create_checkpoint "Auto: Before bulk operation: $truncated_prompt..."; then
                update_last_checkpoint_time "$session_id"
            fi
            exit 0
        fi
    done

    # No risky patterns detected
    log_info "Prompt analysis: No risky patterns detected"
    exit 0
}

handle_session_start() {
    local session_id="$1"
    local source="${2:-unknown}"

    # Only checkpoint on actual startup or resume, not after compact
    if [ "$source" = "startup" ] || [ "$source" = "resume" ]; then
        log_info "Session $source detected"

        if create_checkpoint "Auto: Session $source"; then
            update_last_checkpoint_time "$session_id"
        fi
    else
        log_skip "Session source '$source' does not require checkpoint"
    fi
}

handle_batch_detect() {
    local session_id="$1"

    # This is called when we want to explicitly check for batch operations
    # without necessarily creating a checkpoint

    if increment_operation_count "$session_id"; then
        log_warn "Batch operation in progress"
        exit 0
    fi

    log_info "No batch operation detected"
    exit 0
}

# ============================================================================
# Main Entry Point
# ============================================================================

main() {
    if [ $# -lt 2 ]; then
        echo "Usage: $0 <action> <session_id> [args...]" >&2
        echo "Actions: pre-modify, analyze-prompt, session-start, batch-detect" >&2
        exit 1
    fi

    local action="$1"
    local session_id="$2"
    shift 2

    # Validate session_id is reasonable
    if [ -z "$session_id" ] || [ "$session_id" = "null" ]; then
        log_error "Invalid session_id: $session_id"
        exit 0  # Non-blocking
    fi

    # Route to appropriate handler
    case "$action" in
        pre-modify)
            if [ $# -lt 1 ]; then
                log_error "pre-modify requires tool_name argument"
                exit 0
            fi
            handle_pre_modify "$session_id" "$1"
            ;;
        analyze-prompt)
            handle_analyze_prompt "$session_id"
            ;;
        session-start)
            local source="${1:-unknown}"
            handle_session_start "$session_id" "$source"
            ;;
        batch-detect)
            handle_batch_detect "$session_id"
            ;;
        *)
            log_error "Unknown action: $action"
            exit 1
            ;;
    esac
}

# Run main function
main "$@"
