"""Checkpoint storage for Rewind.

Handles creating, listing, and restoring file snapshots using tarfile.
"""

from __future__ import annotations

import json
import os
import shutil
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from ..config.types import IgnoreConfig


@dataclass
class CheckpointMetadata:
    """Metadata for a checkpoint."""
    name: str
    timestamp: str
    description: str
    file_count: int
    total_size: int
    session_id: str | None = None
    has_transcript: bool = False
    transcript: dict[str, Any] | None = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        data: dict[str, Any] = {
            "name": self.name,
            "timestamp": self.timestamp,
            "description": self.description,
            "fileCount": self.file_count,
            "totalSize": self.total_size,
            "sessionId": self.session_id,
            "hasTranscript": self.has_transcript,
        }

        if self.transcript is not None:
            data["transcript"] = self.transcript

        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> CheckpointMetadata:
        """Create from dictionary."""
        return cls(
            name=data.get("name", ""),
            timestamp=data.get("timestamp", ""),
            description=data.get("description", ""),
            file_count=data.get("fileCount", 0),
            total_size=data.get("totalSize", 0),
            session_id=data.get("sessionId"),
            has_transcript=data.get("hasTranscript", False),
            transcript=data.get("transcript"),
        )


@dataclass
class CheckpointResult:
    """Result of a checkpoint operation."""
    success: bool
    name: str = ""
    file_count: int = 0
    error: str | None = None


