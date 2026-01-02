#!/usr/bin/env python3
"""Smart hook merger for Rewind installation.

Safely merges rewind hooks into settings.json without touching other hooks.
Identifies rewind hooks by the presence of "smart-checkpoint" in the command.

Usage:
    python3 -m src.utils.hook_merger <settings.json> <tier.json> [--remove-only]
    
Options:
    --remove-only   Remove rewind hooks without adding new ones
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


REWIND_HOOK_IDENTIFIER = "smart-checkpoint"


def is_rewind_hook(hook_entry: dict) -> bool:
    """Check if a hook entry belongs to rewind.
    
    Args:
        hook_entry: A hook entry dict with 'hooks' array
        
    Returns:
        True if any hook command contains our identifier
    """
    hooks = hook_entry.get("hooks", [])
    for hook in hooks:
        command = hook.get("command", "")
        if REWIND_HOOK_IDENTIFIER in command:
            return True
    return False


def filter_non_rewind_hooks(hook_list: list[dict]) -> list[dict]:
    """Filter out rewind hooks from a hook list.
    
    Args:
        hook_list: List of hook entries
        
    Returns:
        List with only non-rewind hooks
    """
    return [h for h in hook_list if not is_rewind_hook(h)]


def merge_hooks(
    settings: dict,
    tier_hooks: dict,
    remove_only: bool = False
) -> dict:
    """Merge tier hooks into settings, preserving non-rewind hooks.
    
    Args:
        settings: Current settings.json content
        tier_hooks: Hooks from tier file to add
        remove_only: If True, only remove rewind hooks without adding
        
    Returns:
        Updated settings dict
    """
    # Ensure hooks section exists
    if "hooks" not in settings:
        settings["hooks"] = {}
    
    current_hooks = settings["hooks"]
    
    # Get all hook event types from both sources
    all_events = set(current_hooks.keys()) | set(tier_hooks.keys())
    
    for event in all_events:
        current_list = current_hooks.get(event, [])
        tier_list = tier_hooks.get(event, [])
        
        # Filter out existing rewind hooks
        non_rewind = filter_non_rewind_hooks(current_list)
        
        if remove_only:
            # Only keep non-rewind hooks
            if non_rewind:
                current_hooks[event] = non_rewind
            elif event in current_hooks:
                del current_hooks[event]
        else:
            # Add tier's rewind hooks after non-rewind hooks
            current_hooks[event] = non_rewind + tier_list
    
    # Clean up empty hooks dict
    if not settings["hooks"]:
        del settings["hooks"]
    
    return settings


def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 3:
        print("Usage: python3 -m src.utils.hook_merger <settings.json> <tier.json> [--remove-only]")
        return 1
    
    settings_path = Path(sys.argv[1])
    tier_path = Path(sys.argv[2])
    remove_only = "--remove-only" in sys.argv
    
    # Load settings (create empty if doesn't exist)
    if settings_path.exists():
        try:
            with open(settings_path) as f:
                settings = json.load(f)
        except json.JSONDecodeError:
            print(f"Error: Invalid JSON in {settings_path}", file=sys.stderr)
            return 1
    else:
        settings = {}
    
    # Load tier hooks (unless remove-only)
    tier_hooks = {}
    if not remove_only:
        if not tier_path.exists():
            print(f"Error: Tier file not found: {tier_path}", file=sys.stderr)
            return 1
        
        try:
            with open(tier_path) as f:
                tier_data = json.load(f)
            tier_hooks = tier_data.get("hooks", {})
        except json.JSONDecodeError:
            print(f"Error: Invalid JSON in {tier_path}", file=sys.stderr)
            return 1
    
    # Merge hooks
    updated_settings = merge_hooks(settings, tier_hooks, remove_only=remove_only)
    
    # Write back
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    with open(settings_path, "w") as f:
        json.dump(updated_settings, f, indent=2)
    
    if remove_only:
        print(f"Removed rewind hooks from {settings_path}")
    else:
        tier_name = tier_path.stem
        print(f"Registered {tier_name} hooks in {settings_path}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
