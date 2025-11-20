Goal: Validate the Rewind-native checkpoint integration end-to-end using realistic workflows rather than static analysis.

Plan:
1. Environment Prep (read-only):
   - Confirm repo status (`git status -sb`) and note existing .rewind contents (ls .rewind/...).
   - Ensure Node + tar, jq available (already assumed, but double-check versions).

2. Installer Dry Run Sanity:
   - Run `bin/install-hooks.sh --dry-run` for user-level to confirm .rewind targets in logs without writing.

3. Local Hook Simulation Tests (actual execution):
   - Use `echo ... | bin/smart-checkpoint.sh session-start` to create structural checkpoint; expect .rewind/code/snapshots entry and metadata entry.
   - Use `echo ... | bin/smart-checkpoint.sh pre-tool-use` twice rapidly to confirm anti-spam skip behavior (second invocation should log skip and avoid new snapshot).
   - Use `echo ... | bin/smart-checkpoint.sh post-bash` with simulated session to ensure volumetric path writing metadata.

4. Rewind CLI Validation:
   - `node bin/rewind.js list` should show checkpoints created above.
   - `node bin/rewind.js status` verifying config file + counts.
   - `node bin/rewind.js undo` (or restore last checkpoint) and then `rewind list` to witness emergency backup creation.

5. Full Rewind Script Test:
   - Use `bin/checkpoint-rewind-full.sh <recent-checkpoint>` while pointing to repo root; ensure code restored (no errors) and conversation truncator runs (may need session mock or handle missing gracefully).

6. Metadata Consistency Check:
   - Inspect `.rewind/conversation/metadata.json` to ensure entries for checkpoints exist and were updated.
   - Confirm `.rewind/code/snapshots/*/manifest.json` includes `signature` and `filesMetadata` fields.

7. Cleanup / Reporting:
   - Summarize results, note any failures, attach logs for user.

All commands above will be run sequentially; any failure will be investigated and documented before proceeding.