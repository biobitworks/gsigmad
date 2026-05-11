---
name: gsigmad-run-experiment
description: "Execute a full EXP workflow with governance gates. Use when running a new scientific experiment. Runs Pre-Flight, PROMPT Validation, Power Analysis, Decision Tree, Temporal Integrity, Red Team, and Data Contract gates."
disable-model-invocation: true
allowed-tools:
  - Read
  - Write
  - Bash
  - Glob
  - Grep
---

# Run Experiment

Execute as a full EXP workflow with governance gates.

## Pre-Flight

1. Identify the primary project.
2. Read `.agent/task.md` for current scope and no-overlap guards.
3. Read `.agent/MISSION_ANCHOR.md` — confirm this experiment serves the thesis.
4. Check LAB_NOTEBOOK.md for next available EXP-### number.
5. Verify no other agent is running the same EXP (single-writer rule).
6. If a PROMPT-### exists for this experiment, read it first.
7. **Hypothesis Pre-Flight** (REQUIRED):
   a. Declare classification: CONFIRMATORY / EXPLORATORY / REPLICATION.
   b. If CONFIRMATORY: verify H₀, H₁, statistical test, rejection threshold (α), and minimum effect size of interest (MESI) are stated in the PROMPT **before** running the script.
   c. If EXPLORATORY: note that findings will require confirmatory follow-up.
   d. Check `experiments/NEGATIVE_RESULTS_REGISTRY.md` for conflicts with previously falsified hypotheses.
   e. If multiple tests planned: declare correction method (Bonferroni/Holm/BH-FDR).

8. **PROMPT Validation Gate** (HARD GATE — blocks execution):
   If a PROMPT-### file exists for this experiment, parse it and verify:
   a. **All classifications**: Confirm `Classification:` line exists with value CONFIRMATORY, EXPLORATORY, or REPLICATION.
   b. **If CONFIRMATORY or REPLICATION**: ALL of the following must be present as explicit text in the PROMPT:
      - `H₀:` or `H0:` or `Null hypothesis:`
      - `H₁:` or `H1:` or `Alternative hypothesis:`
      - `Statistical test:` or `Test:`
      - `α` or `alpha` or `Rejection threshold:` — with a numeric value (e.g., 0.05)
      - `MESI:` or `Minimum effect size:` or `Effect size of interest:`
   c. **If any required field is missing**: **HALT**. Report:
      ```
      PROMPT VALIDATION FAILED — cannot run CONFIRMATORY experiment.
      Missing fields: [list each missing field]
      Fix: Add the missing fields to PROMPT-### before re-running.
      Reference: Overwatch EXPERIMENT_STANDARDS.md Section 2
      ```
   d. **If EXPLORATORY**: Warn if H₀/H₁ are absent (encouraged but not required). Proceed.
   e. **If multiple tests declared**: verify a correction method line exists (`Correction:` or `Multiple comparisons:` with value Bonferroni/Holm/BH-FDR/Šidák). Halt if missing.

## Re-run Detection (WIRE-01)

If the operator specifies a base EXP to re-run (e.g., `base_exp=EXP-042`), execute the following block **before** proceeding to the Power Analysis Gate. If no base EXP is specified, skip this section.

```python
import sys
sys.path.insert(0, '.')
from gsigmad.governance.versioning.exp_diff import next_version_id, diff_exp_records

# Assign a version-suffixed EXP ID for this re-run (per D-01, D-03)
rerun_id = next_version_id(base_exp_id=$ARGUMENTS.base_exp, gsd_root='.')
# e.g., "EXP-042.1" on first re-run, "EXP-042.2" on second

# Build the re-run EXP record with the version-suffixed ID
rerun_exp = {**original_exp_record, "exp_id": rerun_id}

# Diff the two records (per D-02)
diff_result = diff_exp_records(original=original_exp_record, rerun=rerun_exp)

# Append the markdown diff to the lab notebook entry
lab_notebook_diff_block = diff_result["markdown_diff"]
# (Append lab_notebook_diff_block to LAB_NOTEBOOK.md under the re-run EXP entry)

print(f"Re-run detected: {diff_result['summary']}")
print(f"Versioned EXP ID: {rerun_id}")
```

**Re-run Lab Notebook Commit:** After the diff block runs, append `lab_notebook_diff_block` to the LAB_NOTEBOOK.md entry for `rerun_id`. The diff header format is `## EXP-042 → EXP-042.1 Diff` followed by a markdown table of changed fields. If no fields changed, the block contains `_(no changes)_`. Record `rerun_id` in all subsequent gate calls and result artifacts — the base EXP ID (`EXP-042`) is for reference only.

