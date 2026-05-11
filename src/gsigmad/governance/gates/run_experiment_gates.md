# run-experiment Pre-Flight Gate Chain Reference
> Phase 1 additions — Governance Foundation
> These gates insert into `~/.claude/commands/run-experiment.md` (or the equivalent SKILL.md)
> in the Pre-Flight section, after step 7 (PROMPT Validation Gate).
> All gates apply to CONFIRMATORY experiments only unless noted otherwise.

---

## Overview of Gate Order

The complete pre-flight gate chain for `run-experiment`. Steps 1–7 are **existing — do not modify**. Steps 8–12 are **NEW — Phase 1**.

```
1. Read .agent/task.md                                         (existing — do not modify)
2. Read .agent/MISSION_ANCHOR.md                               (existing — do not modify)
3. Check LAB_NOTEBOOK.md for next EXP-###                      (existing — do not modify)
4. Single-writer check                                         (existing — do not modify)
5. Read PROMPT-###                                             (existing — do not modify)
6. Hypothesis Pre-Flight — declare classification              (existing — do not modify)
7. PROMPT Validation Gate — check H0/H1/test/alpha/MESI        (existing — do not modify)
   [NEW gates for CONFIRMATORY only, sequential:]
8.  Power Analysis Gate — check power_analysis block present + N achievable   (NEW — Phase 1)
9.  Decision Tree Gate — validate decision_tree YAML schema                    (NEW — Phase 1)
10. Temporal Integrity Gate — check commit_ts < data_mtime                    (NEW — Phase 1)
11. Red Team Gate — check red_team_status = PASS                              (NEW — Phase 1, mandatory)
12. Data Contract Gate — run data-contract validation                          (NEW — Phase 1, ALL classifications)
```

---

## Gate 8 — Power Analysis Gate (CONFIRMATORY only)

**Insertion point:** Immediately after step 7 (PROMPT Validation Gate), before experiment execution.

**Python import:**
```python
from gsigmad.governance.gates.power_analysis import check_power_analysis_gate
```

**Call pattern:**
```python
result = check_power_analysis_gate(exp_record)
if not result["pass"]:
    # HALT — display result["error"]
    raise SystemExit(f"POWER ANALYSIS GATE FAILED:\n{result['error']}")
```

**Error handling:** If `not result["pass"]`, display `result["error"]` and halt. Do not proceed to experiment execution.

**Required EXP record block** — the `power_analysis:` block must be present in the EXP pre-registration YAML before the gate can pass:

```yaml
power_analysis:
  tier: formula          # formula | simulation | plugin
  test_type: ttest_ind   # e.g. ttest_ind, ttest_1samp, anova, chi2, proportion_ztest
  required_n: 100        # minimum sample size per group
  effect_size_mesi: 0.4  # Cohen's d (or equivalent) — minimum effect size of interest
  alpha: 0.05            # Type I error threshold
  achieved_power: 0.80   # Target power (1 - beta)
  computed_at: "2026-03-31T10:00:00Z"
  tool_version: "statsmodels-0.14.5"
```

**Gate status on pass:** Record `power_analysis: PASS` in the `gates:` block of the EXP pre-registration.

---

## Gate 9 — Decision Tree Gate (CONFIRMATORY only)

**Insertion point:** Immediately after Gate 8 (Power Analysis Gate).

**Python import:**
```python
from gsigmad.governance.schemas.decision_tree import validate_decision_tree
```

**Call pattern:**
```python
result = validate_decision_tree(exp_record["decision_tree"])
if not result["valid"]:
    errors = result["errors"]
    raise SystemExit(f"DECISION TREE GATE FAILED:\n{errors}")
```

**Error handling:** If `not result["valid"]`, format `result["errors"]` (list of Pydantic validation errors) and halt.

**Required EXP pre-registration field:**
```yaml
decision_tree: experiments/EXP-042/decision_tree.yaml
```

The `decision_tree` field must point to a YAML file that validates against the `DecisionTree` Pydantic v2 schema in `governance/schemas/decision_tree.py`. The schema requires:
- `exp_id` — experiment identifier matching the EXP pre-registration
- `primary_analysis` — `Analysis` object with `test` and optional `correction`
- `branches` — list of `Branch` objects with `condition` and `action`
- `stopping_rules` — list of stopping rule strings
- `sensitivity_analyses` — list of `SensitivityAnalysis` objects

