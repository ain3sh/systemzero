"""Tests for RewindController."""

import json
import tempfile
from pathlib import Path

import pytest

from src.core.controller import RewindController
from src.config import StorageMode


@pytest.fixture
def temp_project(tmp_path):
    """Create a temporary project directory."""
    project = tmp_path / "project"
    project.mkdir()
    
    # Create test files
    (project / "app.py").write_text("print('hello')")
    (project / "README.md").write_text("# Test")
    
    return project


@pytest.fixture
def controller(temp_project, monkeypatch):
    """Create a RewindController instance."""
    # Set HOME to temp directory for global storage tests
    monkeypatch.setenv("HOME", str(temp_project.parent))
    return RewindController(project_root=temp_project)


class TestRewindController:
    def test_init_project_mode(self, controller, temp_project):
        """Test initializing in project mode."""
        result = controller.init(mode=StorageMode.PROJECT)
        
        assert result["success"]
        assert result["storageMode"] == "project"
        assert (temp_project / ".agent" / "rewind").exists()
    
    def test_init_global_mode(self, controller, temp_project):
        """Test initializing in global mode."""
        result = controller.init(mode=StorageMode.GLOBAL)
        
        assert result["success"]
        assert result["storageMode"] == "global"
    
    def test_create_checkpoint(self, controller):
        """Test creating a checkpoint."""
        controller.init()
        result = controller.create_checkpoint(description="Test checkpoint")
        
        assert result["success"]
        assert result["name"]
        assert result["fileCount"] == 2

    def test_create_checkpoint_saves_transcript_snapshot(self, controller, temp_project, tmp_path):
        """Checkpoint includes transcript snapshot when session.json provides transcript_path."""
        controller.init()

        transcript = tmp_path / "session.jsonl"
        transcript.write_text(
            json.dumps({"type": "session_start", "title": "My Session"})
            + "\n"
            + json.dumps({"id": "m1", "role": "user", "content": [{"type": "text", "text": "hi"}]})
            + "\n",
            encoding="utf-8",
        )

        controller.save_session_info(transcript_path=str(transcript), session_id="s1", agent="droid")
        result = controller.create_checkpoint(description="With transcript")
        assert result["success"]
        assert result["hasTranscript"] is True

        cp_dir = controller.get_checkpoints_dir() / result["name"]
        assert (cp_dir / "transcript.jsonl.gz").exists()

        meta = json.loads((cp_dir / "metadata.json").read_text(encoding="utf-8"))
        assert meta.get("hasTranscript") is True
        assert meta.get("transcript", {}).get("snapshot") == "transcript.jsonl.gz"

    def test_restore_context_creates_fork_session(self, controller, tmp_path):
        """Restoring context creates a forked session JSONL (does not overwrite original)."""
        controller.init()

        transcript = tmp_path / "session.jsonl"
        original = (
            json.dumps({"type": "session_start", "title": "My Session"})
            + "\n"
            + json.dumps({"id": "m1", "role": "user", "content": [{"type": "text", "text": "hi"}]})
            + "\n"
        )
        transcript.write_text(original, encoding="utf-8")
        controller.save_session_info(transcript_path=str(transcript), session_id="s1", agent="droid")

        cp = controller.create_checkpoint(description="Before")
        assert cp["success"]

        # Append more conversation after checkpoint.
        transcript.write_text(original + json.dumps({"id": "m2"}) + "\n", encoding="utf-8")

        restore = controller.restore(cp["name"], mode="context", skip_backup=True)
        assert restore["success"]
        assert restore["contextRestored"] is True
        assert restore["forkCreated"] is True
        assert restore["forkPath"]

        fork_path = Path(restore["forkPath"])
        assert fork_path.exists()
        assert transcript.read_text(encoding="utf-8") != fork_path.read_text(encoding="utf-8")

        fork_lines = fork_path.read_text(encoding="utf-8").splitlines()
        assert len(fork_lines) == 2
        first = json.loads(fork_lines[0])
        assert first["title"].startswith("[Fork] ")
        assert json.loads(fork_lines[1])["id"] == "m1"
    
    def test_list_checkpoints(self, controller):
        """Test listing checkpoints."""
        controller.init()
        controller.create_checkpoint(description="First")
        controller.create_checkpoint(description="Second")
        
        checkpoints = controller.list_checkpoints()
        
        assert len(checkpoints) == 2
    
    def test_restore_checkpoint(self, controller, temp_project):
        """Test restoring a checkpoint."""
        controller.init()
        
        # Create checkpoint
        result = controller.create_checkpoint(description="Original")
        name = result["name"]
        
        # Modify file
        (temp_project / "app.py").write_text("print('changed')")
        
        # Restore
        restore_result = controller.restore(name, skip_backup=True)
        
        assert restore_result["success"]
        assert (temp_project / "app.py").read_text() == "print('hello')"
    
    def test_undo(self, controller, temp_project):
        """Test undo operation."""
        controller.init()
        
        # Create initial checkpoint
        controller.create_checkpoint(description="Initial")
        
        # Modify and checkpoint again
        (temp_project / "app.py").write_text("print('modified')")
        controller.create_checkpoint(description="After change")
        
        # Undo should restore to initial
        result = controller.undo()
        
        assert result["success"]
        assert (temp_project / "app.py").read_text() == "print('hello')"
    
    def test_get_status(self, controller):
        """Test getting status."""
        controller.init()
        controller.create_checkpoint(description="Test")
        
        status = controller.get_status()
        
        assert status.initialized
        assert status.checkpoint_count == 1
        assert status.storage_mode == "project"
    
    def test_validate_system(self, controller):
        """Test system validation."""
        # Not initialized
        result = controller.validate_system()
        assert not result["valid"]
        
        # After init
        controller.init()
        result = controller.validate_system()
        assert result["valid"]
