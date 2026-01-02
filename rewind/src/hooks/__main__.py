"""Entry point for running hooks via: python3 -m src.hooks <action>

This is the main hook entry point called by the shell shim.
It implements proper hook protocol:
- Exit 0: Allow (no stdout for PreToolUse)
- Exit 1: Non-blocking error (stderr shown to user)
- Exit 2: Block (stderr shown to agent)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    """Main entry point for hook processing."""
    # Minimal imports for fast startup
    if len(sys.argv) < 2:
        print("Usage: python3 -m src.hooks <action>", file=sys.stderr)
        print("Actions: session-start, pre-tool-use, post-bash, stop", file=sys.stderr)
        return 1
    
    action = sys.argv[1]
    
    # Import lazily to minimize startup time
    from .io import read_input_with_context, exit_success, emit_context, log_debug
    from .handler import HookHandler
    from ..agents.envfile import write_env_exports
    
    try:
        # Parse hook input from stdin
        hook_input, agent_context = read_input_with_context()
        log_debug(f"Received {hook_input.hook_event_name} hook, action={action}")
        
        # Resolve project root (config overrides -> env -> payload cwd)
        root = Path(agent_context.project_root) if agent_context.project_root else None
        cwd = Path(hook_input.cwd) if hook_input.cwd else Path.cwd()
        project_root = (root or cwd).expanduser()
        
        # Lazy import controller to avoid loading everything
        from ..core.controller import RewindController
        from ..config import ConfigLoader
        
        # Initialize controller
        controller = RewindController(project_root=project_root)

        # Persist session metadata for CLI restore (best-effort)
        controller.save_session_info(
            transcript_path=agent_context.transcript_path,
            session_id=agent_context.session_id,
            agent=agent_context.agent,
            env_file=agent_context.env_file,
        )

        # Write env vars immediately on SessionStart (best-effort)
        if hook_input.hook_event_name == "SessionStart" and agent_context.env_file:
            exports = {
                "REWIND_AGENT_KIND": agent_context.agent,
                "REWIND_PROJECT_ROOT": str(project_root),
            }
            if agent_context.transcript_path:
                exports["REWIND_TRANSCRIPT_PATH"] = agent_context.transcript_path

            # Ensure user-local bin dir is available in tool subprocess PATH.
            # Avoid writing unexpanded ${PATH:-...} since env-files may be parsed.
            current_path = os.environ.get("PATH") or "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
            bin_dir = str((Path.home() / ".local" / "bin").expanduser())
            if bin_dir and bin_dir not in current_path.split(":"):
                exports["PATH"] = f"{bin_dir}:{current_path}"
            try:
                write_env_exports(Path(agent_context.env_file).expanduser(), exports)
            except Exception:
                # Best-effort; do not break the hook.
                pass
        
        # Load tier config from ~/.rewind/config.json (or defaults)
        config_loader = ConfigLoader(project_root=project_root)
        tier_config = config_loader.load_tier_config(None)
        
        # Create handler and process
        handler = HookHandler(controller=controller, tier_config=tier_config)
        checkpoint_created = handler.handle(hook_input)
        
        # For SessionStart, emit context if checkpoint was created
        if hook_input.hook_event_name == "SessionStart" and checkpoint_created:
            emit_context("[rewind] Checkpoint created on session start")
        
        # Always exit success (allow the action)
        # We never block tool calls, just checkpoint before them
        exit_success()
        
    except Exception as e:
        # Log error but don't block - hooks should be non-blocking
        log_debug(f"Hook error: {e}")
        # Exit 1 = non-blocking error, shown to user
        print(f"[rewind] Hook error: {e}", file=sys.stderr)
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