**Gate status on pass:** Record `decision_tree: PASS` in the `gates:` block.

---

## Gate 10 — Temporal Integrity Gate (CONFIRMATORY only)

**Insertion point:** Immediately after Gate 9 (Decision Tree Gate).

**Python import:**
```python
from gsigmad.governance.gates.temporal_integrity import check_temporal_integrity
```

**Call pattern:**
```python
result = check_temporal_integrity(prereg_file=prompt_file, data_file=data_file)
if not result["pass"]:
    raise SystemExit(f"TEMPORAL INTEGRITY GATE FAILED:\n{result['error']}")
```

**Arguments:**
- `prereg_file` — path to the PROMPT-### pre-registration file (must be git-tracked)
- `data_file` — path to the primary data file that will be loaded for analysis

**Error handling:** If `not result["pass"]`, display `result["error"]` and halt. The error message contains `HARKING_PREVENTION_ERROR` with an explicit path forward.

**Example error message format:**
```
HARKING_PREVENTION_ERROR: Pre-registration commit (2026-03-31T10:05:00+00:00)
postdates or equals data file mtime (2026-03-31T09:55:00+00:00) by 600.0 seconds.
This experiment cannot be classified CONFIRMATORY.
Options:
(1) Reclassify as EXPLORATORY and spawn a new CONFIRMATORY EXP with independent data.
(2) Re-register the hypothesis on a new independent dataset and re-commit before loading data.
Reference: EXPERIMENT_STANDARDS.md §2, CANON-CORE Invariant 5.
```

**Edge cases:**
- Data file does not yet exist (pre-registering before data collection): gate passes by definition.
- Pre-registration file has no git commit history (uncommitted): gate fails — commit before running.
- Public/external data files (identified by URL or external database ID) are exempt from the mtime check.

**Gate status on pass:** Record `temporal_integrity: PASS` in the `gates:` block.

---

## Gate 11 — Red Team Gate (CONFIRMATORY only, mandatory)

**Insertion point:** Immediately after Gate 10 (Temporal Integrity Gate). This gate is mandatory — no bypass mechanism exists for CONFIRMATORY experiments.

**Python import:**
```python
from gsigmad.governance.gates.red_team import check_red_team_gate
```

**Call pattern:**
```python
result = check_red_team_gate(
    classification=exp_record["classification"],
    prompt_fields=prompt_fields
)
if not result["pass"]:
    raise SystemExit(f"RED TEAM GATE FAILED:\n{result['error']}")
```

**Required `prompt_fields` keys** (for CONFIRMATORY experiments):

| Key | Required Value | Description |
|-----|----------------|-------------|
| `risk_tier` | `P0`, `P1`, or `P2` | Experiment risk tier (P0 = highest) |
| `red_team_status` | `PASS` | Must be `PASS` — not `PENDING`, `FAIL`, or absent |
| `remediation_constraints` | Non-empty list | At least one constraint documented |
| `execution_decision` | `GO` | Must be `GO` — not `BLOCKED` or absent |

**Per-experiment red team checklist** — complete all items before setting `red_team_status: PASS`:

```markdown
## Pre-Execution Red Team (CONFIRMATORY EXP-###)

- [ ] H0 and H1 are distinct and falsifiable (not trivially true/false)
- [ ] Statistical test selection is justified for the data type
- [ ] MESI is scientifically motivated (not set to guarantee significance)
- [ ] Sample size justification does not assume the result in advance
- [ ] Pre-registration commit predates data file mtime (temporal integrity)
- [ ] Power analysis output is present and N is achievable
- [ ] Decision tree covers the primary analysis AND key sensitivity scenarios
- [ ] No circular evidence: hypothesis source is independent of data used to test it

risk_tier: P0 | P1 | P2
red_team_status: PASS | FAIL
remediation_constraints:
  - [Constraint 1]
execution_decision: GO | BLOCKED
```

**Error handling:** If `not result["pass"]`, display `result["error"]` and halt.