class CheckpointStore:
    """Manages checkpoint storage and retrieval."""
    
    ARCHIVE_NAME = "snapshot.tar.gz"
    METADATA_NAME = "metadata.json"
    
    def __init__(
        self,
        storage_dir: Path,
        project_root: Path,
        ignore_config: IgnoreConfig | None = None,
    ):
        """Initialize checkpoint store.
        
        Args:
            storage_dir: Directory to store checkpoints
            project_root: Project root directory to snapshot
            ignore_config: Patterns for files to ignore
        """
        self.storage_dir = Path(storage_dir)
        self.project_root = Path(project_root)
        self.ignore_config = ignore_config or IgnoreConfig()
        
        # Ensure storage directory exists
        self.storage_dir.mkdir(parents=True, exist_ok=True)
    
    def create(
        self,
        description: str = "",
        session_id: str | None = None,
    ) -> CheckpointResult:
        """Create a new checkpoint.
        
        Args:
            description: Human-readable description
            session_id: Optional session identifier
            
        Returns:
            CheckpointResult with success status and details
        """
        timestamp = datetime.now()
        # Include milliseconds for uniqueness when creating multiple checkpoints quickly
        name = timestamp.strftime("%Y%m%d_%H%M%S") + f"_{timestamp.microsecond // 1000:03d}"
        checkpoint_dir = self.storage_dir / name
        
        try:
            checkpoint_dir.mkdir(parents=True, exist_ok=True)
            
            # Collect files to archive
            files_to_archive = list(self._collect_files())
            if not files_to_archive:
                return CheckpointResult(
                    success=False,
                    error="No files to checkpoint"
                )
            
            # Create tar archive
            archive_path = checkpoint_dir / self.ARCHIVE_NAME
            total_size = 0
            
            with tarfile.open(archive_path, "w:gz") as tar:
                for file_path in files_to_archive:
                    rel_path = file_path.relative_to(self.project_root)
                    tar.add(file_path, arcname=str(rel_path))
                    total_size += file_path.stat().st_size
            
            # Save metadata
            metadata = CheckpointMetadata(
                name=name,
                timestamp=timestamp.isoformat(),
                description=description,
                file_count=len(files_to_archive),
                total_size=total_size,
                session_id=session_id,
            )
            
            metadata_path = checkpoint_dir / self.METADATA_NAME
            with open(metadata_path, "w") as f:
                json.dump(metadata.to_dict(), f, indent=2)
            
            return CheckpointResult(
                success=True,
                name=name,
                file_count=len(files_to_archive),
            )
            
        except Exception as e:
            # Clean up on failure
            if checkpoint_dir.exists():
                shutil.rmtree(checkpoint_dir, ignore_errors=True)
            return CheckpointResult(success=False, error=str(e))
    
    def restore(self, name: str, backup: bool = True) -> CheckpointResult:
        """Restore a checkpoint.
        
        Args:
            name: Checkpoint name to restore
            backup: Whether to create backup before restore
            
        Returns:
            CheckpointResult with success status
        """
        checkpoint_dir = self.storage_dir / name
        archive_path = checkpoint_dir / self.ARCHIVE_NAME
        
        if not archive_path.exists():
            return CheckpointResult(
                success=False,
                error=f"Checkpoint not found: {name}"
            )
        
        try:
            # Create backup if requested
            if backup:
                backup_result = self.create(
                    description=f"Backup before restore to {name}",
                )
                if not backup_result.success:
                    return CheckpointResult(
                        success=False,
                        error=f"Failed to create backup: {backup_result.error}"
                    )
            
            # Extract to temp directory first
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir)
                
                with tarfile.open(archive_path, "r:gz") as tar:
                    tar.extractall(tmp_path, filter="data")
                
                # Copy files to project root
                file_count = 0
                for root, _, files in os.walk(tmp_path):
                    for file in files:
                        src = Path(root) / file
                        rel_path = src.relative_to(tmp_path)
                        dst = self.project_root / rel_path
                        
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, dst)
                        file_count += 1
            
            return CheckpointResult(success=True, name=name, file_count=file_count)
            
        except Exception as e:
            return CheckpointResult(success=False, error=str(e))
    
    def list(self) -> list[CheckpointMetadata]:
        """List all checkpoints.
        
        Returns:
            List of checkpoint metadata, sorted by timestamp (newest first)
        """
        checkpoints = []
        
        if not self.storage_dir.exists():
            return checkpoints
        
        for entry in self.storage_dir.iterdir():
            if not entry.is_dir():
                continue
            
            metadata_path = entry / self.METADATA_NAME
            if metadata_path.exists():
                try:
                    with open(metadata_path) as f:
                        data = json.load(f)
                    checkpoints.append(CheckpointMetadata.from_dict(data))
                except (OSError, json.JSONDecodeError):
                    # Create minimal metadata from directory name
                    checkpoints.append(CheckpointMetadata(
                        name=entry.name,
                        timestamp=entry.name,
                        description="",
                        file_count=0,
                        total_size=0,
                    ))
        
        # Sort by name (which is timestamp-based) descending
        checkpoints.sort(key=lambda x: x.name, reverse=True)
        return checkpoints
    
    def get(self, name: str) -> CheckpointMetadata | None:
        """Get metadata for a specific checkpoint.
        
        Args:
            name: Checkpoint name
            
        Returns:
            CheckpointMetadata or None if not found
        """
        metadata_path = self.storage_dir / name / self.METADATA_NAME
        if not metadata_path.exists():
            return None
        
        try:
            with open(metadata_path) as f:
                return CheckpointMetadata.from_dict(json.load(f))
        except (OSError, json.JSONDecodeError):
            return None
    
    def delete(self, name: str) -> bool:
        """Delete a checkpoint.
        
        Args:
            name: Checkpoint name to delete
            
        Returns:
            True if deleted successfully
        """
        checkpoint_dir = self.storage_dir / name
        if not checkpoint_dir.exists():
            return False
        
        try:
            shutil.rmtree(checkpoint_dir)
            return True
        except OSError:
            return False
    
    def prune(self, keep: int = 10) -> int:
        """Prune old checkpoints, keeping the most recent.
        
        Args:
            keep: Number of checkpoints to keep
            
        Returns:
            Number of checkpoints deleted
        """
        checkpoints = self.list()
        if len(checkpoints) <= keep:
            return 0
        
        to_delete = checkpoints[keep:]
        deleted = 0
        for cp in to_delete:
            if self.delete(cp.name):
                deleted += 1
        
        return deleted
    
    def update_metadata(self, name: str, **updates) -> bool:
        """Update checkpoint metadata.
        
        Args:
            name: Checkpoint name
            **updates: Fields to update
            
        Returns:
            True if updated successfully
        """
        metadata = self.get(name)
        if not metadata:
            return False
        
        # Update fields
        for key, value in updates.items():
            if hasattr(metadata, key):
                setattr(metadata, key, value)
        
        # Save
        metadata_path = self.storage_dir / name / self.METADATA_NAME
        try:
            with open(metadata_path, "w") as f:
                json.dump(metadata.to_dict(), f, indent=2)
            return True
        except OSError:
            return False
    
    def _collect_files(self) -> Iterator[Path]:
        """Collect files to include in checkpoint.
        
        Yields:
            Paths to files that should be checkpointed
        """
        for root, dirs, files in os.walk(self.project_root):
            root_path = Path(root)
            rel_root = root_path.relative_to(self.project_root)
            
            # Filter directories in-place to skip ignored ones
            dirs[:] = [
                d for d in dirs
                if not self.ignore_config.should_ignore(str(rel_root / d))
            ]
            
            for file in files:
                rel_path = rel_root / file
                if not self.ignore_config.should_ignore(str(rel_path)):
                    yield root_path / file