**Non-Negotiables:**
- Do NOT call `next_version_id()` more than once per re-run — each call increments the counter.
- Do NOT set `exp_id` in the EXP pre-registration to the base ID after calling `next_version_id()`.
- `original_exp_record` must be the dict loaded from the existing EXP pre-registration file, not reconstructed from memory.

## Registered Report Deviation Check (CONFIRMATORY with locked report only)

Execute the following block **before** the Power Analysis Gate. If the EXP has no locked registered report, this block exits immediately without side effects.

```python
from gsigmad.governance.reports.registered_report import is_locked, check_immutability, check_deviation

if is_locked(exp_id, gsd_root="."):
    # Step 1: Verify pre-registration file has not been tampered with post-lock
    imm = check_immutability(exp_id, gsd_root=".")
    if not imm["pass"]:
        raise SystemExit(imm["error"])
        # Halts with: REGISTERED_REPORT_IMMUTABLE: EXP-### pre-registration file
        #             '...' has been modified after locking (locked at commit XXXXXXXX).
        #             Use the amendment protocol: create_amendment() in governance/reports/amendment.py.

    # Step 2: Verify EXP record fields match the locked analysis plan
    dev = check_deviation(exp_id, exp_record, gsd_root=".")
    if not dev["pass"]:
        raise SystemExit(dev["error"])
        # Halts with: REGISTERED_REPORT_DEVIATION: hypothesis.{field} differs
        #             — locked={X}, current={Y}
```

If `is_locked()` returns False, both checks are skipped. Exploratory and unlocked CONFIRMATORY experiments continue unaffected.

**What is compared:** `hypothesis.test`, `hypothesis.alpha`, `hypothesis.mesi` in `exp_record` against the values stored in the lock record's `locked_plan` snapshot. Any field mismatch halts execution.

**Amendment path:** If the analysis plan legitimately changed (e.g., revised MESI from pilot data), create an amendment first via `create_amendment()` in `governance/reports/amendment.py`, which updates the lock record's `locked_plan` snapshot. Then re-run — the deviation check will pass.

## Step 8 — Power Analysis Gate (CONFIRMATORY only)

```python
from gsigmad.governance.gates.power_analysis import check_power_analysis_gate
result = check_power_analysis_gate(exp_record)
if not result["pass"]:
    raise SystemExit(result["error"])  # HALT
```

Verify `power_analysis:` block is present in EXP pre-registration with `required_n`, `effect_size_mesi`, `alpha`, `achieved_power`. Block execution if absent or N not achievable.

## Step 9 — Decision Tree Gate (CONFIRMATORY only)

```python
from gsigmad.governance.schemas.decision_tree import validate_decision_tree
result = validate_decision_tree(exp_record["decision_tree"])
if not result["valid"]:
    raise SystemExit(str(result["errors"]))  # HALT
```

Validate `decision_tree:` YAML file against the DecisionTree Pydantic schema. Must include primary_analysis, branches, stopping_rules, sensitivity_analyses.

## Step 10 — Temporal Integrity Gate (CONFIRMATORY only)

```python
from gsigmad.governance.gates.temporal_integrity import check_temporal_integrity
result = check_temporal_integrity(prereg_file=prompt_file, data_file=data_file)
if not result["pass"]:
    raise SystemExit(result["error"])  # HALT — error contains HARKING_PREVENTION_ERROR
```

Verify pre-registration commit timestamp predates data file mtime. Prevents LLM-assisted HARKing (Hypothesizing After Results Known). On failure, `result["error"]` contains the `HARKING_PREVENTION_ERROR` prefix.

## Step 11 — Red Team Gate (CONFIRMATORY only, mandatory)

```python
from gsigmad.governance.gates.red_team import check_red_team_gate
result = check_red_team_gate(
    classification=exp_record["classification"],
    prompt_fields=prompt_fields
)
if not result["pass"]:
    raise SystemExit(result["error"])  # HALT
```

Required `prompt_fields` keys: `risk_tier` (P0/P1/P2), `red_team_status` (must be PASS), `remediation_constraints` (non-empty), `execution_decision` (must be GO). Complete the per-experiment red team checklist before setting `red_team_status: PASS`.

## Step 12 — Data Contract Gate (ALL classifications)

