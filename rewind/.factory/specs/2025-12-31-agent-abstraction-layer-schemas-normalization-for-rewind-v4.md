# Agent-Abstraction Layer for Rewind v4 (Claude Code + Factory Droid now; extensible later)

## Goals

1. Make the Rewind *core* (`src/core/*`) completely agent-CLI agnostic.
2. Centralize all agent-specific details (env var names, discovery rules, transcript quirks) into declarative schemas.
3. Keep tier “when to checkpoint” logic in `tiers/` (user-tunable), not in agent schemas.
4. Support automatic agent detection primarily from SessionStart payload, with config-first overrides.
5. If no usable transcript is available, default to **code-only** and inform the user cleanly.
6. Stay **stdlib-only**.

Non-goals:
- No backward-compatible CLI surface changes beyond messaging.
- No attempt to support agents that do not have any hook mechanism (they can still use manual `rewind` + config overrides).

---

## Terminology

- **Raw hook payload**: whatever JSON the agent sends on stdin.
- **Canonical hook envelope**: Rewind’s internal normalized event shape.
- **Agent profile**: a declarative schema describing how to detect an agent and how to interpret its env/payload/transcript.

---

## Current state (baseline)

Today Rewind already assumes a near-canonical envelope for hook stdin:
- `session_id`, `transcript_path`, `cwd`, `hook_event_name`
- plus `tool_name`, `tool_input` for tool hooks

Your examples for Claude Code and Factory Droid match this closely; the major differentiator is path prefix (`~/.claude/...` vs `~/.factory/...`) and the env vars available in the hook subprocess.

Rewind also already has small transcript-agent coupling in `src/core/transcript_manager.py`:
- agent detection by transcript path/first JSON line
- event id extraction: `uuid` (Claude) vs `id` (Droid)

This spec formalizes those into a clean adapter layer.

---

## Design overview

### Core contract (agent-agnostic)
Introduce two internal data structures that everything outside the adapter layer consumes.

1) **AgentContext** (persisted to `.agent/rewind/session.json`):
- `agent_kind: str` (e.g. `"claude"`, `"droid"`, `"unknown"`)
- `project_root: str | None`
- `cwd: str | None` (observed working dir; not necessarily repo root)
- `transcript_path: str | None`
- `session_id: str | None`
- `env_file: str | None` (path to agent env-file if provided)

2) **HookEnvelope** (in-memory, per hook event):
- `hook_event_name: str` (canonical values like `SessionStart`, `PreToolUse`, ...)
- `session_id: str | None`
- `cwd: str | None`
- `transcript_path: str | None`
- `tool_name: str | None`
- `tool_input: dict | None`
- `raw: dict` (the original JSON for debugging)

`src/hooks/handler.py` should only see `HookEnvelope` (or typed wrappers derived from it), never raw agent-specific JSON.

---

## Agent selection precedence (as requested)

Order of precedence for selecting the agent profile and the core “inputs”:

1. **Config override** (`~/.rewind/config.json`):
   - If `agent` is set → force that profile.
   - If `project_root` or `transcript_path` are set → they override any hook/env discovery.

2. **SessionStart hook payload**:
   - If hook payload already contains canonical fields (`hook_event_name`, `transcript_path`, `cwd`) → use them.
   - Use schema matching to pick agent if config didn’t force one.

3. **Hook environment variables**:
   - Use agent schema to know which env vars to read.
   - Examples:
     - Claude: `CLAUDE_ENV_FILE`, `CLAUDE_PROJECT_DIR`
     - Droid: `CLAUDE_ENV_FILE`, `FACTORY_PROJECT_DIR`

4. **Fallback heuristics**:
   - If `transcript_path` exists, infer agent by path or by peeking first JSONL line (current behavior).
   - If no transcript, agent may still be inferred by env var presence.
   - Otherwise agent is `unknown`.

---

## Agent schema format

