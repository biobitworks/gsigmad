---
name: gsigmad-session-start
description: "Display active EXP status across all projects at session start. Invoked automatically at the beginning of every Claude session. Checks goal alignment, runs drift detection if >= 5 experiments since last check, and reports PROMPT integrity."
allowed-tools: Read, Bash, Glob, Grep
---

# Session Start ($session-orchestrator + $change-log-compliance)

You are starting an interactive session. Complete the full SESSION START checklist.

## Agent Self-Identification

Use for ALL signatures this session:
- Author: Claude Code
- Agent/Version: claude-sonnet-4-6
- Software: Claude Code
- Signature format: SIG-YYYYMMDDTHHMMSSZ-claude-[hash4]
- Hash = first 4 chars of MD5(timestamp|claude|Claude Code)

## Context Discovery

Determine the primary project directory. Check for any registered project repo listed in `adapters/*.md` (template at `examples/adapters/example-project.md`).

Read the project's `.agent/task.md` if it exists.
Read `research_hub/portfolio/WORKFLOW_RULES.md` for canonical rules (if it exists for the project).

## SESSION START CHECKLIST

0. **GOAL ALIGNMENT CHECK** (HARD GATE — do this FIRST):
   a. Read `.agent/MISSION_ANCHOR.md` for EACH active project in this session.
   b. Report: "Thesis: {one-line summary}. Primary metric: {metric}. Phase: {current phase}."
   c. Read most recent `.agent/conversation_digests/*.md` (if any exist).
   d. If >5 EXPs since last drift check, run drift checkpoint now:

```python
import sys
sys.path.insert(0, '.')
from gsigmad.governance.compiler.drift_check import check_drift

result = check_drift(project_root=".")
if not result.get("pass", True):
    print("DRIFT_WARNING:", result.get("message", "SCIENCE < 50% in last 5 experiments"))
    print("HALT: Resolve drift before proceeding.")
else:
    print("Drift check: PASS")
```

   e. Report: "Goal alignment: CONFIRMED" or "Goal alignment: DRIFT WARNING — {details}"

0b. **EXP STATUS DISPLAY** (run immediately after goal alignment):
    Run the following Python block and display the rendered EXP table to the user:

```python
import subprocess, sys
result = subprocess.run(
    [sys.executable, "-c",
     "import warnings; warnings.simplefilter('ignore');"
     "from gsigmad.governance.compiler.session_status import get_exp_status_summary, render_exp_table;"
     "r = get_exp_status_summary('.');"
     "print(r.get('warning') or '');"
     "print(render_exp_table(r['exps']))"],
    capture_output=True, text=True, cwd="."
)
print(result.stdout)
if result.returncode != 0:
    print("EXP STATUS: unavailable —", result.stderr.strip())
```

    Display output as-is (the markdown table will render correctly in the session context).
    If `KG_UNAVAILABLE` appears in output, note: "EXP status sourced from local file scan — ArangoDB offline."

1. Check git status for active projects. Report CLEAN/DIRTY.
2. Record current timestamp (UTC).
3. Generate Session ID: YYYYMMDD_HHMMSS_claude (e.g., 20260217_035900_claude).
4. Create/update entry in <workspace>/SESSION_LOG.md with: Session ID, Start timestamp, Agent, Version, Objectives.
5. Create or resume `.agent/task.md` in primary project with today's objectives.
6. Identify next experiment number (check LAB_NOTEBOOK.md for last EXP-###).
7. Identify next prompt number (check prompts/ folder for last PROMPT-###).
8. **PROMPT INTEGRITY CHECK** (REQUIRED):
   a. Read `.agent/next_prompt.txt` and `.agent/next_exp.txt`
   b. Verify the LAST allocated PROMPT file exists: `prompts/PROMPT_{N-1}_*.md` where N = next_prompt value
   c. If missing, STOP and report: "PROMPT INTEGRITY FAILURE: PROMPT-{N-1} file missing"
   d. Verify PROMPT_EXP_MAP.md last entry matches PROMPT-{N-1}
   e. If map is stale, STOP and report: "PROMPT_EXP_MAP stale"
   f. Report: "PROMPT integrity: PASS (last file: PROMPT-{N-1}, map current)"
9. Review pending items from previous sessions (check task.md or daily journal).
10. Update daily journal with session start entry (SIGNATURE REQUIRED).
11. No-overlap check: confirm no other agent is running the same EXP-### you plan to touch.
12. Signature lint precheck: confirm all SIG IDs will use canonical format.

## Non-Negotiables (entire session)

- Do NOT invent data/results/values.
- Science-advancing work = experiment (script + note + results + LAB_NOTEBOOK + journal).
- Infrastructure/visualization work = TASK-### (separate counter, logged in TASK_LOG.md, does NOT consume EXP namespace).
- Run-id-specific outputs (no overwrite-prone fixed filenames).
- Single-writer rule per EXP-###.
- No secrets in commits.
- Change Log entry with SIG ID for every accepted change.
- Re-read MISSION_ANCHOR after every context compaction event.
- Every PROMPT must include Goal Alignment section (thesis link + classification).

## Non-Negotiables (PROMPT governance)

- When allocating a PROMPT number: create the MD + JSON file IMMEDIATELY in `prompts/` before proceeding.
- ChatGPT/external prompts do NOT get PROMPT numbers. Store them where their output will be ingested.
- Update PROMPT_EXP_MAP.md in the SAME session that creates a new PROMPT.
- Do NOT increment next_prompt.txt until the file exists.

## Report Back

- Git status per repo (CLEAN/DIRTY + key files)
- Next available EXP and PROMPT numbers
- **PROMPT integrity status** (PASS/FAIL + details)
- Pending items from previous sessions
- Signature lint status
- Blockers or questions
