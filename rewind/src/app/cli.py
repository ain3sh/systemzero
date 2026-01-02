"""System Zero Rewind CLI (v4, redesigned).

Principles:
- Safe by default: never destroy the current transcript.
- Minimal muscle memory: `rewind` (interactive), `rewind save`, `rewind jump`.
- Stdlib-only interactive UI.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from ..core.controller import RewindController


DEFAULT_LIST_LIMIT = 20
DEFAULT_GC_KEEP = 50


@dataclass(frozen=True, slots=True)
class Selection:
    checkpoint: str
    intent: str  # "jump" | "code" | "chat"


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rewind",
        description="System Zero Rewind - checkpoints + jump for AI coding agent sessions",
    )
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version="%(prog)s 1.0.0",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug output",
    )

    subparsers = parser.add_subparsers(dest="command")

    save = subparsers.add_parser("save", help="Create a checkpoint")
    save.add_argument("message", nargs="*", help="Optional description")

    jump = subparsers.add_parser("jump", help="Jump to a checkpoint (restore code + fork chat)")
    jump.add_argument(
        "selector",
        nargs="?",
        default="last",
        help="last | prev | N | <checkpoint-name>",
    )

    subparsers.add_parser("list", help="List recent checkpoints")

    subparsers.add_parser("gc", help="Garbage collect old checkpoints")

    back = subparsers.add_parser(
        "back",
        help="Rewind by the last N user prompts (non-interactive, fast)",
    )
    back.add_argument(
        "n",
        nargs="?",
        default=1,
        type=int,
        help="Number of user prompts to rewind (default: 1)",
    )
    back.add_argument(
        "--both",
        action="store_true",
        help="Also restore code to the nearest checkpoint at-or-before the chat boundary",
    )
    back.add_argument(
        "--in-place",
        action="store_true",
        help="Rewrite the current transcript in-place (creates a safety backup)",
    )
    back.add_argument(
        "--copy",
        action="store_true",
        help="Copy reverted prompt(s) to clipboard (best-effort)",
    )

    rewrite = subparsers.add_parser(
        "rewrite-chat",
        help="DESTRUCTIVE: rewrite current chat transcript in-place",
    )
    rewrite.add_argument(
        "selector",
        nargs="?",
        default="last",
        help="last | prev | N | <checkpoint-name>",
    )

    return parser


def main(args: list[str] | None = None) -> int:
    parser = create_parser()
    parsed = parser.parse_args(args)

    if parsed.debug:
        os.environ["REWIND_DEBUG"] = "1"

    controller = RewindController(project_root=_determine_project_root())

    if not parsed.command:
        return cmd_interactive(controller)

    if parsed.command == "save":
        return cmd_save(parsed, controller)
    if parsed.command == "jump":
        return cmd_jump(parsed, controller)
    if parsed.command == "list":
        return cmd_list(controller)
    if parsed.command == "gc":
        return cmd_gc(controller)
    if parsed.command == "back":
        return cmd_back(parsed, controller)
    if parsed.command == "rewrite-chat":
        return cmd_rewrite_chat(parsed, controller)

    parser.print_help()
    return 1


def cmd_save(args: argparse.Namespace, controller: RewindController) -> int:
    description = " ".join(args.message).strip() if args.message else "Manual checkpoint"
    result = controller.create_checkpoint(description=description)
    if not result.get("success"):
        print(f"Error: {result.get('error')}", file=sys.stderr)
        return 1

    chat = "yes" if result.get("hasTranscript") else "no"
    print(f"Saved: {result['name']}  (code: {result.get('fileCount', 0)} files, chat: {chat})")
    return 0


def cmd_jump(args: argparse.Namespace, controller: RewindController) -> int:
    checkpoints = controller.list_checkpoints()
    if not checkpoints:
        print("No checkpoints found.")
        return 1

    name = resolve_selector(args.selector, checkpoints)
    if not name:
        print("Invalid selector or checkpoint not found.")
        return 1

    result = controller.restore(name=name, mode="all", skip_backup=False)
    return _print_restore_result(result)


def cmd_list(controller: RewindController) -> int:
    checkpoints = controller.list_checkpoints()
    if not checkpoints:
        print("No checkpoints found.")
        return 0

    shown = checkpoints[:DEFAULT_LIST_LIMIT]

    print("#  Chat  Name                       Files   Description")
    for idx, cp in enumerate(shown, 1):
        chat_icon = "💬" if getattr(cp, "has_transcript", False) else "  "
        name = cp.name
        files = str(cp.file_count)
        desc = (cp.description or "").strip()
        print(f"{idx:<2} {chat_icon:<4} {name:<26} {files:<6} {desc}")

    if len(checkpoints) > DEFAULT_LIST_LIMIT:
        print(f"\nShowing last {DEFAULT_LIST_LIMIT}. Use `rewind` to search older checkpoints.")

    return 0


def cmd_gc(controller: RewindController) -> int:
    checkpoints = controller.list_checkpoints()
    if len(checkpoints) <= DEFAULT_GC_KEEP:
        print(f"Nothing to clean up ({len(checkpoints)} checkpoints, keeping {DEFAULT_GC_KEEP}).")
        return 0

    keep = _prompt_int(f"Keep how many checkpoints? [{DEFAULT_GC_KEEP}] ", DEFAULT_GC_KEEP)
    if keep < 1:
        print("Keep must be >= 1")
        return 1

    if len(checkpoints) <= keep:
        print(f"Nothing to clean up ({len(checkpoints)} checkpoints, keeping {keep}).")
        return 0

    to_delete = checkpoints[keep:]
    print(f"Will delete {len(to_delete)} checkpoints (keeping {keep}).")
    for cp in to_delete[:10]:
        desc = cp.description or "(no description)"
        print(f"  - {cp.name}: {desc}")
    if len(to_delete) > 10:
        print(f"  ... and {len(to_delete) - 10} more")

    confirm = input("Proceed? [y/N] ").strip().lower()
    if confirm != "y":
        print("Canceled.")
        return 0

    deleted = controller.store.prune(keep=keep)
    print(f"Deleted {deleted} checkpoints.")
    return 0


def cmd_rewrite_chat(args: argparse.Namespace, controller: RewindController) -> int:
    checkpoints = controller.list_checkpoints()
    if not checkpoints:
        print("No checkpoints found.")
        return 1

    name = resolve_selector(args.selector, checkpoints)
    if not name:
        print("Invalid selector or checkpoint not found.")
        return 1

    print("This will rewrite your current agent transcript in-place.")
    print("A backup will be written to `.agent/rewind/transcript-backup/`.\n")
    typed = input("Type REWRITE to continue: ").strip()
    if typed != "REWRITE":
        print("Canceled.")
        return 0

    result = cast(Any, controller).restore(name=name, mode="context", skip_backup=True, transcript_restore="in_place")
    return _print_restore_result(result)


def cmd_back(args: argparse.Namespace, controller: RewindController) -> int:
    n = int(getattr(args, "n", 1))
    if n <= 0:
        print("Error: n must be >= 1", file=sys.stderr)
        return 2

    both = bool(getattr(args, "both", False))
    in_place = bool(getattr(args, "in_place", False))
    copy_prompts = bool(getattr(args, "copy", False))

    result = controller.rewind_back(n, both=both, in_place=in_place, copy=copy_prompts)
    if not result.get("success"):
        print(f"Error: {result.get('error')}", file=sys.stderr)
        return 1

    prompts = result.get("prompts")
    prompts_list = prompts if isinstance(prompts, list) else []

    if result.get("codeCheckpoint"):
        print(f"Code restored to: {result['codeCheckpoint']}", file=sys.stderr)
    if result.get("note"):
        print(str(result.get("note")), file=sys.stderr)

    prompts_text = "\n\n".join(str(p) for p in prompts_list if p is not None).strip()
    if prompts_text:
        if copy_prompts and _try_copy_to_clipboard(prompts_text):
            print("Copied reverted prompt(s) to clipboard.", file=sys.stderr)
        else:
            _print_reverted_prompts(prompts_list, n=n)

    if result.get("forkCreated"):
        print(f"Fork created: {result.get('forkSessionId')}")
        return 0

    print("Chat rewritten in-place")
    if result.get("backupPath"):
        print(f"Backup: {result.get('backupPath')}", file=sys.stderr)
    return 0


def cmd_interactive(controller: RewindController) -> int:
    checkpoints = controller.list_checkpoints()
    if not checkpoints:
        print("No checkpoints found.")
        print("Run `rewind save` to create one.")
        return 0

    selection = interactive_select(checkpoints)
    if selection is None:
        return 0

    if selection.intent == "jump":
        result = controller.restore(name=selection.checkpoint, mode="all", skip_backup=False)
        return _print_restore_result(result)

    if selection.intent == "code":
        result = controller.restore(name=selection.checkpoint, mode="code", skip_backup=False)
        return _print_restore_result(result)

    if selection.intent == "chat":
        result = controller.restore(name=selection.checkpoint, mode="context", skip_backup=True)
        return _print_restore_result(result)

    return 1


def interactive_select(checkpoints) -> Selection | None:
    filtered = checkpoints

    while True:
        print("\nPick a checkpoint (enter number, type to filter, or 'q' to quit):")
        shown = filtered[:30]
        for idx, cp in enumerate(shown, 1):
            chat_icon = "💬" if getattr(cp, "has_transcript", False) else "  "
            desc = (cp.description or "").strip()
            print(f"  {idx:>2}. {chat_icon} {cp.name}  {desc}")
        if len(filtered) > 30:
            print(f"  ... and {len(filtered) - 30} more")

        raw = input("> ").strip()
        if raw.lower() in {"q", "quit", "exit"}:
            return None

        if raw.isdigit():
            n = int(raw)
            if 1 <= n <= len(shown):
                chosen = shown[n - 1].name
                break
            print("Invalid number.")
            continue

        if not raw:
            continue

        needle = raw.lower()
        filtered = [cp for cp in checkpoints if needle in (cp.name + " " + (cp.description or "")).lower()]
        if not filtered:
            print("No matches.")
            filtered = checkpoints

    print("\nPick an intent:")
    print("  1) Jump        (restore code + fork chat)  [default]")
    print("  2) Code only   (restore code only)")
    print("  3) Chat fork   (create forked session only)")
    intent_raw = input("> ").strip()

    intent = "jump"
    if intent_raw == "2":
        intent = "code"
    elif intent_raw == "3":
        intent = "chat"

    return Selection(checkpoint=chosen, intent=intent)


def resolve_selector(selector: str, checkpoints) -> str | None:
    s = (selector or "last").strip()
    if not s or s == "last":
        return checkpoints[0].name
    if s == "prev":
        return checkpoints[1].name if len(checkpoints) > 1 else None
    if s.isdigit():
        n = int(s)
        if 1 <= n <= len(checkpoints):
            return checkpoints[n - 1].name
        return None

    # Exact name match
    for cp in checkpoints:
        if cp.name == s:
            return cp.name
    return None


def _print_restore_result(result: dict) -> int:
    if not result.get("success"):
        print(f"Error: {result.get('error')}", file=sys.stderr)
        if result.get("contextError"):
            print(f"Chat error: {result.get('contextError')}", file=sys.stderr)
        return 1

    name = result.get("name", "")
    if result.get("codeRestored"):
        print(f"Code restored to: {name}")
    elif result.get("success") and result.get("forkCreated") is not None:
        # context-only
        print(f"Chat restored from: {name}")

    if result.get("contextRestored"):
        if result.get("forkCreated") and result.get("forkPath"):
            print(f"Chat fork: {result['forkPath']}")
            print("Next: select the forked session in your agent session list")
        elif result.get("forkCreated") is False:
            print("Chat rewritten in-place")
    elif result.get("contextRequested"):
        print("Chat rewind unavailable for this checkpoint/session")

    return 0


def _prompt_int(prompt: str, default: int) -> int:
    raw = input(prompt).strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _determine_project_root() -> Path:
    val = os.environ.get("REWIND_PROJECT_ROOT")
    if isinstance(val, str) and val.strip():
        return Path(val.strip()).expanduser()
    return Path.cwd()


def _print_reverted_prompts(prompts: list[Any], *, n: int) -> None:
    clean = [str(p).strip() for p in prompts if p is not None and str(p).strip()]
    if not clean:
        return
    print(f"Reverted prompts (n={n}):", file=sys.stderr)
    print("---", file=sys.stderr)
    print("\n\n".join(clean), file=sys.stderr)
    print("---", file=sys.stderr)


def _try_copy_to_clipboard(text: str) -> bool:
    if not text:
        return False

    candidates: list[list[str]] = [
        ["pbcopy"],
        ["wl-copy"],
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
        ["clip.exe"],
    ]

    data = text.encode("utf-8")
    for cmd in candidates:
        try:
            proc = subprocess.run(
                cmd,
                input=data,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
                timeout=2,
            )
            if proc.returncode == 0:
                return True
        except Exception:
            continue
    return False


if __name__ == "__main__":
    sys.exit(main())