### Option A (recommended): JSON agent schemas
Store schemas as packaged data inside the wheel:
- `src/agents/schemas/claude.json`
- `src/agents/schemas/droid.json`

Load via `importlib.resources` so it works in the system install.

**Schema fields (v1):**

```json
{
  "id": "claude",
  "display_name": "Claude Code",

  "detection": {
    "score_rules": [
      {"when": {"json_path_exists": "$.transcript_path"}, "score": 2},
      {"when": {"json_path_matches": ["$.transcript_path", "\\/.claude\\/"]}, "score": 5},
      {"when": {"env_exists": "CLAUDE_PROJECT_DIR"}, "score": 4}
    ],
    "min_score": 5
  },

  "env": {
    "env_file_var": "CLAUDE_ENV_FILE",
    "project_dir_var": "CLAUDE_PROJECT_DIR"
  },

  "hooks": {
    "event_name_paths": ["$.hook_event_name", "$.hookEventName"],
    "session_id_paths": ["$.session_id", "$.sessionId"],
    "transcript_path_paths": ["$.transcript_path", "$.transcriptPath"],
    "cwd_paths": ["$.cwd"],
    "tool_name_paths": ["$.tool_name", "$.tool.name"],
    "tool_input_paths": ["$.tool_input", "$.tool.input"],

    "event_name_map": {
      "session_start": "SessionStart",
      "pre_tool_use": "PreToolUse"
    }
  },

  "transcript": {
    "last_event_id_fields": ["uuid", "id"],
    "title_prefix": {
      "enabled": true,
      "prefix": "[Fork] ",
      "json_path": "$.title"
    }
  }
}
```

Notes:
- JSONPath here is a *minimal* dotted-path implementation we own (no third-party lib):
  - Support: `$.a.b.c` and a limited `$.tool.name` style.
  - No arrays/filters in v1.
- `detection.score_rules` provides robust detection without relying solely on `transcript_path` existence.

### Option B: TOML agent schemas
Same semantic fields, but stored as TOML and parsed via stdlib `tomllib`.

---

## Where this code lives

New package:
- `src/agents/`
  - `profile.py` (dataclasses for AgentProfile)
  - `registry.py` (load packaged schemas + optional user overrides later)
  - `detect.py` (scoring + matching)
  - `jsonpath.py` (minimal extractor)
  - `normalize.py` (raw JSON → HookEnvelope)
  - `schemas/*.json` (or `*.toml`)

Existing modules updated to depend on these:
- `src/hooks/io.py`: read raw stdin JSON, call normalizer, then validate canonical envelope.
- `src/hooks/types.py`: can remain, but should be based on canonical envelope only.
- `src/hooks/handler.py`: accept canonical typed inputs; no agent branching.
- `src/core/transcript_manager.py`: remove hardcoded Claude/Droid logic and instead accept an `AgentProfile.transcript` config for:
  - agent detection hints
  - last_event_id field choices
  - title-prefix patching strategy

---

## Normalization pipeline (hook stdin)

1. Read raw JSON from stdin (dict required).
2. Determine `forced_agent` and overrides from config (if any).
3. If forced, load that agent schema; else run schema detection:
   - compute score for each schema
   - pick highest score ≥ `min_score`
   - tie-breakers: strongest rule match, then deterministic order
4. Use the selected schema’s `hooks.*_paths` to extract canonical fields.
5. Normalize event name via `event_name_map` if needed.
6. Produce `HookEnvelope(raw=original_json, ...)`.
7. Continue with existing logic (tier matchers, checkpoint policy, controller invocation).

If normalization fails:
- Never block agent operation.
- Log debug (`REWIND_DEBUG`) and exit success (or non-blocking error) depending on hook type.

---

## Project root and env-file handling

### Inputs
We will treat `project_root` / `project_dir` as discoverable via:
- config override (`project_root`)
- hook payload `cwd`
- env var from schema: `CLAUDE_PROJECT_DIR` / `FACTORY_PROJECT_DIR`

