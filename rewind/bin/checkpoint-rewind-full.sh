#!/bin/bash
# checkpoint-rewind-full.sh
# Full rewind: code + conversation
#
# Usage: checkpoint-rewind-full.sh <checkpoint-name> [project-root]

set -euo pipefail

CHECKPOINT_NAME="${1:-}"
PROJECT_ROOT="${2:-.}"

if [[ -z "$CHECKPOINT_NAME" ]]; then
    echo "Usage: checkpoint-rewind-full.sh <checkpoint-name> [project-root]"
    echo ""
    echo "Full rewind: restores code AND conversation to checkpoint state"
    echo ""
    echo "Examples:"
    echo "  checkpoint-rewind-full.sh auto_before_edit_2025-11-16T12-00-00"
    echo "  checkpoint-rewind-full.sh my-checkpoint ~/project"
    exit 1
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔄 Full Rewind: Code + Conversation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 1. Read checkpoint metadata
echo "📖 Reading checkpoint metadata..."
METADATA_FILE="$PROJECT_ROOT/.claudepoint/conversation_metadata.json"

if [[ ! -f "$METADATA_FILE" ]]; then
    echo "❌ No conversation metadata found"
    echo "   File: $METADATA_FILE"
    echo ""
    echo "   This checkpoint has no conversation context."
    echo "   Use 'claudepoint undo' for code-only restore."
    exit 1
fi

METADATA=$(cat "$METADATA_FILE" | jq -r ".\"$CHECKPOINT_NAME\"")

if [[ "$METADATA" == "null" ]]; then
    echo "❌ Checkpoint not found in metadata: $CHECKPOINT_NAME"
    echo ""
    echo "Available checkpoints:"
    cat "$METADATA_FILE" | jq -r 'keys[]' | head -10
    exit 1
fi

SESSION_ID=$(echo "$METADATA" | jq -r '.sessionId')
SESSION_FILE=$(echo "$METADATA" | jq -r '.sessionFile')
MESSAGE_UUID=$(echo "$METADATA" | jq -r '.messageUuid')
USER_PROMPT=$(echo "$METADATA" | jq -r '.userPrompt')
AGENT=$(echo "$METADATA" | jq -r '.agent')

# Handle null values gracefully
if [[ "$SESSION_ID" == "null" ]] || [[ -z "$SESSION_ID" ]]; then
    echo "❌ No session ID in checkpoint metadata"
    echo "   This is a code-only checkpoint."
    echo "   Use 'claudepoint undo' instead."
    exit 1
fi

echo "   Session: $SESSION_ID"
echo "   Message: $MESSAGE_UUID"
echo "   Prompt: ${USER_PROMPT:0:60}..."
echo ""

# 2. Restore code via ClaudePoint
echo "💾 Restoring code from checkpoint..."
cd "$PROJECT_ROOT"

if ! claudepoint undo "$CHECKPOINT_NAME" 2>&1; then
    echo "❌ Code restore failed"
    exit 1
fi

echo "✅ Code restored"
echo ""

# 3. Truncate conversation
echo "✂️  Truncating conversation..."

# Find ConversationTruncator
TRUNCATOR=""
if [[ -f "$(dirname "$0")/../lib/rewind/ConversationTruncator.js" ]]; then
    TRUNCATOR="$(dirname "$0")/../lib/rewind/ConversationTruncator.js"
elif [[ -f "$HOME/.checkpoint-rewind/rewind/ConversationTruncator.js" ]]; then
    TRUNCATOR="$HOME/.checkpoint-rewind/rewind/ConversationTruncator.js"
elif [[ -f "$HOME/.local/lib/checkpoint-rewind/rewind/ConversationTruncator.js" ]]; then
    TRUNCATOR="$HOME/.local/lib/checkpoint-rewind/rewind/ConversationTruncator.js"
else
    echo "❌ ConversationTruncator not found"
    echo "   Looked in:"
    echo "     - $(dirname "$0")/../lib/rewind/ConversationTruncator.js"
    echo "     - $HOME/.checkpoint-rewind/rewind/ConversationTruncator.js"
    echo "     - $HOME/.local/lib/checkpoint-rewind/rewind/ConversationTruncator.js (legacy)"
    echo ""
    echo "   Code has been restored, but conversation is unchanged."
    exit 1
fi

if ! node "$TRUNCATOR" "$SESSION_FILE" "$MESSAGE_UUID" --verbose; then
    echo ""
    echo "❌ Conversation truncation failed"
    echo ""
    echo "   Code has been restored, but conversation is unchanged."
    echo "   You can manually restore conversation or continue with current context."
    echo ""
    echo "   To manually truncate:"
    echo "     node $TRUNCATOR $SESSION_FILE $MESSAGE_UUID"
    exit 1
fi

echo "✅ Conversation truncated"
echo ""

# 4. Display resume instructions
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎉 Rewind Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Both code and conversation have been restored."
echo ""
echo "Next steps:"
echo "  1. Exit your current agent session (Ctrl+C or quit)"
echo "  2. Resume with truncated conversation:"
echo ""

case "$AGENT" in
    claude-code)
        echo "     claude --resume $SESSION_ID"
        ;;
    droid-cli)
        echo "     droid --resume $SESSION_ID"
        ;;
    *)
        echo "     <agent> --resume $SESSION_ID"
        ;;
esac

echo ""
echo "Your agent will restart with the conversation context"
echo "as it was at checkpoint: $CHECKPOINT_NAME"
echo ""
echo "📁 Backups created:"
echo "   Code: .claudepoint/snapshots/$CHECKPOINT_NAME (ClaudePoint emergency backup)"
echo "   Conversation: $SESSION_FILE.backup.* (timestamped)"
echo ""
