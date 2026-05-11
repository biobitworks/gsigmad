---
name: gsigmad-fair-check
description: "Assess experiment outputs against FAIR criteria (Findable, Accessible, Interoperable, Reusable). Produces a scored checklist with pass/fail per dimension, actionable gaps, and a JSON output file. Use before publication export."
disable-model-invocation: true
allowed-tools:
  - Read
  - Write
  - Bash
  - Glob
  - Grep
---

# FAIR Compliance Check

Assess experiment outputs against the four FAIR data principles and produce a scored checklist.

## 1. Pre-Conditions

Before beginning the FAIR assessment:

1. Identify the target EXP-### from the operator's request (e.g., `EXP-042`).
2. Confirm the experiment directory exists: check for `experiments/EXP_{NNN}_*.json` or `experiments/EXP_{NNN}_*.md` where NNN is the numeric part of the EXP ID.
3. If no EXP record is found, STOP and report: "EXP-### not found. Create the experiment record before running FAIR check."

## 2. Run FAIR Assessment

Run the governance module to evaluate all four FAIR dimensions:

```python
import sys
sys.path.insert(0, '.')
from gsigmad.governance.fair.fair_check import run_fair_check

result = run_fair_check(exp_id="$ARGUMENTS.exp_id", gsd_root=".")

if not result["pass"]:
    print(f"FAIR_CHECK_FAILED: {result['summary']}")
else:
    print(f"FAIR check PASSED: {result['summary']}")
```

What the module does:

- Loads the EXP record and discovers output files (explicit `output_files` list merged with `results/` directory glob).
- Evaluates all 4 FAIR dimensions (11 sub-checks total): Findable (2), Accessible (2), Interoperable (3), Reusable (4).
- Writes the checklist JSON to `experiments/fair/EXP_{NNN}_fair.json`.
- Returns a structured result dict with `exp_id`, `checked_at`, `dimensions`, `total_score`, `pass`, and `summary`.

## 3. Report Back

Display the FAIR assessment results as a markdown summary table:

| Dimension | Sub-Checks | Score | Status |
|-----------|------------|-------|--------|
| Findable | F-ID, F-META | {0 or 1}/1 | PASS/FAIL |
| Accessible | A-PROTOCOL, A-LICENSE | {0 or 1}/1 | PASS/FAIL |
| Interoperable | I-FORMAT, I-VOCAB, I-PROV | {0 or 1}/1 | PASS/FAIL |
| Reusable | R-LICENSE, R-METHOD, R-VARDEF, R-UNITS | {0 or 1}/1 | PASS/FAIL |
| **Total** | **11 sub-checks** | **{total_score}/4** | **{PASS/FAIL}** |

**Action Items** (one checkbox per failing sub-check):

- [ ] {Sub-check ID}: {detail from result explaining what is missing and how to fix it}
- [ ] ...

Report:
- JSON path: `experiments/fair/EXP_{NNN}_fair.json`
- Total score: `{total_score}/4`
- Overall: `{PASS/FAIL}`
- Action items: `{count of failing sub-checks}`

## 4. Post-Conditions

After the FAIR assessment completes, verify:

1. `experiments/fair/EXP_{NNN}_fair.json` exists on disk.
2. The JSON file contains valid JSON with keys: `exp_id`, `checked_at`, `dimensions`, `total_score`, `pass`, `summary`.
3. If the FAIR check FAILED, the action items list provides specific, actionable steps the operator can take.

The FAIR check is an assessment tool, NOT an execution gate. A failing FAIR check does not block experiment execution or other governance gates. It identifies gaps for the operator to address before publication export.

## Sub-Check Reference

| ID | Dimension | What It Checks | FAIL Condition |
|----|-----------|----------------|----------------|
| F-ID | Findable | Persistent identifier (DOI or PMID) in EXP record or `.agent/identifiers.json` | No DOI or PMID found in any source |
| F-META | Findable | Searchable metadata fields: title, description, keywords, creator | Any of the four metadata fields is missing or empty |
| A-PROTOCOL | Accessible | Output files listed in EXP record exist on disk and are retrievable | One or more declared output files are missing from disk |
| A-LICENSE | Accessible | License declared in EXP record `license` field or LICENSE/LICENSE.md file | No license found in any source |
| I-FORMAT | Interoperable | Output files use community standard formats (.json, .csv with headers, .prov.json) | Any output file uses a non-standard format (e.g., .xlsx, .dat) |
| I-VOCAB | Interoperable | JSON output files contain JSON-LD `@context` or EXP record has `vocabulary` field | No linked vocabulary reference in JSON outputs or EXP record |
| I-PROV | Interoperable | `.prov.json` file exists with W3C PROV keys (entity, activity, wasGeneratedBy) | No .prov.json file found, or file is missing required W3C keys |
| R-LICENSE | Reusable | Explicit license for reuse (same sources as A-LICENSE) | No license found in any source |
| R-METHOD | Reusable | Non-empty `methodology` field in EXP record | Methodology field is absent or empty |
| R-VARDEF | Reusable | Each variable in `variables` array has a `definition` field | Any variable is missing its definition |
| R-UNITS | Reusable | Each variable in `variables` array has a `unit` field | Any variable is missing its unit |

## Anti-Patterns

**Do NOT call `verify_doi()` or `verify_pmid()` during the FAIR check.** The FAIR findability check verifies identifier PRESENCE (DOI/PMID string exists), not online verification against CrossRef or PubMed. Network calls are out of scope for FAIR assessment.

**Do NOT use the FAIR check as a run-experiment gate.** The FAIR check is an assessment tool for publication readiness, not an execution gate. It does not block experiment runs, registered report locking, or any other governance operation. Use it before export, not before execution.

**Do NOT modify the EXP record or any experiment files.** The FAIR check is read-only. It reads the EXP record, output files, and license files but never modifies them. The only write is to `experiments/fair/` directory (the FAIR checklist JSON output).
