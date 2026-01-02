---
title: Contributing
---

# Contributing to Rewind

This repo is intentionally **stdlib-only** and optimized for **hook-driven agent environments**.

The easiest way to contribute (and the most common PR type we want) is improving or adding **agent schemas**.

## Agent schemas (preferred extension point)

Agent-specific behavior is defined in JSON files under:

- `src/schemas/agents/`

Each schema is designed to keep the rest of Rewind agent-agnostic.

### What schemas control

Schemas define:

- **Detection**: how to identify an agent from hook payloads and hook environment variables.
- **Hook normalization**: where to extract canonical fields like `hook_event_name`, `cwd`, `transcript_path`, etc.
- **Transcript quirks**: how to extract the last event id (e.g. `uuid` vs `id`) and whether title-prefixing is enabled.

### Canonical hook envelope

Internally, Rewind normalizes hook input into a canonical shape that matches Claude Code / Factory Droid:

- `hook_event_name`
- `session_id`
- `cwd`
- `transcript_path`
- `tool_name` + `tool_input` (for tool hooks)

If a new agent’s hook payload differs (camelCase, nesting, different keys), you should fix that **in the schema** via the `hooks.*_paths` lists.

## Updating an existing agent schema

Common edits:

- Change env var names (e.g. if an agent renames its env-file variable).
- Add alternative JSON paths (e.g. `$.transcriptPath` as well as `$.transcript_path`).
- Adjust detection weights (to avoid ambiguous matches).

Guidelines:

- Keep `detection.min_score` high enough that random JSON doesn’t match.
- Prefer detection signals that are stable (e.g. transcript path directory markers).
- Keep normalization paths minimal and explicit.

## Adding a new agent schema

1. Copy an existing schema (e.g. `src/schemas/agents/claude.json`).
2. Set:
   - `id` (short, stable identifier)
   - `display_name`
3. Implement detection rules in `detection.score_rules`:
   - `json_path_exists`: checks for field presence
   - `json_path_matches`: regex match against a string field
   - `env_exists`: checks for presence of an env var
4. Map hook fields in `hooks.*_paths`.
5. Configure transcript handling in `transcript.*`:
   - `path_regexes`: regexes used to classify transcript paths
   - `last_event_id_fields`: ordered list of keys to try for “last event id”
   - `title_prefix`: set `enabled` and keep `json_path` as `$.title` (v1)

## Environment-file behavior

On `SessionStart`, if the agent provides an env-file path, Rewind appends:

- `REWIND_AGENT_KIND`
- `REWIND_PROJECT_ROOT`
- `REWIND_TRANSCRIPT_PATH` (if known)

to the env file. This is intentionally **append-only**.

## Tests and validation

Before opening a PR:

```bash
python3 -m compileall -q src tests
python3 -m pytest
```

If you add a new agent schema, please also add a test case in `tests/test_agents.py` with representative payload(s).
