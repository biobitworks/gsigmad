# EXP Closeout Contract

Canonical science-governance contract for closing a Getting Science
Done (gsigmad) experiment. Every EXP closeout must explicitly account
for the four sections below. The 10 portfolio classifications recognised
by an operator console overlay (if any) are codified here as the
**science-governance side** of that contract — the console observes,
gsigmad governs.

This document is read by:

- `skills/gsigmad-run-experiment/SKILL.md` — at closeout time.
- `skills/gsigmad-audit-output/SKILL.md` — at audit-gate time.
- Downstream project skills that wrap `gsigmad-run-experiment`.

## Section 1 — EXP artifact linkage (required)

Every EXP closeout must record:

| Field | Required? | Notes |
|---|---|---|
| `experiment_id` | yes | `EXP-###` (or version-suffixed `EXP-###.N` per re-run protocol) |
| `experiment_note_path` | yes | `experiments/EXP_###_NAME.md` (or per-repo convention) |
| `script_path` | conditional | Required if any script was executed; absent only when the EXP is a literature-only or governance-only artifact |
| `result_artifact_paths` | conditional | One or more `results/exp###_<run_id>_*.json` paths, run-id stamped; required when `script_path` is recorded |
| `result_manifest_hash` | recommended | `sha256` of an immutable artifact index when produced; required when promoting to KG / external publication |
| `lab_notebook_anchor` | yes | Path + heading anchor to the LAB_NOTEBOOK entry that links the EXP note + script + results |
| `daily_journal_anchor` | conditional | Required when the repo uses daily journals (`provenance/`, `journal/`, etc.) |

Read by: `gsigmad-run-experiment` §5–§6, `gsigmad-audit-output` Output
Audit.

## Section 2 — PROMPT provenance (required)

Every EXP closeout must record one of:

- **`prompt_id` + `prompt_path`** — the PROMPT-### preregistration
  artifact that governs this experiment. Required for:
  - any CONFIRMATORY experiment;
  - any REPLICATION experiment;
  - any material AI-assisted experiment (where an LLM authored part
    of the analysis plan, code, or interpretation).
- **`prompt_exp_map_entry`** — repo-relative path + line anchor when
  the project uses `PROMPT_EXP_MAP.md` (e.g., Vitaology).
- **`no_prompt_reason`** — one of the following enum values, with a
  short justification string:

| `no_prompt_reason` | When to use |
|---|---|
| `exploratory_no_prompt` | EXPLORATORY experiment with no preregistered PROMPT (still must declare classification per `gsigmad-run-experiment` Pre-Flight) |
| `legacy_import` | Pre-PROMPT-era EXP imported into the gsigmad lifecycle; record provenance pointer to the imported artifact |
| `governance_task_not_experiment` | The "EXP" is a governance-surface index (e.g., `EXP_000_GOVERNANCE_SURFACE.md`), not a scientific experiment |
| `operator_surface` | Repo is an operator console / product site / meta repo and does not carry an experiment surface (Watchtower-aligned classification) |
| `other` | Any other reason — must be documented inline (no blank justification) |

Read by: `gsigmad-create-prompt` (the artifact authoring side) +
`gsigmad-audit-output` (the audit gate that consumes it).

## Section 3 — Notebook replay contract (required)

Every EXP closeout must declare exactly one **notebook replay
contract** value:

| Value | Meaning | Owner for next action |
|---|---|---|
| `canonical_replay_notebook` | A notebook that *is* the replay surface. Independently runnable. Loads frozen run artifacts. Safe for Ollarma replay. | `ollarma` (when ready) |
| `inspection_aid_notebook` | A notebook that inspects / visualizes results. Not the replay surface. May call frozen artifacts read-only. | `repo` |
| `operator_wrapper_notebook` | A notebook that calls scripts via `subprocess` / `!python` / `%run`. NOT a replay surface. Needs reclassification or backfill. | `gsigmad` |
| `no_notebook_required` | EXP is script-only or analysis-only; no notebook is part of the closeout contract. | `repo` |
| `human_gated_no_execution` | Wrappers exist; replay decision deferred to the human PI (matches Watchtower `human_gated`). | `human` |
| `ip_sensitive_no_execution` | IP-sensitive surface; notebook content must never be opened (matches Watchtower `ip_sensitive_no_execution`). | `human` |
| `backfill_required` | EXP has experiments but no notebooks; gsigmad must produce the canonical replay notebook before COMPLETE. | `gsigmad` |

For each notebook listed in the contract, record:

