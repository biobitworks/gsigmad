---
name: gsigmad-create-prompt
description: "Create a PROMPT-### pre-registration artifact for a new experiment. Use when starting a CONFIRMATORY or REPLICATION experiment. Enforces H0/H1/test/alpha/MESI fields and PROMPT_EXP_MAP update in the same session."
allowed-tools: Read, Write, Bash
---

# Create Prompt ($prompt-governance + $change-log-compliance)

Create a PROMPT-### artifact with full governance.

## Pre-Flight

1. Read `.agent/task.md` for current scope.
2. Check prompts/ folder for next available PROMPT-### number.
3. Read `research_hub/portfolio/PROMPT_RULES.md` for canonical structure.

## Prompt Creation Protocol

1. Assign next PROMPT-### number.
2. Create `prompts/PROMPT_###_NAME.md` with:
   - Date, Agent assignment, Status
   - Originating questions (user verbatim + PI interpretation)
   - Goal, Scope, Constraints
   - Expected inputs/outputs with file paths
   - Run-id-specific results requirements
   - No-overlap guards (single-writer enforcement)
   - Verification checklist
   - Post-run reporting requirements
   - Change Log entry with SIGNATURE ID
3. Create matching `prompts/PROMPT_###_NAME.json` with machine-readable metadata:
   - prompt_id, title, date, status, agent
   - inputs[], outputs[], constraints[]
   - change_log[]
4. If the prompt will produce a CONFIRMATORY or REPLICATION experiment: include required pre-registration fields:
   - **H0**: Null hypothesis (exact statistical statement)
   - **H1**: Alternative hypothesis (directional or two-sided)
   - **test**: Statistical test (e.g., Mann-Whitney U, paired t-test, permutation test)
   - **alpha**: Significance threshold (typically 0.05)
   - **MESI**: Minimum Effect Size of Interest (must be justified — not arbitrary)
   - Power analysis: minimum N to detect MESI at alpha with power >= 0.80
5. Link to literature notes if claims/parameters come from publications.

## Post-Creation (REQUIRED — do not skip)

5. **Update PROMPT_EXP_MAP.md** with the new entry (same session, not deferred).
6. **Update `.agent/next_prompt.txt`** to N+1 (only AFTER files exist).
7. If EXP reserved, update `.agent/next_exp.txt` to M+1 (only AFTER files exist).
8. **ChatGPT/external scope check**: If this prompt is directed at ChatGPT or another external agent that will NOT produce a project EXP, it does NOT get a PROMPT number. Instead, create an `EXTREF-###` entry in `external_research/` with prompt.md, output.md, and ingestion_notes.md. See `research_hub/portfolio/WORKFLOW_RULES.md` Section 11 (External Research Registry) for full rules. Update `REGISTRY.md` and `.agent/next_extref.txt`.

## Non-Negotiables

- PROMPT-### naming convention: `PROMPT_###_DESCRIPTIVE_NAME.md` (zero-padded to 3 digits minimum)
- MD + JSON files created in the SAME action — never allocate the number without both files
- PROMPT_EXP_MAP.md updated before session ends — never deferred
- Do NOT increment next_prompt.txt until files exist on disk
- Every PROMPT must include Goal Alignment section (thesis link + classification)

## Report Back

- PROMPT-### created (MD + JSON paths)
- PROMPT_EXP_MAP.md updated (new entry added)
- Counter files updated (next_prompt.txt, next_exp.txt)
- Reserved EXP-### number (if applicable)
- Change Log entry added
