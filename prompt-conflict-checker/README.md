# Prompt Conflict Checker

**UserPromptSubmit hook for Claude Code and Factory Droid CLI** that blocks long prompts, saves them for conflict analysis, and prompts you to check before proceeding. Prevents wasted context on confused iterations.

---

## What It Does

When you submit a prompt exceeding 1800 tokens (configurable):

1. **Blocks submission** (erases from context, saves ~95% tokens)
2. **Saves prompt** to `/tmp/prompt-conflicts/<timestamp>-<session>-<hash>.md`
3. **Creates symlink** at `/tmp/prompt-conflicts/latest.md`
4. **Copies `/check-conflicts` to clipboard**
5. **Slash command** tells the agent to read the saved file and highlight conflicts with git-diff colors

You see conflicts **before** any code is touched.

---

## Installation

### Claude Code

```bash
mkdir -p .claude/hooks .claude/commands
cp .claude/hooks/prompt_conflict_identifier.py .claude/hooks/
cp .claude/commands/check-conflicts.md .claude/commands/
chmod +x .claude/hooks/prompt_conflict_identifier.py
```

Add to `.claude/settings.json`:
```json
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
mkdir -p .factory/hooks .factory/commands
cp .claude/hooks/prompt_conflict_identifier.py .factory/hooks/
cp .claude/commands/check-conflicts.md .factory/commands/
chmod +x .factory/hooks/prompt_conflict_identifier.py
```

Add to `.factory/settings.json`:
```json
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

Both CLIs implement identical `UserPromptSubmit` protocols.

---

## Usage

1. Submit long prompt (>1800 tokens)
2. Hook blocks and displays:
   ```
   ✓ /check-conflicts copied to clipboard - paste and submit!
   ────────────────────────────────────────────────
   /check-conflicts
   ────────────────────────────────────────────────
   ```
3. Paste and Enter
4. Agent analyzes saved prompt, highlights conflicts
5. Fix conflicts and resubmit

**Override for a specific prompt:**
```
# skip-conflict-check
<your long prompt here>
```

---

## Configuration

Environment variables (set in `settings.json` `env` block):

| Variable | Default | Description |
|----------|---------|-------------|
| `LONG_PROMPT_THRESHOLD` | `1800` | Token count before blocking |
| `PROMPT_CONFLICT_ALWAYS_ON` | `0` | Check all prompts (ignore threshold) |
| `PROMPT_CONFLICT_ALLOW_OVERRIDE` | `1` | Enable `# skip-conflict-check` override |
| `PROMPT_CONFLICT_TMP_DIR` | `/tmp/prompt-conflicts` | Directory for saved prompts |

---

## How It Works

**Token counting:** tiktoken with `o200k_base` encoding, module-level encoder binding. Falls back to char estimate (~4 chars/token) if unavailable.

**File storage:** Timestamped files (`<timestamp>-<session>-<hash>.md`) with `latest.md` symlink so slash command always references the same path.

**Clipboard:** Auto-detects platform (macOS/Linux/WSL), tries `pbcopy`/`clip.exe`/`xclip`/`xsel`. Degrades gracefully.

**Optimizations:** match/case, dataclass slots, frozen dataclasses, cached computations.

---

## Requirements

- **Python 3.10+** (match/case, slots, native type hints)
- **tiktoken** (`pip install tiktoken`)
- **Clipboard (optional):** `pbcopy` (macOS) / `clip.exe` (Windows/WSL) / `xclip` or `xsel` (Linux)

---

## Why This Matters

Complex prompts with multiple instructions ("do X, also Y, make it Z-compliant, refactor for A, ensure B compatibility") often contain conflicting requirements. This causes:

- Wasted context on confused iterations
- Code satisfying some requirements but breaking others
- Time debugging agent confusion vs actual bugs

LLMs are excellent at identifying conflicts when explicitly asked. This hook ensures you leverage that **before** context is burned. A 2000-token prompt costs ~1950 tokens; `/check-conflicts` costs ~49 tokens (98% reduction).

---

## References

- [GPT-5.1 Prompting Guide](https://cookbook.openai.com/examples/gpt-5/gpt-5-1_prompting_guide)
- [Claude Code Hooks Reference](https://code.claude.com/docs/en/hooks.md)
- [Factory Droid Hooks Reference](https://docs.factory.ai/reference/hooks-reference.md)
- [OpenAI Codex ApplyPatch Implementation](https://github.com/openai/codex/raw/326c1e0a7eaefaf675e41c66e0b1c8033cbfdb7c/codex-rs/core/src/tools/runtimes/apply_patch.rs)

---

**License:** MIT