```python
from gsigmad.governance.gates.data_contract import validate_data_contract
result = validate_data_contract(contract=contract_dict, data=data_dict)
if not result["valid"]:
    raise SystemExit(result["halt_message"])  # HALT — halt_message contains DATA CONTRACT VIOLATION
```

Applies to ALL experiment classifications (CONFIRMATORY, EXPLORATORY, REPLICATION). Validates interface boundaries before execution. Record `data_contract: PASS` in EXP gates block on success.

On all gates passing, record in EXP pre-registration:

```yaml
gates:
  power_analysis: PASS
  decision_tree: PASS
  temporal_integrity: PASS
  red_team: PASS        # CONFIRMATORY only
  data_contract: PASS
```

## Experiment Execution Protocol

1. **Script**: Create `scripts/exp###_name.py` implementing the experiment.
2. **Run**: Execute with `python scripts/exp###_name.py`. Capture all output.
3. **Results**: Verify run-id-specific outputs in `results/exp###_<run_id>_*.json`.
   - Results JSON MUST include: experiment_id, run_id, timestamp_utc, status, validation.success
   - If proteins/crosses touched: include entities section
   - sha256 hashes for all output files
4. **Validation Gate**: Check explicit pass/fail criteria. Record outcome.
5. **Experiment Note**: Create/update `experiments/EXP_###_NAME.md` with all required sections:
   - Header, Objective, Methods, Proteins/Entities Touched, Results, Validation/Decision, Conclusions, Reproducibility
   - Include Claim-to-Evidence Map if literature claims used
6. **LAB_NOTEBOOK**: Add entry linking EXP note, script, and results.
7. **Journal**: Update daily journal with experiment summary.
8. **Change Log**: Add SIG ID entry to all modified documents.

## EXP Closeout Contract (HARD GATE — blocks COMPLETE)

Source of truth: `docs/EXP_CLOSEOUT_CONTRACT.md` (v1.0). Every EXP
closeout MUST record the four sections below or declare an explicit
exemption. The portfolio_classifications vocabulary defined in your
operator console (if any) is the science-governance contract here.

Record these fields in the EXP note's frontmatter or a dedicated
`## Closeout Contract` section. Do NOT mark the EXP COMPLETE until
all four sections check.

### Section 1 — Artifact linkage (required)

```yaml
artifact_linkage:
  experiment_id: EXP-###            # or version-suffixed EXP-###.N
  experiment_note_path: experiments/EXP_###_NAME.md
  script_path: scripts/exp###_name.py    # absent only for literature-only / governance-only EXPs
  result_artifact_paths:
    - results/exp###_<run_id>_*.json
  result_manifest_hash: "<sha256>"  # recommended; required at KG / publication promotion
  lab_notebook_anchor: LAB_NOTEBOOK.md#exp-###
  daily_journal_anchor: provenance/journal/YYYY-MM-DD.md#exp-###  # if repo uses daily journals
```

### Section 2 — PROMPT provenance (required — one of)

```yaml
prompt_provenance:
  # EITHER record the preregistration:
  prompt_id: PROMPT-###
  prompt_path: prompts/PROMPT-###.md
  prompt_exp_map_entry: prompts/PROMPT_EXP_MAP.md#exp-###   # if repo uses PROMPT_EXP_MAP

  # OR declare why no PROMPT applies:
  no_prompt_reason: exploratory_no_prompt | legacy_import |
                    governance_task_not_experiment | operator_surface | other
  no_prompt_justification: "<short prose; required when no_prompt_reason is set>"
```

CONFIRMATORY and REPLICATION experiments and material AI-assisted
experiments MUST record a `prompt_id`. Other experiments MAY use
`no_prompt_reason`.

### Section 3 — Notebook replay contract (required — exactly one)

```yaml
notebook_replay_contract: canonical_replay_notebook |
                          inspection_aid_notebook |
                          operator_wrapper_notebook |
                          no_notebook_required |
                          human_gated_no_execution |
                          ip_sensitive_no_execution |
                          backfill_required
notebooks:
  - notebook_path: notebooks/exp###_replay.ipynb
    independently_runnable: true
    calls_scripts_via_subprocess: false
    imports_experiment_scripts: false
    loads_frozen_run_artifacts: true
    safe_for_ollarma_jupyter_replay: true
    replay_owner: ollarma | gsigmad | repo | human | watchtower
```

`safe_for_ollarma_jupyter_replay: true` is allowed ONLY when
`notebook_replay_contract == canonical_replay_notebook`.

### Section 4 — Classification (required)

