"""Hook handler for Rewind.

Implements the decision logic for when to create checkpoints.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from .io import log_debug
from .types import (
    HookInput,
    PostToolUseInput,
    PreToolUseInput,
    SessionStartInput,
    StopInput,
    UserPromptSubmitInput,
)

if TYPE_CHECKING:
    from ..config import TierConfig
    from ..core.controller import RewindController


class HookHandler:
    """Handles hook events and decides when to checkpoint."""
    
    # Tools that trigger checkpoints
    CHECKPOINT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit", "Create"}
    
    # State file for anti-spam
    STATE_FILE = ".agent/rewind/hook-state.json"
    
    def __init__(self, controller: RewindController, tier_config: TierConfig | None = None):
        """Initialize hook handler.
        
        Args:
            controller: RewindController instance
            tier_config: Tier configuration (for anti-spam, significance)
        """
        self.controller = controller
        self.tier_config = tier_config
        self._last_checkpoint_time: float | None = None
    
    def handle(self, hook_input: HookInput) -> bool:
        """Handle a hook event.
        
        Args:
            hook_input: Parsed hook input
            
        Returns:
            True if checkpoint was created, False otherwise
        """
        if isinstance(hook_input, SessionStartInput):
            return self._handle_session_start(hook_input)
        elif isinstance(hook_input, PreToolUseInput):
            return self._handle_pre_tool_use(hook_input)
        elif isinstance(hook_input, PostToolUseInput):
            return self._handle_post_tool_use(hook_input)
        elif isinstance(hook_input, StopInput):
            return self._handle_stop(hook_input)
        elif isinstance(hook_input, UserPromptSubmitInput):
            return self._handle_user_prompt_submit(hook_input)
        else:
            log_debug(f"Unhandled hook event: {hook_input.hook_event_name}")
            return False
    
    def _handle_session_start(self, hook_input: SessionStartInput) -> bool:
        """Handle SessionStart hook.
        
        Creates initial checkpoint on startup.
        """
        if hook_input.source != "startup":
            log_debug(f"Skipping checkpoint for session source: {hook_input.source}")
            return False
        
        log_debug("Session start - creating initial checkpoint")
        result = self.controller.create_checkpoint(
            description="Session start",
            session_id=hook_input.session_id,
            transcript_path=hook_input.transcript_path,
        )
        return result.get("success", False)
    
    def _handle_pre_tool_use(self, hook_input: PreToolUseInput) -> bool:
        """Handle PreToolUse hook.
        
        Creates checkpoint before file-modifying tools.
        """
        tool_name = hook_input.tool_name
        
        # Only checkpoint for file-modifying tools
        if tool_name not in self.CHECKPOINT_TOOLS:
            log_debug(f"Skipping non-checkpoint tool: {tool_name}")
            return False
        
        # Anti-spam check
        if not self._should_checkpoint():
            log_debug("Anti-spam: skipping checkpoint (too soon)")
            return False
        
        # Get target file info for description
        tool_input = hook_input.tool_input
        target_file = tool_input.get("file_path") or tool_input.get("path") or "unknown"
        if isinstance(target_file, str):
            target_file = Path(target_file).name
        
        description = f"Before {tool_name}: {target_file}"
        log_debug(f"Creating checkpoint: {description}")
        
        result = self.controller.create_checkpoint(
            description=description,
            session_id=hook_input.session_id,
            transcript_path=hook_input.transcript_path,
        )
        
        if result.get("success"):
            self._update_checkpoint_time()
        
        return result.get("success", False)
    
    def _handle_post_tool_use(self, hook_input: PostToolUseInput) -> bool:
        """Handle PostToolUse hook.
        
        Used in aggressive tier for post-Bash checkpoints.
        """
        if hook_input.tool_name != "Bash":
            return False
        
        # Only checkpoint after potentially destructive commands
        command = hook_input.tool_input.get("command", "")
        if not self._is_destructive_command(command):
            return False
        
        if not self._should_checkpoint():
            return False
        
        description = f"After Bash: {command[:50]}..."
        result = self.controller.create_checkpoint(
            description=description,
            session_id=hook_input.session_id,
            transcript_path=hook_input.transcript_path,
        )
        
        if result.get("success"):
            self._update_checkpoint_time()
        
        return result.get("success", False)
    
    def _handle_stop(self, hook_input: StopInput) -> bool:
        """Handle Stop hook.
        
        Creates final checkpoint when session ends.
        """
        log_debug("Session stop - creating final checkpoint")
        result = self.controller.create_checkpoint(
            description="Session end",
            session_id=hook_input.session_id,
            transcript_path=hook_input.transcript_path,
        )
        return result.get("success", False)
    
    def _handle_user_prompt_submit(self, hook_input: UserPromptSubmitInput) -> bool:
        """Handle UserPromptSubmit hook.
        
        Used in aggressive tier for prompt-based checkpoints.
        """
        # Check for destructive keywords in prompt
        prompt_lower = hook_input.prompt.lower()
        destructive_keywords = ["delete", "remove", "refactor", "rewrite", "replace all"]
        
        if not any(kw in prompt_lower for kw in destructive_keywords):
            return False
        
        if not self._should_checkpoint():
            return False
        
        description = f"Before prompt: {hook_input.prompt[:30]}..."
        result = self.controller.create_checkpoint(
            description=description,
            session_id=hook_input.session_id,
            transcript_path=hook_input.transcript_path,
        )
        
        if result.get("success"):
            self._update_checkpoint_time()
        
        return result.get("success", False)
    
    def _should_checkpoint(self) -> bool:
        """Check if we should create a checkpoint (anti-spam).
        
        Returns:
            True if enough time has passed since last checkpoint
        """
        if self.tier_config and not self.tier_config.anti_spam.enabled:
            return True
        
        min_interval = 30  # default
        if self.tier_config:
            min_interval = self.tier_config.anti_spam.min_interval_seconds
        
        if self._last_checkpoint_time is None:
            # Load from state file
            self._load_state()
        
        if self._last_checkpoint_time is None:
            return True
        
        elapsed = time.time() - self._last_checkpoint_time
        return elapsed >= min_interval
    
    def _update_checkpoint_time(self) -> None:
        """Update last checkpoint time and persist to state file."""
        self._last_checkpoint_time = time.time()
        self._save_state()
    
    def _load_state(self) -> None:
        """Load state from file."""
        import json
        state_path = self.controller.get_rewind_dir() / "hook-state.json"
        if state_path.exists():
            try:
                with open(state_path) as f:
                    data = json.load(f)
                self._last_checkpoint_time = data.get("last_checkpoint_time")
            except (OSError, json.JSONDecodeError):
                pass
    
    def _save_state(self) -> None:
        """Save state to file."""
        import json
        state_path = self.controller.get_rewind_dir() / "hook-state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(state_path, "w") as f:
                json.dump({"last_checkpoint_time": self._last_checkpoint_time}, f)
        except OSError:
            pass
    
    @staticmethod
    def _is_destructive_command(command: str) -> bool:
        """Check if a bash command is potentially destructive.
        
        Args:
            command: Bash command string
            
        Returns:
            True if command might be destructive
        """
        destructive_patterns = [
            "rm ", "rm\t", "rmdir",
            "mv ", "mv\t",
            "git reset", "git checkout", "git clean",
            "pip uninstall", "npm uninstall",
            "> ", ">>",  # redirects that overwrite
        ]
        command_lower = command.lower()
        return any(pattern in command_lower for pattern in destructive_patterns)
