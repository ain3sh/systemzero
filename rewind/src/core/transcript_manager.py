"""Transcript management for Rewind.

The transcript JSONL at `transcript_path` is the source of truth for
conversation state for both Claude Code and Factory Droid.

This module provides efficient primitives for:
- Detecting agent kind (best-effort)
- Capturing a compressed snapshot of the transcript
- Computing a stable cursor (byte offset of last complete JSONL line)
- Creating a forked transcript session file from a checkpoint
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..agents.registry import AgentRegistry


AgentKind = str


@dataclass(frozen=True, slots=True)
class TranscriptCursor:
    """Cursor describing a transcript state at a point in time."""

    byte_offset_end: int
    last_event_id: str | None
    prefix_sha256: str
    tail_sha256: str


@dataclass(frozen=True, slots=True)
class TranscriptSnapshot:
    """Snapshot information for a transcript saved into a checkpoint."""

    agent: AgentKind
    original_path: str
    snapshot_relpath: str  # relative to checkpoint dir
    cursor: TranscriptCursor


@dataclass(frozen=True, slots=True)
class BoundaryResult:
    """Boundary information for rewinding by user prompts."""

    boundary_offset: int
    prompts: list[str]


class TranscriptManagerError(Exception):
    """Raised when transcript operations fail."""


class TranscriptManager:
    """Efficient transcript snapshot and fork creation."""

    PREFIX_HASH_BYTES = 64 * 1024
    TAIL_HASH_BYTES = 64 * 1024

    def __init__(self) -> None:
        self._registry = AgentRegistry.load_bundled()

    def _title_prefix_enabled(self, agent: str | None) -> bool:
        if not agent:
            return False
        profile = self._registry.get(agent)
        if not profile:
            return False
        transcript = profile.data.get("transcript") if isinstance(profile.data, dict) else None
        if not isinstance(transcript, dict):
            return False
        tp = transcript.get("title_prefix")
        if not isinstance(tp, dict):
            return False
        if tp.get("enabled") is False:
            return False
        return tp.get("json_path", "$.title") == "$.title"

    def detect_agent(self, transcript_path: Path) -> AgentKind:
        p = str(transcript_path)

        for profile in self._registry.all():
            transcript = profile.data.get("transcript") if isinstance(profile.data, dict) else None
            if not isinstance(transcript, dict):
                continue
            regexes = transcript.get("path_regexes")
            if not isinstance(regexes, list):
                continue
            for pat in regexes:
                if isinstance(pat, str) and pat and re.search(pat, p):
                    return profile.id

        # Best-effort sniff from first non-empty JSON line
        try:
            with open(transcript_path, "rb") as f:
                for _ in range(20):
                    line = f.readline()
                    if not line:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(obj, dict):
                        if "uuid" in obj or "parentUuid" in obj:
                            return "claude"
                        if "id" in obj or "parentId" in obj:
                            return "droid"
        except OSError:
            pass

        return "unknown"

    def compute_cursor(self, transcript_path: Path, *, last_event_id_fields: list[str] | None = None) -> TranscriptCursor:
        """Compute cursor for transcript.

        Cursor points to the end of the last complete JSONL line.
        """
        try:
            file_size = os.path.getsize(transcript_path)
        except OSError as e:
            raise TranscriptManagerError(f"Unable to stat transcript: {e}") from e

        prefix_sha256 = self._hash_prefix(transcript_path)
        tail_sha256 = self._hash_tail(transcript_path)

        if file_size == 0:
            return TranscriptCursor(
                byte_offset_end=0,
                last_event_id=None,
                prefix_sha256=prefix_sha256,
                tail_sha256=tail_sha256,
            )

        try:
            with open(transcript_path, "rb") as f:
                byte_offset_end = self._find_last_complete_line_end(f, file_size)
                last_event_id = self._read_last_event_id(
                    f,
                    byte_offset_end,
                    fields=last_event_id_fields or ["uuid", "id"],
                )
        except OSError as e:
            raise TranscriptManagerError(f"Unable to read transcript: {e}") from e

        return TranscriptCursor(
            byte_offset_end=byte_offset_end,
            last_event_id=last_event_id,
            prefix_sha256=prefix_sha256,
            tail_sha256=tail_sha256,
        )

    def snapshot_into_checkpoint(
        self,
        transcript_path: Path,
        checkpoint_dir: Path,
        *,
        agent_hint: str | None = None,
    ) -> TranscriptSnapshot:
        """Write a compressed transcript snapshot into a checkpoint directory."""

        agent = agent_hint or self.detect_agent(transcript_path)
        last_event_id_fields: list[str] | None = None
        profile = self._registry.get(agent) if agent else None
        if profile is not None:
            transcript = profile.data.get("transcript") if isinstance(profile.data, dict) else None
            if isinstance(transcript, dict):
                fields = transcript.get("last_event_id_fields")
                if isinstance(fields, list) and all(isinstance(x, str) for x in fields):
                    last_event_id_fields = [str(x) for x in fields]

        cursor = self.compute_cursor(transcript_path, last_event_id_fields=last_event_id_fields)

        snapshot_name = "transcript.jsonl.gz"
        snapshot_path = checkpoint_dir / snapshot_name
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        try:
            with open(transcript_path, "rb") as src, gzip.open(snapshot_path, "wb") as dst:
                # Copy whole file as-is; cursor allows fast fork creation later.
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    dst.write(chunk)
        except OSError as e:
            raise TranscriptManagerError(f"Failed to snapshot transcript: {e}") from e

        return TranscriptSnapshot(
            agent=agent,
            original_path=str(transcript_path),
            snapshot_relpath=snapshot_name,
            cursor=cursor,
        )

    def find_boundary_by_user_prompts(self, transcript_path: Path, n: int) -> BoundaryResult:
        """Find a rewind boundary by counting the last N user prompts.

        Returns the byte offset of the start of the Nth-most-recent user message line,
        plus the extracted prompt texts (chronological order).
        """
        if n <= 0:
            raise ValueError("n must be >= 1")

        try:
            file_size = os.path.getsize(transcript_path)
        except OSError as e:
            raise TranscriptManagerError(f"Unable to stat transcript: {e}") from e

        if file_size == 0:
            raise TranscriptManagerError("Transcript is empty")

        prompts_newest_first: list[str] = []
        boundary_offset: int | None = None

        chunk_size = 128 * 1024
        end_offset = file_size
        buf = b""
        buf_start_offset = end_offset

        def process_line(line_bytes: bytes, line_start: int) -> None:
            nonlocal boundary_offset

            if not line_bytes:
                return
            line_bytes = line_bytes.rstrip(b"\r")
            if not line_bytes.strip():
                return

            try:
                obj = json.loads(line_bytes)
            except json.JSONDecodeError:
                return
            if not isinstance(obj, dict):
                return
            if not self._is_user_message(obj):
                return

            prompts_newest_first.append(self._extract_prompt_text(obj, fallback=obj))
            if len(prompts_newest_first) == n:
                boundary_offset = line_start

        try:
            with open(transcript_path, "rb") as f:
                while end_offset > 0 and boundary_offset is None:
                    start_offset = max(0, end_offset - chunk_size)
                    read_size = end_offset - start_offset
                    f.seek(start_offset)
                    data = f.read(read_size)

                    buf = data + buf
                    buf_start_offset = start_offset
                    end_offset = start_offset

                    while boundary_offset is None:
                        idx = buf.rfind(b"\n")
                        if idx == -1:
                            break

                        line = buf[idx + 1 :]
                        line_start = buf_start_offset + idx + 1
                        buf = buf[:idx]
                        process_line(line, line_start)

                if boundary_offset is None and buf:
                    process_line(buf, buf_start_offset)
        except OSError as e:
            raise TranscriptManagerError(f"Unable to read transcript: {e}") from e

        if boundary_offset is None:
            raise TranscriptManagerError(f"Not enough user prompts (requested {n}, found {len(prompts_newest_first)})")

        prompts = list(reversed(prompts_newest_first))
        return BoundaryResult(boundary_offset=boundary_offset, prompts=prompts)

    def create_fork_at_offset(
        self,
        *,
        current_transcript_path: Path,
        boundary_offset: int,
        fork_dir: Path | None = None,
        rewrite_title_prefix: str | None = "[Fork] ",
        agent: str | None = None,
    ) -> Path:
        fork_parent = fork_dir or current_transcript_path.parent
        fork_parent.mkdir(parents=True, exist_ok=True)
        fork_path = fork_parent / f"{uuid.uuid4()}.jsonl"

        self._copy_prefix(current_transcript_path, fork_path, boundary_offset)
        self._ensure_trailing_newline(fork_path)

        if rewrite_title_prefix and self._title_prefix_enabled(agent):
            try:
                self._prefix_first_title_field(fork_path, rewrite_title_prefix)
            except Exception:
                pass

        return fork_path

    def rewrite_in_place_at_offset(
        self,
        *,
        current_transcript_path: Path,
        boundary_offset: int,
        backup_dir: Path,
    ) -> Path:
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4()}.jsonl"

        try:
            if current_transcript_path.exists():
                import shutil

                shutil.copy2(current_transcript_path, backup_path)

            tmp_path = current_transcript_path.with_suffix(current_transcript_path.suffix + ".tmp")
            self._copy_prefix(current_transcript_path, tmp_path, boundary_offset)
            self._ensure_trailing_newline(tmp_path)
            os.replace(tmp_path, current_transcript_path)
        except OSError as e:
            raise TranscriptManagerError(f"Failed to rewrite transcript in-place: {e}") from e

        return backup_path

    @staticmethod
    def _is_user_message(obj: dict[str, Any]) -> bool:
        return obj.get("role") == "user"

    @staticmethod
    def _extract_prompt_text(obj: dict[str, Any], *, fallback: Any) -> str:
        content = obj.get("content")
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and isinstance(block.get("text"), str):
                    parts.append(str(block.get("text")))
            if parts:
                return "\n".join(parts).strip()

        try:
            return json.dumps(fallback, ensure_ascii=False)
        except Exception:
            return ""

    def prefix_matches(self, transcript_path: Path, expected_prefix_sha256: str) -> bool:
        try:
            return self._hash_prefix(transcript_path) == expected_prefix_sha256
        except TranscriptManagerError:
            return False

    def create_fork_session(
        self,
        *,
        checkpoint_cursor: TranscriptCursor,
        checkpoint_snapshot_gz: Path | None,
        current_transcript_path: Path,
        fork_dir: Path | None = None,
        rewrite_title_prefix: str | None = "[Fork] ",
        agent: str | None = None,
    ) -> Path:
        """Create a new forked session JSONL file.

        Returns the created fork path.
        """
        fork_parent = fork_dir or current_transcript_path.parent
        fork_parent.mkdir(parents=True, exist_ok=True)
        fork_path = fork_parent / f"{uuid.uuid4()}.jsonl"

        # Fast path: copy the prefix from current transcript and truncate at cursor.
        if self.prefix_matches(current_transcript_path, checkpoint_cursor.prefix_sha256):
            self._copy_prefix(current_transcript_path, fork_path, checkpoint_cursor.byte_offset_end)
        else:
            if checkpoint_snapshot_gz is None:
                raise TranscriptManagerError(
                    "Transcript prefix mismatch and no checkpoint snapshot available"
                )
            self._inflate_gz(checkpoint_snapshot_gz, fork_path)

        self._ensure_trailing_newline(fork_path)

        if rewrite_title_prefix and self._title_prefix_enabled(agent):
            try:
                self._prefix_first_title_field(fork_path, rewrite_title_prefix)
            except Exception:
                # Best-effort; do not fail fork creation.
                pass

        return fork_path

    # -----------------
    # Internal helpers
    # -----------------

    def _hash_prefix(self, transcript_path: Path) -> str:
        try:
            with open(transcript_path, "rb") as f:
                data = f.read(self.PREFIX_HASH_BYTES)
            return hashlib.sha256(data).hexdigest()
        except OSError as e:
            raise TranscriptManagerError(f"Failed to hash prefix: {e}") from e

    def _hash_tail(self, transcript_path: Path) -> str:
        try:
            size = os.path.getsize(transcript_path)
            start = max(0, size - self.TAIL_HASH_BYTES)
            with open(transcript_path, "rb") as f:
                f.seek(start)
                data = f.read(self.TAIL_HASH_BYTES)
            return hashlib.sha256(data).hexdigest()
        except OSError as e:
            raise TranscriptManagerError(f"Failed to hash tail: {e}") from e

    @staticmethod
    def _find_last_complete_line_end(f, file_size: int) -> int:
        """Return the file offset immediately after the last complete line."""
        if file_size == 0:
            return 0

        # If file already ends with newline, we're done.
        f.seek(file_size - 1)
        last = f.read(1)
        if last == b"\n":
            return file_size

        # Otherwise scan backwards in chunks to find the final newline.
        chunk_size = 64 * 1024
        pos = file_size
        while pos > 0:
            read_size = min(chunk_size, pos)
            pos -= read_size
            f.seek(pos)
            chunk = f.read(read_size)
            idx = chunk.rfind(b"\n")
            if idx != -1:
                return pos + idx + 1

        # No newline found; treat entire file as a single line.
        return file_size

    @staticmethod
    def _read_last_event_id(f, byte_offset_end: int, *, fields: list[str]) -> str | None:
        if byte_offset_end == 0:
            return None

        # Find the last complete line by scanning backwards.
        # Note: byte_offset_end may point to a newline boundary; in that case,
        # parse the preceding line.
        start = max(0, byte_offset_end - 64 * 1024)
        f.seek(start)
        buf = f.read(byte_offset_end - start)

        # Drop trailing newline(s) so we capture the last non-empty line.
        buf = buf.rstrip(b"\n\r")

        idx = buf.rfind(b"\n")
        last_line = buf[idx + 1 :] if idx != -1 else buf
        last_line = last_line.strip()
        if not last_line:
            return None

        try:
            obj = json.loads(last_line)
        except json.JSONDecodeError:
            return None
        if not isinstance(obj, dict):
            return None

        for field in fields:
            if not field:
                continue
            if field in obj and obj.get(field) is not None:
                val = obj.get(field)
                return str(val) if val is not None else None
        return None

    @staticmethod
    def _copy_prefix(src_path: Path, dst_path: Path, byte_count: int) -> None:
        try:
            with open(src_path, "rb") as src, open(dst_path, "wb") as dst:
                remaining = byte_count
                while remaining > 0:
                    chunk = src.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    dst.write(chunk)
                    remaining -= len(chunk)
        except OSError as e:
            raise TranscriptManagerError(f"Failed to copy prefix: {e}") from e

    @staticmethod
    def _inflate_gz(gz_path: Path, dst_path: Path) -> None:
        try:
            with gzip.open(gz_path, "rb") as src, open(dst_path, "wb") as dst:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    dst.write(chunk)
        except OSError as e:
            raise TranscriptManagerError(f"Failed to inflate snapshot: {e}") from e

    @staticmethod
    def _ensure_trailing_newline(path: Path) -> None:
        try:
            size = os.path.getsize(path)
            if size == 0:
                return
            with open(path, "rb+") as f:
                f.seek(size - 1)
                last = f.read(1)
                if last != b"\n":
                    f.seek(size)
                    f.write(b"\n")
        except OSError:
            # Best-effort
            return

    @staticmethod
    def _prefix_first_title_field(path: Path, prefix: str, max_lines: int = 50) -> None:
        """Prefix the first JSON object containing a 'title' field."""
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        replaced = False

        with open(path, "rb") as src, open(tmp_path, "wb") as dst:
            for i in range(max_lines):
                line = src.readline()
                if not line:
                    break
                if replaced:
                    dst.write(line)
                    continue

                stripped = line.strip()
                if not stripped:
                    dst.write(line)
                    continue

                try:
                    obj = json.loads(stripped)
                except json.JSONDecodeError:
                    dst.write(line)
                    continue

                if isinstance(obj, dict) and isinstance(obj.get("title"), str):
                    title = obj["title"]
                    if not title.startswith(prefix):
                        obj["title"] = prefix + title
                    new_line = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
                    dst.write(new_line)
                    replaced = True
                else:
                    dst.write(line)

            # Copy remainder
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                dst.write(chunk)

        os.replace(tmp_path, path)
