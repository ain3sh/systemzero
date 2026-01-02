"""Tests for hook handling."""

import json
import io
import sys
from unittest.mock import patch

import pytest

from src.integrations.hooks.types import PreToolUseInput, SessionStartInput
from src.integrations.hooks.io import read_input, read_input_as, HookInputError


class TestHookTypes:
    def test_pre_tool_use_input(self):
        """Test PreToolUseInput dataclass."""
        inp = PreToolUseInput(
            session_id="test-session",
            transcript_path="/tmp/transcript",
            cwd="/home/user/project",
            hook_event_name="PreToolUse",
            tool_name="Edit",
            tool_input={"file_path": "/home/user/project/app.py"},
        )
        
        assert inp.tool_name == "Edit"
        assert inp.tool_input["file_path"] == "/home/user/project/app.py"
    
    def test_session_start_input(self):
        """Test SessionStartInput dataclass."""
        inp = SessionStartInput(
            session_id="test-session",
            transcript_path="/tmp/transcript",
            cwd="/home/user/project",
            hook_event_name="SessionStart",
            source="startup",
        )
        
        assert inp.source == "startup"


class TestHookIO:
    def test_read_input_pre_tool_use(self):
        """Test reading PreToolUse input from stdin."""
        input_data = json.dumps({
            "session_id": "test",
            "transcript_path": "/tmp/t",
            "cwd": "/home/user",
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "app.py"},
        })
        
        with patch.object(sys, 'stdin', io.StringIO(input_data)):
            result = read_input()
        
        assert isinstance(result, PreToolUseInput)
        assert result.tool_name == "Edit"
    
    def test_read_input_session_start(self):
        """Test reading SessionStart input from stdin."""
        input_data = json.dumps({
            "session_id": "test",
            "transcript_path": "/tmp/t",
            "cwd": "/home/user",
            "hook_event_name": "SessionStart",
            "source": "startup",
        })
        
        with patch.object(sys, 'stdin', io.StringIO(input_data)):
            result = read_input()
        
        assert isinstance(result, SessionStartInput)
        assert result.source == "startup"
    
    def test_read_input_as_correct_type(self):
        """Test read_input_as with correct type."""
        input_data = json.dumps({
            "session_id": "test",
            "transcript_path": "/tmp/t",
            "cwd": "/home/user",
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {},
        })
        
        with patch.object(sys, 'stdin', io.StringIO(input_data)):
            result = read_input_as(PreToolUseInput)
        
        assert isinstance(result, PreToolUseInput)
    
    def test_read_input_as_wrong_type(self):
        """Test read_input_as with wrong type raises error."""
        input_data = json.dumps({
            "session_id": "test",
            "transcript_path": "/tmp/t",
            "cwd": "/home/user",
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {},
        })
        
        with patch.object(sys, 'stdin', io.StringIO(input_data)):
            with pytest.raises(HookInputError):
                read_input_as(SessionStartInput)
    
    def test_read_input_empty_stdin(self):
        """Test read_input with empty stdin raises error."""
        with patch.object(sys, 'stdin', io.StringIO("")):
            with pytest.raises(HookInputError):
                read_input()
    
    def test_read_input_invalid_json(self):
        """Test read_input with invalid JSON raises error."""
        with patch.object(sys, 'stdin', io.StringIO("not json")):
            with pytest.raises(HookInputError):
                read_input()