### Behavior
- `cwd` is not guaranteed to be repo root; we will keep current repo-root inference logic (if any exists) or implement a standard approach:
  - walk up from `cwd` to find `.git/` (bounded depth)
  - if found, that is `project_root`; else `cwd`.

### `CLAUDE_ENV_FILE`
- `env_file` path comes from env var `env.env_file_var`.
- Rewind may write a small set of stable env vars for convenience (optional but recommended):
  - `REWIND_AGENT_KIND`
  - `REWIND_PROJECT_ROOT`
  - `REWIND_TRANSCRIPT_PATH`
- Writing is **best-effort**, never fatal.
- This makes CLI runs outside hooks still “know” context when launched by the agent.

(If you prefer not to write any env vars at all, we can omit this and only *read* the env file location for future features.)

---

## Transcript support and safe fallback (code-only)

### Capability model
Agent schema declares transcript capabilities:
- `transcript.title_prefix.enabled` (default false if missing)
- `transcript.last_event_id_fields` (default `["uuid", "id"]`)

### Runtime rules
- If `transcript_path` is missing/unreadable:
  - checkpoint creation still succeeds as code-only.
  - checkpoint metadata indicates `hasTranscript=false`.
  - CLI messaging:
    - `rewind save`: `chat: unavailable`
    - `rewind jump`: `Chat rewind unavailable (no transcript found)`

### Safety
- Title prefixing is only attempted if schema declares it.
- All transcript modifications remain best-effort and non-blocking.

---

## How tiers remain agent-agnostic

Tiers should operate on canonical `HookEnvelope` properties:
- `hook_event_name` (canonical)
- `tool_name` (canonical)

If a future agent uses different tool naming, that mapping belongs in the agent schema (`tool_name_paths` + optional normalization map), not in tiers.

---

## Migration plan

1. Introduce agent schema loading + detection but keep existing typed parsing as fallback.
2. Switch `read_input()` in `src/hooks/io.py` to:
   - read raw JSON
   - normalize
   - then produce typed inputs (`SessionStartInput`, `PreToolUseInput`, etc.) from canonical fields
3. Move transcript coupling (`detect_agent`, `uuid vs id`) into schema-driven logic.
4. Add tests and ensure existing tests still pass.

---

## Testing plan (must-pass)

Unit tests (stdlib + pytest):

1. **Schema detection**
   - Given your Claude/Droid sample payloads, ensure the correct schema is selected.
   - Ensure config override forces schema choice regardless of payload.

2. **Normalization**
   - For canonical payloads (like your examples), ensure we get a correct `HookEnvelope`.
   - For non-canonical variants (camelCase fields), ensure extraction works.

3. **Env var extraction**
   - When `CLAUDE_PROJECT_DIR` / `FACTORY_PROJECT_DIR` present, ensure `project_root` discovery uses it (unless overridden by config).
   - Ensure `CLAUDE_ENV_FILE` is read and (if enabled) written best-effort.

4. **Transcript behavior remains safe**
   - If transcript path missing, `create_checkpoint` returns `hasTranscript=false` and does not error.
   - Restore/jump prints a clean “chat unavailable” signal (no exception).

Acceptance criteria:
- All existing tests pass.
- New tests cover schema selection + normalization.
- No agent-specific branching remains in `src/hooks/handler.py` or `src/core/*`.
- Adding a new agent should require only:
  - adding `src/agents/schemas/<agent>.json` (and optionally updating docs/tests)

---

## Open questions (optional, but good to settle)

1. Should Rewind write env vars to `CLAUDE_ENV_FILE` immediately on SessionStart, or only when requested?
2. Do you want schema overrides in `~/.rewind/agents/<id>.json` in the future, or keep it “packaged-only” forever?

If you confirm this spec, I will implement Option A (JSON schemas) unless you choose Option B.