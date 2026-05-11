---
name: gsigmad-audit-output
description: "Audit AI-generated output for trust tier compliance. Use when reviewing any AI agent output before promotion to the KG. Checks JSON integrity, sha256 hashes, reproducibility, and PROVISIONAL artifact promotion rules."
allowed-tools:
  - Read
  - Bash
  - Grep
---

# Audit Output

Audit the latest experiment output in the specified project directory.

## Closeout Contract Gate (HARD GATE — runs first)

Source of truth: `docs/EXP_CLOSEOUT_CONTRACT.md` (v1.0, quick task
`260508-ecc`). Before any output / reproducibility audit runs, verify
the EXP note records the four required sections of the closeout
contract:

1. **Artifact linkage** — `experiment_id`, `experiment_note_path`,
   `script_path` (or documented absence reason), `result_artifact_paths`,
   `lab_notebook_anchor`, optionally `result_manifest_hash` and
   `daily_journal_anchor`.
2. **PROMPT provenance** — either `prompt_id` + `prompt_path` (with
   optional `prompt_exp_map_entry`) **or** `no_prompt_reason` + a
   non-empty `no_prompt_justification`. CONFIRMATORY / REPLICATION /
   material AI-assisted experiments MUST record a `prompt_id`.
3. **Notebook replay contract** — exactly one of
   `canonical_replay_notebook | inspection_aid_notebook |
   operator_wrapper_notebook | no_notebook_required |
   human_gated_no_execution | ip_sensitive_no_execution |
   backfill_required`. For each listed notebook, verify the
   per-notebook fields (`independently_runnable`,
   `calls_scripts_via_subprocess`, `imports_experiment_scripts`,
   `loads_frozen_run_artifacts`, `safe_for_ollarma_jupyter_replay`,
   `replay_owner`).
4. **Classification + reason** — one of `experiment_repo |
   operator_console_exempt | product_site_exempt | meta_repo_exempt |
   human_gated | ip_sensitive_no_execution` plus a
   `classification_reason` string.

### Hard halts (block claim promotion / KG writeback)

- **Missing required field** → halt with
  `EXP_CLOSEOUT_CONTRACT_VIOLATION: missing fields [list]` and refuse
  to proceed to the Output Audit. Cite
  `docs/EXP_CLOSEOUT_CONTRACT.md`.
- **`safe_for_ollarma_jupyter_replay: true` declared with a non-canonical
  contract value** → halt with `EXP_CLOSEOUT_CONTRACT_REPLAY_MISMATCH`.
  Only `canonical_replay_notebook` is replay-eligible.
- **CONFIRMATORY / REPLICATION / material AI-assisted EXP without a
  `prompt_id`** → halt with `EXP_CLOSEOUT_CONTRACT_PROMPT_MISSING`. The
  `no_prompt_reason` enum is not allowed for these classifications.
- **Claim promotion attempted with notebook contract
  `operator_wrapper_notebook | backfill_required | needs_deep_audit |
  human_gated_no_execution | ip_sensitive_no_execution`** → halt with
  `EXP_CLOSEOUT_CONTRACT_PROMOTION_BLOCKED`. Only contracts that
  declare a runnable / inspection-class notebook (or
  `no_notebook_required` for analysis-only EXPs) are eligible for
  promotion.

### Soft warnings (do NOT halt; report under "Issues found")

- Classification is `experiment_repo` AND `notebook_replay_contract:
  backfill_required` AND no `prompt_id` → warn `notebook_backfill +
  prompt_missing`; do not halt.
- Classification is `human_gated` AND notebooks present without
  `safe_for_ollarma_jupyter_replay` set → warn `human_gated_replay_
  decision_pending`; the human PI owns the next action.

### Operator console interop note

When this gate halts, an operator console overlay (if any) will
render the project's current readiness state but cannot fix the
inputs. The fix is in the EXP note, not in the console.

## Trust Tier Compliance Note (EC-03)

PROVISIONAL outputs cannot be promoted to the Knowledge Graph without human countersignature. If this audit identifies a PROVISIONAL artifact being promoted without countersignature, halt with:

```
TRUST_TIER_ERROR: PROVISIONAL artifact requires human countersignature before KG promotion.
Artifact: [path]
Required action: Governing-lane agent (Claude Code) or human PI must review and countersign.
Reference: EXTREF quarantine-to-promote policy, CANON-CORE Invariant 9
```

## Output Audit

1. Find the most recent results file(s) in `results/` (by timestamp in filename).
2. Verify required JSON fields:
   - experiment_id, run_id, timestamp_utc, status
   - validation.success (boolean) + failure reason if false
   - outputs with sha256 hashes
3. Cross-check against experiment note in `experiments/EXP_###_*.md`:
   - Do results match what the note claims?
   - Are all output files referenced actually present?
   - Are sha256 hashes correct?
4. Check for invented/fabricated data patterns:
   - Suspiciously round numbers
   - Values that match defaults or placeholders
   - Results that appear without a script execution

## Reproducibility Audit

1. Verify run-id-specific outputs exist (no overwrite-prone fixed filenames).
2. Verify sha256 hashes match actual file contents.
3. Check that the script can be replayed:
   - `python scripts/exp###_name.py` — does it exist and have correct imports?
   - Are all input data files referenced in the script actually present?
4. Check for immutable artifact index — generate one if missing:
   - List all results files for this EXP with: filename, sha256, size, timestamp

## Report Back

- Audit status: PASS/FAIL
- Issues found (list)
- Missing files or broken references
- Reproducibility score (all inputs present / script runnable / hashes valid)
- Immutable artifact index (if generated)
- Trust tier compliance: PROVISIONAL artifacts requiring countersignature (if any)