```yaml
classification: experiment_repo |
                operator_console_exempt | product_site_exempt |
                meta_repo_exempt | human_gated |
                ip_sensitive_no_execution
classification_reason: "<one-line operator-declared reason>"
```

When `classification` is not `experiment_repo`, the closeout MAY use
`no_prompt_reason: operator_surface` and `notebook_replay_contract:
no_notebook_required` (or the matching gated value). The exemption is
a *positive declaration*, not a waiver.

### Closeout gate (HARD)

Before marking the EXP COMPLETE:

1. All four sections present, OR
2. Classification is one of `operator_console_exempt /
   product_site_exempt / meta_repo_exempt`, with matching
   `no_prompt_reason` and `notebook_replay_contract`, AND
3. If `safe_for_ollarma_jupyter_replay: true` — the contract value is
   `canonical_replay_notebook` (cross-check), AND
4. If a result manifest hash is recorded — the file at
   `result_manifest_hash`'s referenced path actually exists.

Halt with:

```
EXP_CLOSEOUT_CONTRACT_VIOLATION: missing fields [list]
Reference: docs/EXP_CLOSEOUT_CONTRACT.md (v1.0)
Fix: complete the sections OR declare an explicit exemption per the
     classification table.
```

9. **Auto-Generate CHAIN_DIGEST** (post-run, every time):
   Rebuild `.agent/CHAIN_DIGEST.md` from current state. This file is machine-generated, never hand-edited. Format (80 lines max):
   - Active Hypothesis Branch (1-2 lines from MISSION_ANCHOR.md)
   - Recent Experiments table (last 5, from LAB_NOTEBOOK.md)
   - Active Blockers
   - Statistical Contract Summary (default α, correction, deterministic runs, sensitivity)
   - Dependency Chain for current EXP
   - Next Decision Point (1-2 lines)

   If LAB_NOTEBOOK is too large, scan only the last 200 lines. Truncate any section that would push over 80 lines.

## Literature Traceability

If publications justify claims, parameters, or model structure:
- Ingest papers into research_hub/literature/
- Map: claim -> figure/table/text evidence -> citation key/PMID/DOI -> local note path
- Claims without traceable support must be labeled HYPOTHESIS
- HYPOTHESIS claims cannot be used for hard parameterization

## PROTHUB Writeback Gate

- Write immutable local results FIRST
- Only after validation PASS may writeback occur
- Writeback must include provenance: exp_id, run_id, script_path, algorithm version, artifact pointers + sha256
- Per-protein success/failure with reason codes required

## Hypothesis Testing

After execution, verify and report:
1. **Classification**: CONFIRMATORY / EXPLORATORY / REPLICATION
2. **If CONFIRMATORY**: Report hypothesis test table:
   - H₀, H₁, test name, test statistic, p-value, effect size (+ measure), decision (REJECT / FAIL TO REJECT)
   - If effect size < MESI: flag as "statistically significant but practically insignificant"
3. **If H₀ not rejected**: Report power. Distinguish true null from underpowered.
4. **If multiple tests**: Report correction method and which tests survive adjustment.
5. **If post-hoc discovery**: Label explicitly. Propose confirmatory follow-up EXP.
6. **Negative results**: Register in `experiments/NEGATIVE_RESULTS_REGISTRY.md` with forward-link.

## Post-Flight Drift Check (REQUIRED — run before Report Back)

```python
from gsigmad.governance.compiler.drift_check import check_drift
result = check_drift(project_root)
if not result["pass"]:
    raise SystemExit(result["error"])  # HALT with DRIFT_WARNING
```

If `result["triggered"]` is True (counter reached 5), display the classification breakdown:
- Science: {result["breakdown"]["SCIENCE"]}/5
- Infrastructure: {result["breakdown"]["INFRASTRUCTURE"]}/5
- Visualization: {result["breakdown"]["VISUALIZATION"]}/5
- Science%: {result["science_pct"]:.0f}%

If drift check halts: re-read `.agent/MISSION_ANCHOR.md` and propose a science-advancing experiment before continuing.

## Report Back

- Run ID and status (PASS/FAIL)
- **Classification**: CONFIRMATORY / EXPLORATORY / REPLICATION
- **Hypothesis outcome** (if CONFIRMATORY): H₀ REJECTED / NOT REJECTED, effect size, p-value
- Key results summary
- Validation outcome
- Files created/modified
- Change Log entries added
- **Drift check status**: counter={N}, triggered={True/False}
- **Re-run**: If this was a re-run, include `rerun_id` and `diff_result["summary"]` in the Report Back output.
