"""Tests for checkpoint store."""

import json
import tempfile
from pathlib import Path

import pytest

from src.core.checkpoint_store import CheckpointStore
from src.config.types import IgnoreConfig


@pytest.fixture
def temp_project(tmp_path):
    """Create a temporary project directory with test files."""
    project = tmp_path / "project"
    project.mkdir()
    
    # Create some test files
    (project / "app.py").write_text("print('hello')")
    (project / "README.md").write_text("# Test Project")
    (project / "src").mkdir()
    (project / "src" / "main.py").write_text("def main(): pass")
    
    # Create ignored directories
    (project / "node_modules").mkdir()
    (project / "node_modules" / "pkg.js").write_text("ignored")
    (project / ".git").mkdir()
    (project / ".git" / "config").write_text("ignored")
    
    return project


@pytest.fixture
def storage_dir(tmp_path):
    """Create a temporary storage directory."""
    storage = tmp_path / "storage"
    storage.mkdir()
    return storage


@pytest.fixture
def store(storage_dir, temp_project):
    """Create a CheckpointStore instance."""
    return CheckpointStore(
        storage_dir=storage_dir,
        project_root=temp_project,
        ignore_config=IgnoreConfig(),
    )


class TestCheckpointStore:
    def test_create_checkpoint(self, store):
        """Test creating a checkpoint."""
        result = store.create(description="Test checkpoint")
        
        assert result.success
        assert result.name
        assert result.file_count == 3  # app.py, README.md, src/main.py
    
    def test_list_checkpoints(self, store):
        """Test listing checkpoints."""
        # Create a few checkpoints
        store.create(description="First")
        store.create(description="Second")
        
        checkpoints = store.list()
        
        assert len(checkpoints) == 2
        # Newest first
        assert checkpoints[0].description == "Second"
        assert checkpoints[1].description == "First"
    
    def test_restore_checkpoint(self, store, temp_project):
        """Test restoring a checkpoint."""
        # Create checkpoint
        result = store.create(description="Before change")
        checkpoint_name = result.name
        
        # Modify a file
        (temp_project / "app.py").write_text("print('modified')")
        
        # Restore
        restore_result = store.restore(checkpoint_name, backup=False)
        
        assert restore_result.success
        assert (temp_project / "app.py").read_text() == "print('hello')"
    
    def test_delete_checkpoint(self, store):
        """Test deleting a checkpoint."""
        result = store.create(description="To delete")
        name = result.name
        
        assert len(store.list()) == 1
        
        deleted = store.delete(name)
        
        assert deleted
        assert len(store.list()) == 0
    
    def test_prune_checkpoints(self, store):
        """Test pruning old checkpoints."""
        # Create several checkpoints
        for i in range(5):
            store.create(description=f"Checkpoint {i}")
        
        assert len(store.list()) == 5
        
        # Prune to keep only 2
        deleted = store.prune(keep=2)
        
        assert deleted == 3
        assert len(store.list()) == 2
    
    def test_ignores_node_modules(self, store, temp_project):
        """Test that node_modules is ignored."""
        result = store.create(description="Test")
        
        # Should not include node_modules files
        assert result.file_count == 3
    
    def test_ignores_git_directory(self, store, temp_project):
        """Test that .git is ignored."""
        result = store.create(description="Test")
        
        # Should not include .git files
        assert result.file_count == 3


class TestIgnoreConfig:
    def test_should_ignore_node_modules(self):
        """Test ignoring node_modules."""
        config = IgnoreConfig()
        
        assert config.should_ignore("node_modules")
        assert config.should_ignore("node_modules/package/index.js")
    
    def test_should_ignore_git(self):
        """Test ignoring .git."""
        config = IgnoreConfig()
        
        assert config.should_ignore(".git")
        assert config.should_ignore(".git/config")
    
    def test_should_not_ignore_regular_files(self):
        """Test that regular files are not ignored."""
        config = IgnoreConfig()
        
        assert not config.should_ignore("app.py")
        assert not config.should_ignore("src/main.py")
        assert not config.should_ignore("README.md")
    
    def test_force_include(self):
        """Test force include overrides ignore."""
        config = IgnoreConfig(
            patterns=["*.env"],
            force_include=[".env.example"],
        )
        
        assert config.should_ignore(".env")
        assert not config.should_ignore(".env.example")
