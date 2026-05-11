---
name: gsigmad-handoff
description: "Generate a structured handoff document for the next agent or session. Use when switching agents or ending a complex multi-step workflow. Produces a no-overlap handoff note and copy-pasteable resume prompt."
disable-model-invocation: true
allowed-tools: Read, Write, Bash
---

# Cross-Agent Handoff ($cross-agent-handoff + $change-log-compliance)

Produce a no-overlap handoff note and resume prompt for another agent/model to continue work.

## Handoff Protocol

1. Read `.agent/task.md` for current state.
2. Identify:
   - Completed items (with EXP/PROMPT numbers and result paths)
   - In-progress items (with exact state and next action)
   - Blocked items (with blocker description)
   - Reserved EXP/PROMPT numbers not yet used
3. Check for active locks in `.agent/locks/`.

## Generate Handoff Note

Create a structured handoff block:

```
HANDOFF NOTE
From: Claude Code (claude-sonnet-4-6)
Timestamp: [UTC]
Session ID: [SESSION_ID]
Project: [PROJECT_PATH]

COMPLETED:
- [x] EXP-### — description (results: path)

IN PROGRESS:
- [/] EXP-### — description (state: X, next: Y)

BLOCKED:
- [ ] EXP-### — description (blocker: Z)

NO-OVERLAP SCOPE:
- Active locks: [list from .agent/locks/]
- Reserved IDs: EXP-###, PROMPT-###

RESUME PROMPT:
[Exact text the next agent should receive to continue seamlessly]
```

## Generate Resume Prompt

Write a complete, self-contained prompt the next agent can use:
- Include project path, active scope, and no-overlap guards
- Reference specific file paths for context
- Include the exact next action to take
- Include non-negotiables reminder

## Report Back

- Handoff note (structured block above)
- Resume prompt (copy-pasteable)
- Files that need attention
- Active locks status
