## Goals
- Make the Python package layout *obvious* and *single-source-of-truth* under `rewind/src/` (no `src/rewind/` nesting).
- Eliminate “config.py everywhere” ambiguity and consolidate static JSON assets (tiers + agent schemas) into one place.
- No backwards-compat re-exports/stubs: all imports and entrypoints are updated to the new structure, and old module paths are removed.
- Keep the public CLI behavior the same (`rewind …` commands), but it’s fine if the Python entrypoint path changes.

## Non-goals
- No behavior changes to checkpointing/rewinding logic beyond what’s required to move modules and load resources.
- No repo-wide cleanup outside `rewind/` unless explicitly requested.

## Proposed target tree (within `rewind/`)
```
rewind/
  bin/
    rewind
    smart-checkpoint
  src/
    __init__.py
    __main__.py            # new: allows `python -m src` (optional but nice)

    app/
      __init__.py
      cli.py               # new home for CLI parsing + command dispatch

    core/                  # unchanged: core domain logic
      __init__.py
      controller.py
      transcript_manager.py
      checkpoint_store.py

    hooks/                 # unchanged path OR move under integrations (see below)
      __init__.py
      __main__.py
      handler.py
      io.py
      types.py

    config/
      __init__.py
      loader.py            # stays
      types.py             # rename from `schemas.py` (it’s code types, not JSON schemas)

    integrations/
      __init__.py
      agents/
        __init__.py
        detect.py
        normalize.py
        envfile.py
        jsonpath.py
        project_root.py
        registry.py
        types.py

    utils/
      __init__.py
      env.py
      fs.py
      hook_merger.py
      hook_merger_testdata.py (optional)

    resources/
      agents/
        claude.json
        droid.json
      tiers/
        minimal.json
        balanced.json
        aggressive.json
      rewind-checkpoint-ignore.json

  tests/
    ...

  install.sh
  pyproject.toml
```

### Notes
- I’m proposing `src/integrations/agents/` to clearly separate “agent integration” from “core rewind logic”. This replaces the current `src/agents/`.
- I left `src/hooks/` in place in this plan to minimize churn, but we can also move it under `src/integrations/hooks/` if you want a stricter separation. (Either way is fine; pick one and we’ll do it consistently.)

## File moves (explicit mapping)
### Agent integration
- `src/agents/*` → `src/integrations/agents/*`
- `src/agents/schemas/*.json` → `src/schemas/agents/*.json`

### Config
- `src/config/schemas.py` → `src/config/types.py`
- Keep `src/config/loader.py` where it is, update imports accordingly.

### Tiers / static assets
- `tiers/*.json` → `src/schemas/tiers/*.json`
- `bin/rewind-checkpoint-ignore.json` → `src/schemas/rewind-checkpoint-ignore.json`

### CLI entrypoint
- `src/cli.py` → `src/app/cli.py`
- Add `src/__main__.py` that calls `src.app.cli:main`.

## Code updates required
### Imports
- Update all intra-package imports to new module paths (e.g. `from src.agents.detect import …` → `from src.integrations.agents.detect import …`).
- Update places that refer to tier JSON paths or agent schema JSON paths to use the new `src/schemas/...` location.

### Resource loading
- Replace any hard-coded filesystem paths like `Path(__file__).parent / "schemas" / …` with a single helper:
  - `src/utils/resources.py` (new) providing:
  - `get_resource_path("tiers/balanced.json")` for “installed files on disk” use-cases
    - and/or `read_text_resource(...)` using `importlib.resources` for packaged resources.
- Use that helper everywhere tiers/schemas/ignore-config are needed.

### Packaging (`pyproject.toml`)
- Update `[project.scripts]` from `rewind = "src.cli:main"` to `rewind = "src.app.cli:main"`.
- Update `[tool.setuptools.package-data]` from `agents/schemas/*.json` to:
  - `schemas/agents/*.json`
  - `schemas/tiers/*.json`
  - `schemas/rewind-checkpoint-ignore.json`

### Installer (`install.sh`)
- Remove the separate `cp -r "$REPO_ROOT/tiers" ...` step because tiers live inside `src/` now.
- Update `TIER_FILE` to point at the installed location:
  - `TIER_FILE="$INSTALL_DIR/src/schemas/tiers/${SELECTED_TIER}.json"`
- Update any other references that assumed `$INSTALL_DIR/tiers/...`.

### Binaries
- `bin/smart-checkpoint` runs `python3 -m src.integrations.hooks ...`.
- `bin/rewind` can remain a thin shim, but should import `src.app.cli:main`.

## Test plan (automated)
- Update existing tests’ imports to match the moved modules.
- Add a focused test ensuring tier JSON + agent schema JSON resolve via the new resource helper.
- Run:
  - `pytest -q`
  - `python3 -m compileall src`
  - `python3 -m src --help` (or `rewind --help` once installed)

## Manual smoke plan
- Run `./install.sh` locally and choose “re-register hooks”.
- Verify `~/.factory/settings.json` keeps OpenSkills entries untouched and gains the Rewind hooks for the selected tier.
- Start a Droid session and verify:
  - `SessionStart` hook runs and creates/extends env-file entries
  - `rewind save` and `rewind back 1` behave as documented

## Open decision (pick one)
- **Hooks location**:
  - **Option A (lower churn):** keep hooks at `src/hooks/*` (only update CLI + integrations + resources).
  - **Option B (cleaner separation):** move hooks under `src/integrations/hooks/*` and update `bin/smart-checkpoint` + any imports accordingly.