- `notebook_path` (repo-relative; absolute path is exposed by
  Watchtower's `notebook_replay` payload, not required here);
- `independently_runnable: true | false` — does it run without an
  external orchestrator?
- `calls_scripts_via_subprocess: true | false` — `subprocess.run` /
  `subprocess.Popen` / `!python` / `!bash` / `%run`;
- `imports_experiment_scripts: true | false` — `from scripts.exp###`
  or `import experiments.…`;
- `loads_frozen_run_artifacts: true | false` — reads
  `results/exp###_<run_id>_*.json` or equivalent without recomputing;
- `safe_for_ollarma_jupyter_replay: true | false` — when true, the
  contract value must be `canonical_replay_notebook`;
- `replay_owner` — one of `gsigmad`, `ollarma`, `repo`, `human`,
  `watchtower` (matches the `recommended_owner` field returned by
  Watchtower's `notebook_replay`).

Read by: `gsigmad-run-experiment` §"EXP Closeout Contract" + Watchtower
`watchtower/notebook_replay.py` (for surface rendering only — Watchtower
never sets the contract).

## Section 4 — Classification + exemption reason (required)

Every EXP closeout must declare a **classification** drawn from the
governance contract below. The first six are operator-declared at the
repo / EXP level; the last four are derived by Watchtower's
`notebook_replay` machinery from the artifacts on disk.

### Input classifications (operator-declared)

| Classification | Use it for | Expects experiments? |
|---|---|---|
| `experiment_repo` | Default. Repos with `experiments/` + canonical EXP records (demo-bio, demo-math, demo-pipeline, …) | yes |
| `operator_console_exempt` | Operator surfaces with no experiment by design (Watchtower) | no |
| `product_site_exempt` | Public product / website surfaces (bioviz-tech, game-playcast) | no |
| `meta_repo_exempt` | Meta / portfolio / governance repos (metarepo) | no |
| `human_gated` | Control planes whose wrappers need human reclassification (Overwatch) | yes |
| `ip_sensitive_no_execution` | Patent / IP-sensitive repos where notebook content must never be opened (shadow-seeds) | yes |

When the classification is *not* `experiment_repo`, the closeout
contract MAY declare `no_prompt_reason: operator_surface` (or
equivalent) and MAY declare `notebook_replay_contract:
no_notebook_required` (or `human_gated_no_execution`,
`ip_sensitive_no_execution`).

### Derived classifications (produced by `notebook_replay`)

| Classification | Meaning |
|---|---|
| `missing_experiment_surface` | Should-have-experiments repo that does not carry one |
| `notebook_backfill_required` | Has experiments but no replayable notebooks |
| `needs_deep_audit` | Replay deep-audit signals trip; chain suppressed |
| `ready_for_ollarma_replay` | `replay_readiness == "ready"`; chain emitted |

Derived classifications are **observed**, not declared. Watchtower
emits them; gsigmad does not record them in the EXP closeout itself.

## Section 5 — Closeout gate behavior

The contract is enforced by these gates:

1. **EXP cannot be marked COMPLETE** unless Sections 1–4 are recorded
   *or* an explicit exemption is declared via classification +
   `no_prompt_reason` + `notebook_replay_contract` (e.g.,
   `operator_console_exempt` + `operator_surface` +
   `no_notebook_required`).
2. **Claim promotion is blocked** when a notebook / replay artifact
   is missing and no exemption exists. `gsigmad-audit-output` must
   halt with an explicit error referencing this contract.
3. **Ollarma replay is blocked** when the notebook replay contract
   value is `operator_wrapper_notebook` / `backfill_required` /
   `human_gated_no_execution` / `ip_sensitive_no_execution` /
   `needs_deep_audit`. Only `canonical_replay_notebook` (with
   `safe_for_ollarma_jupyter_replay: true`) is replay-eligible.
4. **Operator / product / meta repos do not require notebooks**
   unless they explicitly declare themselves
   `experiment_repo`. The exemption is a positive declaration, not a
   waiver — the repo's classification record is what makes the
   notebook expectation go away.

## Section 6 — Operator console interop

An operator console (if integrated) renders the *observed* state of
these classifications in its project-review surface. The console
never writes the contract; it only displays it. The mapping is
one-to-one:

| Operator console field | gsigmad contract source |
|---|---|
| `classification` | Section 4 input classification |
| `classification_reason` | Section 4 declared reason text |
| `notebook_replay.replay_readiness` | Derived from Section 3 contract value + on-disk state |
| `notebook_replay.recommended_owner` | Section 3 `replay_owner` |
| `dashboard.kind` (`control_plane_script`) | Console-side detection only; not a gsigmad contract field |

When the contract changes (e.g., a new `notebook_replay_contract`
enum value), update both this document AND the corresponding console
classification module so the operator console keeps rendering
accurately.

## Section 7 — How to add a contract field

1. Edit this document. Increment the contract version (next section).
2. Update `skills/gsigmad-run-experiment/SKILL.md` §"EXP Closeout
   Contract" to surface the new field at closeout time.
3. Update `skills/gsigmad-audit-output/SKILL.md` "Closeout Contract
   Gate" if the new field is gate-enforceable.
4. If the field maps to an operator console rendered surface, also
   update that console's portfolio classification module + reference
   docs.
5. Record the change in the project's append-only LAB_NOTEBOOK with a
   signed entry. The contract is a governance contract; new fields go
   through this doc + a notebook receipt, not silent edits.

## Boundaries

- This document is a **governance contract**, not executable code.
  Pydantic schema validation of these fields is a follow-up
  `260508-eccf-*` lane.
- gsigmad governs; the operator console (if any) observes; the
  bounded local execution lane (if any) executes only when
  `safe_for_ollarma_jupyter_replay: true`.
- No KG / SeedGraph / Overwatch / ProTHub / ArangoDB writeback.
- No notebook execution from gsigmad itself. Replay is owned by
  Ollarma; the contract gates *whether* a replay may run, not how.

## Contract version

`v1.0` — 2026-05-08.

## Cross-references

- `skills/gsigmad-run-experiment/SKILL.md` §"EXP Closeout Contract"
- `skills/gsigmad-audit-output/SKILL.md` "Closeout Contract Gate"
- `skills/gsigmad-create-prompt/SKILL.md` (PROMPT provenance side;
  `no_prompt_reason` enum lives in `gsigmad-create-prompt`)
- Operator console (if integrated): the console's portfolio
  classification module and its observed-state machinery for
  notebook replay.
