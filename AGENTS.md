# Agent Guide


## Portfolio commit/push custody policy

Commit/push policy: do not push multi-machine work directly to `main`. Use machine custody lanes: `magicstudio/*` for `magicSTUDIObox` and `magicpro/*` for `magicPRObox`. `main` is reconcile-only. See `/Users/byron/projects/active/portfolio-master-plan/plans/08-two-lane-two-signature-push-reconcile.md`.

Git/rsync does not necessarily capture live ArangoDB or Neo4j state unless DB files or governed exported snapshots are deliberately included. Treat KG snapshot/export custody as a separate explicit step from repo commit/push/rsync.
