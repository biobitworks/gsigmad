# Lab Notebook - gsigmad

<!-- portfolio-sidecar-rule-lapse-20260531 -->

## 2026-05-31 - Portfolio JSON/JSONL sidecar lapse repair

- Operator instruction: all project prompts and agent handoffs should emit machine-readable JSON/JSONL sidecars for source intake, task state, decisions, receipts, reviews, and deferred writeback candidates as work proceeds.
- Lapse documented: prior sessions in this repo did not consistently create repo-local JSON/JSONL sidecars for future writeback candidate data.
- Repair performed: created or verified `docs/source_intake.manifest.jsonl`, `docs/deferred_writeback_candidates.jsonl`, `.planning/task_state.jsonl`, `.planning/decision_log.jsonl`, and `.planning/receipts.jsonl`.
- Boundary: these sidecars are local planning/custody records only. No live writeback, import, commit, push, external database mutation, claim promotion, or canonical truth promotion was performed.
- Branch at repair: `main`.
- Rule hash anchor: `c8222b5d926bbd46dabb7989ca10cac963d0e9e023c28ccc693cbc70842b1e22`.

<!-- portfolio-file-sidecar-tests-20260531 -->

## 2026-05-31 - File-level sidecar test coverage

- Operator instruction: each project should have file-level sidecars and a task list so future writeback/readiness checks can pass like writeback tests.
- Repair performed: generated or verified `.planning/file_sidecar_inventory.jsonl` and `.planning/sidecar_test_tasks.jsonl` for this repo.
- Branch at repair: `main`.
- Boundary: local planning/custody data only. No live writeback, import, commit, push, external database mutation, claim promotion, or canonical truth promotion was performed.
- Future test command: `/Users/byron/projects/bin/portfolio_sidecar_file_tests.py --check`.
