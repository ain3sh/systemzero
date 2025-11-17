# Prompt Conflict Checker

**UserPromptSubmit hook for Claude Code and Factory Droid CLI** that blocks long prompts containing potentially conflicting instructions, saves them for analysis, and asks you to check for conflicts before proceeding. Prevents wasted context and confused iterations on complex prompts.

---

## What It Does

When you submit a prompt exceeding 1800 tokens (configurable):

1. **Blocks submission** (erases from context, saves ~95% tokens)
2. **Saves prompt** to `/tmp/prompt-conflicts/<timestamp>-<session>-<hash>.md`
3. **Creates symlink** at `/tmp/prompt-conflicts/latest.md` for easy access
4. **Copies `/check-conflicts` to clipboard** for instant submission
5. **Slash command expands** to instructions asking the agent to read the saved file and use `ApplyPatch` to highlight conflicts with git-diff colors (green for one instruction, red for contradictions)

You see conflicts **before** any code is touched.

---

## Installation

### Claude Code

```bash
# Copy hook and slash command to project
mkdir -p .claude/hooks .claude/commands
cp .claude/hooks/prompt_conflict_identifier.py .claude/hooks/
cp .claude/commands/check-conflicts.md .claude/commands/
chmod +x .claude/hooks/prompt_conflict_identifier.py

# Add to .claude/settings.json
{
  "env": { "LONG_PROMPT_THRESHOLD": "1800" },
  "hooks": {
    "UserPromptSubmit": [{
      "hooks": [{
        "type": "command",
        "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/prompt_conflict_identifier.py",
        "timeout": 30
      }]
    }]
  }
}
```

### Factory Droid

```bash
# Copy hook and slash command to project (just rename directory)
mkdir -p .factory/hooks .factory/commands
cp .claude/hooks/prompt_conflict_identifier.py .factory/hooks/
cp .claude/commands/check-conflicts.md .factory/commands/
chmod +x .factory/hooks/prompt_conflict_identifier.py

# Add to .factory/settings.json (same format as Claude Code)
{
  "env": { "LONG_PROMPT_THRESHOLD": "1800" },
  "hooks": {
    "UserPromptSubmit": [{
      "hooks": [{
        "type": "command",
        "command": "\"$FACTORY_PROJECT_DIR\"/.factory/hooks/prompt_conflict_identifier.py",
        "timeout": 30
      }]
    }]
  }
}
```

**Note:** Hook is CLI-agnostic. Both CLIs implement identical UserPromptSubmit protocols.

---

## Usage

**Normal workflow:**

1. Submit long prompt (>1800 tokens)
2. Hook blocks and displays:
   ```
   ✓ /check-conflicts copied to clipboard - paste and submit!
   ────────────────────────────────────────────────
   /check-conflicts
   ────────────────────────────────────────────────
   ```
3. Paste (Ctrl+V) and press Enter
4. Agent analyzes saved prompt, shows conflicts using ApplyPatch git-diff highlighting
5. Fix conflicts in your prompt and resubmit

**Override check for specific prompt:**

```
# skip-conflict-check
<your long prompt here that won't be checked>
```

---

## Configuration

Set environment variables in your CLI's `settings.json` `env` block:

| Variable | Default | Description |
|----------|---------|-------------|
| `LONG_PROMPT_THRESHOLD` | `1800` | Token count before blocking |
| `PROMPT_CONFLICT_ALWAYS_ON` | `0` | Force check all prompts (ignore threshold) |
| `PROMPT_CONFLICT_ALLOW_OVERRIDE` | `1` | Enable `# skip-conflict-check` prefix override |
| `PROMPT_CONFLICT_TMP_DIR` | `/tmp/prompt-conflicts` | Directory for saved prompts |

---

## How It Works

**Token counting:** Uses tiktoken with `o200k_base` encoding (same as GPT-4/Claude), with module-level encoder binding for speed. Falls back to character-based estimation if tiktoken unavailable.

**File storage:** Saves prompts to timestamped files (`<timestamp>-<session>-<hash>.md`) and maintains a `latest.md` symlink pointing to the most recent, so the slash command always references the same path.

**Clipboard:** Auto-detects platform (macOS/Linux/WSL) and attempts `pbcopy`, `clip.exe`, `xclip`, or `xsel`. Degrades gracefully if clipboard unavailable.

**Python 3.13 optimizations:** Match/case for platform detection, dataclass slots for memory efficiency, frozen dataclasses, cached computations (skip prefix lowercase, platform detection), minimal allocations.

---

## Requirements

- **Python 3.13+** (uses modern syntax: match/case, slots, native type hints)
- **tiktoken** (`pip install tiktoken`)
- **Clipboard tools (optional):** `pbcopy` (macOS) / `clip.exe` (Windows) / `xclip` or `xsel` (Linux)

---

## Why This Matters

For complex prompts with multiple instructions (e.g., "do X, but also do Y, make it Z-compliant, refactor for A, ensure B compatibility"), conflicting requirements cause:

- Wasted context on confused iterations
- Code that satisfies some requirements but breaks others
- Time spent debugging agent confusion vs actual bugs

LLMs are excellent at **identifying** conflicts when explicitly asked. This hook ensures you leverage that capability **before** context is burned, not after. On a 2000-token prompt, you save ~1950 tokens (98% reduction) by submitting `/check-conflicts` (49 tokens) instead.

---

## References

- ![GPT-5.1 Prompting Guide from OpenAI](https://cookbook.openai.com/examples/gpt-5/gpt-5-1_prompting_guide)

- ![Anthropic Claude Code Hooks Reference](https://code.claude.com/docs/en/hooks.md)
    - ![Claude Code Default Tools Info](https://code.claude.com/docs/en/settings#tools-available-to-claude)
    - ![Tool Control with Hooks in Claude Code](https://code.claude.com/docs/en/settings#extending-tools-with-hooks)

- ![Factory Droid CLI Hooks Reference](https://docs.factory.ai/reference/hooks-reference.md)
    - ![Droid Default Tools Info](https://docs.factory.ai/cli/configuration/custom-droids#tool-categories-→-concrete-tools)
    - ![Droid Tool Naming Differences](https://docs.factory.ai/cli/configuration/custom-droids#handling-tool-validation-errors)

- ![OpenAI Codex CLI ApplyPatch Tool Implementation](https://github.com/openai/codex/raw/326c1e0a7eaefaf675e41c66e0b1c8033cbfdb7c/codex-rs/core/src/tools/runtimes/apply_patch.rs)

---

**License:** MIT