**Gate status on pass:** Record `red_team: PASS` in the `gates:` block.

---

## Gate 12 — Data Contract Gate (ALL classifications)

**Insertion point:** Immediately after Gate 11 (Red Team Gate). **Note: This gate applies to ALL experiment classifications** (CONFIRMATORY, EXPLORATORY, and REPLICATION) — not CONFIRMATORY only.

**Python import:**
```python
from gsigmad.governance.gates.data_contract import validate_data_contract
```

**Call pattern:**
```python
result = validate_data_contract(contract=contract_dict, data=data_dict)
if not result["valid"]:
    raise SystemExit(f"DATA CONTRACT GATE FAILED:\n{result['halt_message']}")
```

**Arguments:**
- `contract` — dict (loaded from the experiment's data contract YAML or built programmatically) matching the `DataContract` Pydantic model
- `data` — dict of actual data values to validate against the contract

**Error handling:** If `not result["valid"]`, display `result["halt_message"]` and halt. The halt message follows the format:
```
DATA CONTRACT VIOLATION: [interface name] field '[field_name]' [violation description].
Fix: Update the data contract schema in [file] before re-running.
Reference: CANON-CORE Invariant 1 (no fabricated data, all data traced to source)
```

**Gate status on pass:** Record `DATA_CONTRACT_GATE: PASS` — specifically record `data_contract: PASS` in the `gates:` block of the EXP pre-registration.

---

## Gate Status Recording

After all gates pass, record the following `gates:` YAML block in the EXP pre-registration file:

```yaml
gates:
  power_analysis: PASS
  decision_tree: PASS
  temporal_integrity: PASS
  red_team: PASS        # CONFIRMATORY only
  data_contract: PASS
```

This block must appear in the EXP pre-registration **before execution begins**. Update it gate-by-gate as each one passes — do not write it all at once at the end.

---

## Complete Example EXP Pre-Registration YAML

The following is a complete example EXP pre-registration with all Phase 1 gate fields:

```yaml
---
# EXP pre-registration — author in YAML, stored as JSON in KG
exp_id: "EXP-042"
classification: CONFIRMATORY
created_at: "2026-03-31T10:00:00Z"
author: "claude-sonnet-4-6"
sig: "SIG-20260331T100000Z-claude-a3f1"

hypothesis:
  h0: "Fragment-context disorder equals protein-context disorder (delta = 0)"
  h1: "Fragment-context disorder differs from protein-context (|delta| > 0.05)"
  test: "ttest_ind"
  alpha: 0.05
  mesi: 0.4  # Cohen's d — smallest effect that changes a therapeutic decision
  sample_justification: "Derived from power analysis: at MESI=0.4, power=0.80 requires N=100/group"

power_analysis:
  tier: formula
  test_type: ttest_ind
  required_n: 100
  effect_size_mesi: 0.4
  alpha: 0.05
  achieved_power: 0.80
  computed_at: "2026-03-31T10:00:00Z"
  tool_version: "statsmodels-0.14.5"

decision_tree: experiments/EXP-042/decision_tree.yaml

gates:
  power_analysis: PASS
  decision_tree: PASS
  temporal_integrity: PASS
  red_team: PASS        # CONFIRMATORY only
  data_contract: PASS
```

---

## Quick Reference: All Gate Import Paths

| Gate | Module | Function | Applies To |
|------|--------|----------|------------|
| Gate 8: Power Analysis | `governance.gates.power_analysis` | `check_power_analysis_gate` | CONFIRMATORY |
| Gate 9: Decision Tree | `governance.schemas.decision_tree` | `validate_decision_tree` | CONFIRMATORY |
| Gate 10: Temporal Integrity | `governance.gates.temporal_integrity` | `check_temporal_integrity` | CONFIRMATORY |
| Gate 11: Red Team | `governance.gates.red_team` | `check_red_team_gate` | CONFIRMATORY (mandatory) |
| Gate 12: Data Contract | `governance.gates.data_contract` | `validate_data_contract` | ALL classifications |

All gate scripts live in `governance/gates/` (except `decision_tree` in `governance/schemas/`). Import them directly in pre-flight scripts or via the gate chain orchestrator.
