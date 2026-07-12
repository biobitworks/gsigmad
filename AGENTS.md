# Agent Guide


## Portfolio commit/push custody policy

Commit/push policy: do not push multi-machine work directly to `main`. Use per-machine custody lanes (one branch namespace per contributing machine) and keep `main` reconcile-only, so no single machine's working state lands on `main` without a reconcile step. Follow your project's internal ops runbook for the exact lane scheme.

Git/rsync does not necessarily capture live ArangoDB or Neo4j state unless DB files or governed exported snapshots are deliberately included. Treat KG snapshot/export custody as a separate explicit step from repo commit/push/rsync.


<!-- scratchpad-custody-rule v1 -->
## Scratchpad is inside the chain of custody

`scratchpad/` is inside the chain of custody — not an ephemeral or exempt zone. Every scratchpad file is a custody atom: record it in `.planning/scratchpad_ledger.jsonl` (`sha256` + origin) and either persist it (commit, or promote to `.planning/` or a named non-repo home) or discard it with a logged reason. A scratchpad file that is neither git-tracked nor ledgered is **UNSAVED** and raises an Antigence Sentinel alert (`scratchpad_custody` event → HIGH ticket → Watchtower review lane). Truly volatile temp work belongs in the harness-provided session scratchpad directory (the out-of-repo temp path the harness assigns), never an in-repo `scratchpad/`. Nothing in scratchpad goes missing without a receipt.
