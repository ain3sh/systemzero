"""Rewind controller - main orchestrator.

Coordinates checkpoint store and context manager for unified operations.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, cast

from ..config import ConfigLoader, RewindConfig, StorageMode
from ..utils.env import get_global_rewind_dir, get_global_storage_dir
from ..utils.fs import atomic_write, safe_json_load
from .checkpoint_store import CheckpointStore, CheckpointMetadata
from .transcript_manager import TranscriptCursor, TranscriptManager, TranscriptManagerError


RestoreMode = Literal["all", "code", "context"]
TranscriptRestoreMode = Literal["fork", "in_place"]


@dataclass
class RewindStatus:
    """Status of the Rewind system."""
    initialized: bool
    storage_mode: str
    checkpoint_count: int
    latest_checkpoint: str | None
    project_root: str
    rewind_dir: str
    tier: str = "balanced"
    agent: str = "unknown"


class RewindController:
    """Main controller for Rewind operations."""
    
    def __init__(self, project_root: Path | str | None = None):
        """Initialize controller.
        
        Args:
            project_root: Project root directory (defaults to cwd)
        """
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self._config_loader = ConfigLoader(project_root=self.project_root)
        self._store: CheckpointStore | None = None
        self._transcripts: TranscriptManager = TranscriptManager()
    
    @property
    def config(self) -> RewindConfig:
        """Get current configuration."""
        return self._config_loader.config
    
    @property
    def store(self) -> CheckpointStore:
        """Get checkpoint store (lazy init)."""
        if self._store is None:
            self._store = CheckpointStore(
                storage_dir=self.get_checkpoints_dir(),
                project_root=self.project_root,
                ignore_config=self._config_loader.load_ignore_config(),
            )
        return self._store
    
    def get_rewind_dir(self) -> Path:
        """Get the .agent/rewind directory path.
        
        Returns:
            Path to .agent/rewind directory (project-local or global)
        """
        if self.config.storage_mode == StorageMode.GLOBAL:
            return get_global_rewind_dir()
        return self.project_root / ".agent" / "rewind"
    
    def get_checkpoints_dir(self) -> Path:
        """Get the checkpoints storage directory.
        
        Returns:
            Path to checkpoints directory
        """
        if self.config.storage_mode == StorageMode.GLOBAL:
            # Use project hash for global storage
            project_hash = self._get_project_hash()
            return get_global_storage_dir() / project_hash / "checkpoints"
        return self.get_rewind_dir() / "checkpoints"

    def get_session_file(self) -> Path:
        """Get path to stored session metadata for this project."""
        return self.get_rewind_dir() / "session.json"

    def load_session_info(self) -> dict[str, Any] | None:
        """Load stored session info (best-effort)."""
        data = safe_json_load(self.get_session_file(), None)
        return data if isinstance(data, dict) else None

    def save_session_info(
        self,
        *,
        transcript_path: str | None,
        session_id: str | None = None,
        agent: str | None = None,
        env_file: str | None = None,
    ) -> None:
        """Persist session info to disk (best-effort)."""
        info: dict[str, Any] = {
            "version": 1,
            "transcript_path": transcript_path or "",
            "session_id": session_id or "",
            "agent": agent or "unknown",
            "project_root": str(self.project_root),
            "updated_at": datetime.now().isoformat(),
        }
        if env_file:
            info["env_file"] = env_file

        try:
            atomic_write(self.get_session_file(), json.dumps(info, indent=2), mode="w")
        except Exception:
            # Best-effort; do not fail core operations.
            return
    
    def init(self, mode: StorageMode | None = None) -> dict[str, Any]:
        """Initialize Rewind for the current project.
        
        Args:
            mode: Storage mode to use (project or global)
            
        Returns:
            Result dictionary with success status
        """
        try:
            # Create .agent/rewind directory
            rewind_dir = self.get_rewind_dir()
            rewind_dir.mkdir(parents=True, exist_ok=True)
            
            # Save config if mode specified
            if mode:
                config = RewindConfig(storage_mode=mode)
                self._config_loader.save_config(config, scope="project")
                self._config_loader.reload()
                # Reset lazy-loaded components
                self._store = None
            
            # Create checkpoints directory
            self.get_checkpoints_dir().mkdir(parents=True, exist_ok=True)
            
            return {
                "success": True,
                "rewindDir": str(rewind_dir),
                "storageMode": self.config.storage_mode.value,
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def create_checkpoint(
        self,
        description: str = "",
        session_id: str | None = None,
        force: bool = False,
        transcript_path: str | None = None,
    ) -> dict[str, Any]:
        """Create a new checkpoint.
        
        Args:
            description: Human-readable description
            session_id: Optional session identifier
            force: Force creation even if no changes
            
        Returns:
            Result dictionary with checkpoint info
        """
        # Ensure initialized
        rewind_dir = self.get_rewind_dir()
        if not rewind_dir.exists():
            init_result = self.init()
            if not init_result.get("success"):
                return init_result
        
        # Create checkpoint
        result = self.store.create(description=description, session_id=session_id)
        
        if not result.success:
            return {
                "success": False,
                "error": result.error,
            }
        
        checkpoint_dir = self.get_checkpoints_dir() / result.name

        # Save transcript snapshot (source-of-truth conversation)
        effective_transcript_path = transcript_path
        session_info: dict[str, Any] = {}
        if not effective_transcript_path:
            session_info = self.load_session_info() or {}
            if isinstance(session_info, dict):
                effective_transcript_path = session_info.get("transcript_path")

        has_transcript = False
        forkable_transcript: dict[str, Any] | None = None
        if effective_transcript_path:
            tp = Path(effective_transcript_path).expanduser()
            if tp.exists():
                try:
                    agent_hint = session_info.get("agent") if isinstance(session_info, dict) else None
                    snapshot = self._transcripts.snapshot_into_checkpoint(
                        tp,
                        checkpoint_dir,
                        agent_hint=str(agent_hint) if isinstance(agent_hint, str) and agent_hint else None,
                    )
                    has_transcript = True
                    forkable_transcript = {
                        "agent": snapshot.agent,
                        "original_path": snapshot.original_path,
                        "snapshot": snapshot.snapshot_relpath,
                        "cursor": {
                            "byte_offset_end": snapshot.cursor.byte_offset_end,
                            "last_event_id": snapshot.cursor.last_event_id,
                            "prefix_sha256": snapshot.cursor.prefix_sha256,
                            "tail_sha256": snapshot.cursor.tail_sha256,
                        },
                    }
                except TranscriptManagerError:
                    has_transcript = False

        if has_transcript:
            self.store.update_metadata(
                result.name,
                has_transcript=True,
                transcript=forkable_transcript,
            )
        
        return {
            "success": True,
            "name": result.name,
            "fileCount": result.file_count,
            "hasTranscript": has_transcript,
        }
    
    def restore(
        self,
        name: str,
        mode: RestoreMode = "all",
        skip_backup: bool = False,
        transcript_restore: TranscriptRestoreMode = "fork",
    ) -> dict[str, Any]:
        """Restore to a checkpoint.
        
        Args:
            name: Checkpoint name to restore
            mode: What to restore (all, code, context)
            skip_backup: Skip creating backup before restore
            
        Returns:
            Result dictionary
        """
        checkpoint_dir = self.get_checkpoints_dir() / name
        if not checkpoint_dir.exists():
            return {"success": False, "error": f"Checkpoint not found: {name}"}
        
        results = {"success": True, "name": name}
        
        # Restore code
        if mode in ("all", "code"):
            code_result = self.store.restore(name, backup=not skip_backup)
            if not code_result.success:
                return {"success": False, "error": code_result.error}
            results["codeRestored"] = True
            results["fileCount"] = code_result.file_count
        
        # Restore context
        results["contextRequested"] = mode in ("all", "context")
        if results["contextRequested"]:
            results.update(self._restore_transcript(checkpoint_dir, transcript_restore))
            if "contextRestored" not in results:
                results["contextRestored"] = False
        
        return results

    def rewind_back(
        self,
        n: int,
        *,
        both: bool = False,
        in_place: bool = False,
        copy: bool = False,
    ) -> dict[str, Any]:
        """Rewind by the last N user prompts (fast path).

        This is a chat-first primitive designed for non-interactive usage.
        """
        if n <= 0:
            return {"success": False, "error": "n must be >= 1"}

        session_info = self.load_session_info() or {}
        transcript_path: str | None = None

        env_tp = os.environ.get("REWIND_TRANSCRIPT_PATH")
        if isinstance(env_tp, str) and env_tp.strip():
            transcript_path = env_tp.strip()
        elif isinstance(session_info, dict):
            transcript_path = session_info.get("transcript_path")

        if not transcript_path:
            return {
                "success": False,
                "error": "No transcript path available (run inside an agent session or ensure hooks wrote session.json)",
            }

        agent = session_info.get("agent") if isinstance(session_info, dict) else None
        agent_str = str(agent) if isinstance(agent, str) and agent else None

        tp = Path(transcript_path).expanduser()
        if not tp.exists():
            return {"success": False, "error": f"Transcript not found: {tp}"}

        try:
            boundary = cast(Any, self._transcripts).find_boundary_by_user_prompts(tp, n)
        except (TranscriptManagerError, ValueError) as e:
            return {"success": False, "error": str(e)}

        result: dict[str, Any] = {
            "success": True,
            "n": n,
            "prompts": boundary.prompts,
            "boundaryOffset": boundary.boundary_offset,
        }

        if both:
            checkpoint = self._select_checkpoint_for_boundary(
                self.list_checkpoints(),
                transcript_path=str(tp),
                boundary_offset=boundary.boundary_offset,
            )
            if checkpoint is not None:
                code_restore = self.restore(name=checkpoint.name, mode="code", skip_backup=False)
                if not code_restore.get("success"):
                    return {"success": False, "error": code_restore.get("error") or "Failed to restore code"}
                result["codeRestored"] = True
                result["codeCheckpoint"] = checkpoint.name
            else:
                result["codeRestored"] = False
                result["note"] = "No code checkpoint matched this rewind boundary; created chat rewind only"

        if in_place:
            backup_dir = self.get_rewind_dir() / "transcript-backup"
            try:
                backup_path = cast(Any, self._transcripts).rewrite_in_place_at_offset(
                    current_transcript_path=tp,
                    boundary_offset=boundary.boundary_offset,
                    backup_dir=backup_dir,
                )
            except TranscriptManagerError as e:
                return {"success": False, "error": str(e)}

            result.update(
                {
                    "forkCreated": False,
                    "chatRewritten": True,
                    "backupPath": str(backup_path),
                }
            )
            return result

        try:
            fork_path = cast(Any, self._transcripts).create_fork_at_offset(
                current_transcript_path=tp,
                boundary_offset=boundary.boundary_offset,
                rewrite_title_prefix="[Fork] ",
                agent=agent_str,
            )
        except TranscriptManagerError as e:
            return {"success": False, "error": str(e)}

        result.update(
            {
                "forkCreated": True,
                "forkPath": str(fork_path),
                "forkSessionId": fork_path.stem,
            }
        )
        return result

    @staticmethod
    def _select_checkpoint_for_boundary(
        checkpoints: list[CheckpointMetadata],
        *,
        transcript_path: str,
        boundary_offset: int,
    ) -> CheckpointMetadata | None:
        """Pick the newest checkpoint whose cursor is at-or-before the boundary."""
        tp = str(Path(transcript_path).expanduser())

        for cp in checkpoints:
            meta = cp.transcript
            if not isinstance(meta, dict):
                continue

            original_path = meta.get("original_path") or meta.get("path")
            if not isinstance(original_path, str) or not original_path:
                continue

            if str(Path(original_path).expanduser()) != tp:
                continue

            cursor = meta.get("cursor")
            if not isinstance(cursor, dict):
                continue

            try:
                cursor_end = int(cursor.get("byte_offset_end", 0))
            except Exception:
                continue

            if cursor_end <= boundary_offset:
                return cp

        return None

    def _restore_transcript(self, checkpoint_dir: Path, transcript_restore: TranscriptRestoreMode) -> dict[str, Any]:
        """Restore conversation state from a checkpoint.

        Default is to create a new fork session file and not mutate the original transcript.
        """
        meta = self.store.get(checkpoint_dir.name)
        if not meta or not meta.transcript:
            return {"contextRestored": False}

        transcript_meta = meta.transcript
        cursor_data = transcript_meta.get("cursor") if isinstance(transcript_meta, dict) else None
        if not isinstance(cursor_data, dict):
            return {"contextRestored": False}

        try:
            cursor = TranscriptCursor(
                byte_offset_end=int(cursor_data.get("byte_offset_end", 0)),
                last_event_id=cursor_data.get("last_event_id"),
                prefix_sha256=str(cursor_data.get("prefix_sha256", "")),
                tail_sha256=str(cursor_data.get("tail_sha256", "")),
            )
        except Exception:
            return {"contextRestored": False}

        # Resolve current transcript path (prefer session.json)
        current_path: str | None = None
        session_info = self.load_session_info() or {}
        if isinstance(session_info, dict):
            current_path = session_info.get("transcript_path")
        if not current_path:
            current_path = transcript_meta.get("original_path") or transcript_meta.get("path")

        if not current_path:
            return {"contextRestored": False}

        current_transcript_path = Path(current_path).expanduser()
        snapshot_rel = transcript_meta.get("snapshot")
        snapshot_gz = (checkpoint_dir / snapshot_rel) if isinstance(snapshot_rel, str) else None
        if snapshot_gz is not None and not snapshot_gz.exists():
            snapshot_gz = None

        if transcript_restore == "fork":
            try:
                agent = transcript_meta.get("agent") if isinstance(transcript_meta, dict) else None
                fork_path = self._transcripts.create_fork_session(
                    checkpoint_cursor=cursor,
                    checkpoint_snapshot_gz=snapshot_gz,
                    current_transcript_path=current_transcript_path,
                    rewrite_title_prefix="[Fork] ",
                    agent=str(agent) if isinstance(agent, str) and agent else None,
                )
            except TranscriptManagerError as e:
                return {"contextRestored": False, "contextError": str(e)}

            self._append_restore_history({
                "timestamp": datetime.now().isoformat(),
                "checkpoint": checkpoint_dir.name,
                "transcript": {
                    "mode": "fork",
                    "original": str(current_transcript_path),
                    "fork": str(fork_path),
                },
            })
            return {"contextRestored": True, "forkCreated": True, "forkPath": str(fork_path)}

        # In-place restore (optional)
        try:
            self._restore_transcript_in_place(
                checkpoint_cursor=cursor,
                checkpoint_snapshot_gz=snapshot_gz,
                current_transcript_path=current_transcript_path,
            )
        except TranscriptManagerError as e:
            return {"contextRestored": False, "contextError": str(e)}

        self._append_restore_history({
            "timestamp": datetime.now().isoformat(),
            "checkpoint": checkpoint_dir.name,
            "transcript": {
                "mode": "in_place",
                "path": str(current_transcript_path),
            },
        })
        return {"contextRestored": True, "forkCreated": False}

    def _restore_transcript_in_place(
        self,
        *,
        checkpoint_cursor: TranscriptCursor,
        checkpoint_snapshot_gz: Path | None,
        current_transcript_path: Path,
    ) -> None:
        # Backup current transcript first.
        backup_dir = self.get_rewind_dir() / "transcript-backup"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        if current_transcript_path.exists():
            import shutil
            shutil.copy2(current_transcript_path, backup_path)

        if current_transcript_path.exists() and self._transcripts.prefix_matches(
            current_transcript_path, checkpoint_cursor.prefix_sha256
        ):
            try:
                with open(current_transcript_path, "rb+") as f:
                    f.truncate(checkpoint_cursor.byte_offset_end)
            except OSError as e:
                raise TranscriptManagerError(f"Failed to truncate transcript: {e}") from e
            return

        if checkpoint_snapshot_gz is None:
            raise TranscriptManagerError("No checkpoint transcript snapshot available")

        # Overwrite from snapshot.
        self._transcripts._inflate_gz(checkpoint_snapshot_gz, current_transcript_path)

    def _append_restore_history(self, entry: dict[str, Any]) -> None:
        """Append an entry to restore history (best-effort)."""
        history_path = self.get_rewind_dir() / "restore-history.json"
        history = safe_json_load(history_path, [])
        if not isinstance(history, list):
            history = []
        history.append(entry)
        try:
            atomic_write(history_path, json.dumps(history, indent=2), mode="w")
        except Exception:
            return
    
    def undo(self) -> dict[str, Any]:
        """Undo to the previous checkpoint.
        
        Returns:
            Result dictionary
        """
        checkpoints = self.list_checkpoints()
        if len(checkpoints) < 2:
            return {"success": False, "error": "Not enough checkpoints to undo"}
        
        # Restore to second-most-recent (index 1, since list is newest-first)
        previous = checkpoints[1]
        result = self.restore(previous.name, skip_backup=True)
        
        if result.get("success"):
            # Delete the most recent checkpoint
            self.store.delete(checkpoints[0].name)
            result["deletedCheckpoint"] = checkpoints[0].name
        
        return result
    
    def list_checkpoints(self) -> list[CheckpointMetadata]:
        """List all checkpoints.
        
        Returns:
            List of checkpoint metadata, newest first
        """
        return self.store.list()
    
    def get_status(self) -> RewindStatus:
        """Get system status.
        
        Returns:
            RewindStatus with current state
        """
        rewind_dir = self.get_rewind_dir()
        initialized = rewind_dir.exists()
        
        checkpoints = self.list_checkpoints() if initialized else []
        latest = checkpoints[0].name if checkpoints else None
        
        agent = "unknown"
        session_info = self.load_session_info() or {}
        if isinstance(session_info, dict) and session_info.get("agent"):
            agent = str(session_info.get("agent"))
        
        return RewindStatus(
            initialized=initialized,
            storage_mode=self.config.storage_mode.value,
            checkpoint_count=len(checkpoints),
            latest_checkpoint=latest,
            project_root=str(self.project_root),
            rewind_dir=str(rewind_dir),
            tier=self.config.tier.tier,
            agent=agent,
        )
    
    def validate_system(self) -> dict[str, Any]:
        """Validate system configuration and state.
        
        Returns:
            Validation result with any issues found
        """
        issues = []
        
        rewind_dir = self.get_rewind_dir()
        if not rewind_dir.exists():
            issues.append("Rewind not initialized (run 'rewind init')")
        
        checkpoints_dir = self.get_checkpoints_dir()
        if not checkpoints_dir.exists():
            issues.append("Checkpoints directory missing")
        
        # Check for corrupted checkpoints
        for cp in self.list_checkpoints():
            cp_dir = checkpoints_dir / cp.name
            archive = cp_dir / "snapshot.tar.gz"
            if not archive.exists():
                issues.append(f"Checkpoint {cp.name} missing archive")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
        }
    
    def diff(self, checkpoint1: str, checkpoint2: str | None = None) -> dict[str, Any]:
        """Compare two checkpoints or checkpoint with current state.
        
        Args:
            checkpoint1: First checkpoint name
            checkpoint2: Second checkpoint name (or None for current state)
            
        Returns:
            Diff result with changed files
        """
        # This is a simplified diff - just compares file lists
        # A full diff would extract and compare file contents
        
        cp1_meta = self.store.get(checkpoint1)
        if not cp1_meta:
            return {"success": False, "error": f"Checkpoint not found: {checkpoint1}"}
        
        if checkpoint2:
            cp2_meta = self.store.get(checkpoint2)
            if not cp2_meta:
                return {"success": False, "error": f"Checkpoint not found: {checkpoint2}"}
            
            return {
                "success": True,
                "checkpoint1": {"name": checkpoint1, "fileCount": cp1_meta.file_count},
                "checkpoint2": {"name": checkpoint2, "fileCount": cp2_meta.file_count},
                "note": "Detailed diff not yet implemented",
            }
        else:
            return {
                "success": True,
                "checkpoint1": {"name": checkpoint1, "fileCount": cp1_meta.file_count},
                "checkpoint2": {"name": "current", "fileCount": "N/A"},
                "note": "Detailed diff not yet implemented",
            }
    
    def _get_project_hash(self) -> str:
        """Get a hash of the project path for global storage.
        
        Returns:
            Short hash string
        """
        path_bytes = str(self.project_root.resolve()).encode()
        return hashlib.sha256(path_bytes).hexdigest()[:12]
