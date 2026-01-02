## Goals
1. Make “tiers” **thin presets** over a unified config (single source of truth for runtime knobs), while keeping the preset UX (`minimal|balanced|aggressive`).
2. Broaden `SessionStart` to handle `startup|resume|clear|compact` and **rewrite** the SessionStart hook logic cleanly (idempotent, low-noise, non-blocking).

---

## Current Problems Observed
- `~/.rewind/config.json` currently stores `{"tier": "balanced", "runtime": {...}}`, but `RewindConfig.from_dict()` expects `tier` to be an object; this is a latent correctness bug for any code path that touches `ConfigLoader.config`.
- Tier JSON files in `src/schemas/tiers/*.json` currently hardcode `SessionStart.matcher: "startup"` which is narrower than Droid’s documented sources.
- Hook runtime logic currently skips all non-`startup` SessionStart sources entirely.

---

## Decision: What “thin presets” means
- Presets live in `rewind/src/schemas/tiers/*.json` (we keep the files; they are now treated as “presets”).
- User config becomes the **single place** to pick a preset and optionally override runtime knobs.
- Preset files provide **defaults** (runtime + hook registration entries), not something we always copy into `~/.rewind/config.json`.

---

## Canonical Config Shape (Unified)
### Global config: `~/.rewind/config.json`
Canonical keys:
```json
{
  "preset": "balanced",
  "storage": {"mode": "project"},
  "runtime": {"antiSpam": {...}, "significance": {...}}
}
```
- `preset` is the chosen preset name.
- `runtime` is **optional** and represents overrides on top of preset defaults.

### Back-compat keys (Option A only)
Support reading:
- `tier` as a string alias for `preset`.
- `tier` as an object (legacy/experimental) treated as runtime overrides.

---

## Preset File Shape (No change required, just semantics)
Keep existing JSON files:
- `rewind/src/schemas/tiers/minimal.json`
- `rewind/src/schemas/tiers/balanced.json`
- `rewind/src/schemas/tiers/aggressive.json`

They remain:
```json
{
  "tier": "balanced",
  "runtime": {...},
  "hooks": {...}
}
```
But we treat them as preset definitions.

---

## Effective Runtime Resolution
Given merged config (global + project override):
1. Determine `preset` from `preset` or `tier` string (default `balanced`).
2. Load preset defaults from `schemas/tiers/{preset}.json` → `preset_runtime`.
3. Compute `effective_runtime = deep_merge(preset_runtime, runtime_overrides)`.
4. Build `TierConfig` from `effective_runtime` (antiSpam/significance), and carry the chosen preset name.

This makes presets “thin” because config only needs `preset`, and overrides only appear when user explicitly adds them.

---

## Installer Changes (`rewind/install.sh`)
- Keep the interactive selection UX and `TIER_FILE` path, but:
  - For fresh installs: write `~/.rewind/config.json` containing only:
    - `preset` (selected)
    - `storage.mode` (preserve current behavior)
  - For updates: preserve any existing `runtime` overrides in config.
- Update the “existing tier” detection logic to read `preset` first, else `tier`.
- Hook registration continues to pass `TIER_FILE` to `python3 -m src.utils.hook_merger` (no schema changes needed there).

---

## Code Changes: Config (clean, centralized)
### Files
- `rewind/src/config/loader.py`
- `rewind/src/config/types.py`
- (optionally) `rewind/src/config/__init__.py` exports

### `ConfigLoader.load()` becomes responsible for producing an internally-consistent `RewindConfig`
- Parse storage mode.
- Resolve preset name.
- Apply preset+override merge to construct `TierConfig`.
- Fix the latent bug where `tier` can be a string.

### `RewindConfig.from_dict()` and `TierConfig.from_dict()` adjustments
- Accept `tier` being a string or dict.
- Accept top-level `runtime` and merge it into the tier runtime (per resolution rules).

(Option B removes all alias logic and enforces only `preset` + `runtime`.)

---

## Code Changes: Hooks (clean overwrite)
### Files
- `rewind/src/integrations/hooks/handler.py`
- `rewind/src/integrations/hooks/__main__.py`
- Add: `rewind/src/integrations/hooks/policy.py` (new)
- Update presets: `rewind/src/schemas/tiers/{minimal,balanced,aggressive}.json`

### Preset matcher widening
Change `hooks.SessionStart[0].matcher` to:
- `"startup|resume|clear|compact"` in all 3 preset JSONs.

### Hook processing refactor
Introduce a small structured return type instead of a bare `bool`:
- `HookOutcome(checkpoint_created: bool, context_messages: list[str], warnings: list[str])`

Update `__main__.py`:
- On `SessionStart`: emit `context_messages` via `emit_context(...)`.
- Print `warnings` to stderr.
- Always `exit_success()` (non-blocking).

### SessionStart policy (in `policy.py`)
Inputs:
- `source: SessionStartSource`
- `transcript_path: str | None`
- `checkpoints: list[CheckpointMetadata]`

Rules:
1. Always save session metadata / env exports (already done).
2. If `source in {resume, clear, compact}`: reset anti-spam state.
3. `startup`: always create baseline checkpoint (`"Session start"`).
4. `resume|clear|compact`: create a baseline checkpoint **only if** no existing checkpoint is associated to the current transcript.
   - “Associated” = checkpoint metadata contains `transcript.original_path` (or fallback `transcript.path`) matching the current transcript path after `expanduser()`.
5. Warnings (non-blocking):
   - On `resume` only:
     - if transcript path missing: warn that coverage cannot be verified.
     - if no existing checkpoint and baseline was created: warn once that baseline was created for safety.

Descriptions:
- resume → `Session resume`
- clear → `Session clear`
- compact → `Session compact`

---

## Tests
### 1) Config resolution tests
Add `rewind/tests/test_config_presets.py`:
- Monkeypatch `HOME` to tmpdir.
- Write `~/.rewind/config.json` in different shapes:
  - legacy: `{ "tier": "balanced", "runtime": {...} }`
  - canonical: `{ "preset": "balanced" }`
  - overrides: `{ "preset": "balanced", "runtime": {"antiSpam": {"minIntervalSeconds": 5}} }`
- Assert `ConfigLoader(project_root=tmp_project).config.storage_mode` and `config.tier.*` resolved as expected.

### 2) SessionStart policy tests
Add `rewind/tests/test_session_start_policy.py`:
- Build fake checkpoints with transcript metadata and verify baseline decision.
- Verify anti-spam reset behavior flips `_should_checkpoint()` to allow immediate checkpoint after resume/clear/compact.

---

## Validation
After implementation:
- Run `pytest` for `rewind/`.
- Run `./rewind/install.sh` (non-interactive) to ensure:
  - `~/.rewind/config.json` is written in canonical form.
  - hooks register correctly for Claude + Droid.

---

## Options
### Option A: Backward-compatible config/presets (recommended)
- Loader accepts `tier` (string) and `runtime` from existing installs.
- Installer writes `preset` for new installs and preserves `runtime` on update.

### Option B: Breaking config rewrite
- Enforce only `preset` + optional `runtime`.
- Installer rewrites `~/.rewind/config.json` into canonical form unconditionally.
- Loader drops support for `tier` aliases.
