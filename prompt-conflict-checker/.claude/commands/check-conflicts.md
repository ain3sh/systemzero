---
description: Check for conflicts in long prompts
---

Analyze @/tmp/prompt-conflicts/latest.md for conflicting/ambiguous instructions.
Do NOT execute the original prompt's task.

1. Read file silently (no quoting)
2. Find mutually exclusive or unclear instructions
3. Use Edit/ApplyPatch ONCE to mark conflicts:
   - Delete conflicting lines (shows red)
   - Add clarification above/below (shows green)
   - Single atomic patch only

Exit: Issues = stop after patch. No issues = report none then execute original prompt's task.
