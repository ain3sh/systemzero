# Tier Configuration Files

These files contain **script behavior parameters only** - they are read by `smart-checkpoint.sh` at runtime.

## Purpose

Tier configs define **how the checkpoint script behaves**:
- Anti-spam intervals
- Significance detection thresholds
- Critical file patterns

They do **NOT** contain hook registrations (those are in `../hooks/`).

## File Format

```json
{
  "tier": "balanced",
  "description": "Human-readable description",
  "antiSpam": {
    "enabled": true,
    "minIntervalSeconds": 30
  },
  "significance": {
    "enabled": true,
    "minChangeSize": 50,
    "criticalFiles": ["package.json", "Dockerfile"]
  }
}
```

## Available Tiers

### minimal-tier.json
- **Anti-spam:** Disabled
- **Significance:** Disabled
- **Frequency:** Every file creation (~2-5/session)

### balanced-tier.json (Default)
- **Anti-spam:** 30 second cooldown
- **Significance:** 50 char minimum
- **Frequency:** Smart filtering (~5-15/session)

### aggressive-tier.json
- **Anti-spam:** 15 second cooldown
- **Significance:** 25 char minimum, all files critical
- **Frequency:** Aggressive tracking (~15-40/session)

## Installation Location

These files are copied to `~/.config/checkpoint-rewind/tiers/` during installation.

The `smart-checkpoint.sh` script reads from there based on the `CHECKPOINT_TIER` environment variable.

## Environment Variable

Set your tier:

```bash
export CHECKPOINT_TIER=aggressive  # or minimal, balanced
```

This is automatically set by `install-hooks.sh` in your `~/.bashrc` or `~/.zshrc`.

## See Also

- `../hooks/` - Hook registration files (for settings.json)
- `../bin/smart-checkpoint.sh` - Script that reads these configs
- `../bin/install-hooks.sh` - Installation script
