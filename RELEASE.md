# Public Release Checklist

Release target: `gsigmad` public GitHub repository.

## Included

- `src/gsigmad/` Python package
- `skills/gsigmad*/SKILL.md` source skills
- packaged skill bundle under `src/gsigmad/skill_bundle/skills/`
- public docs, specs, tests, npm shim, Homebrew formula
- generic adapter examples only

## Excluded

- private planning state
- private project adapters
- experiment run records
- raw data
- local receipts
- dashboards and operator-only exports
- live database, KG, or writeback configuration
- caches, virtualenvs, generated artifacts, and worktrees

## Release Gate

Before pushing publicly:

- tests pass
- secret scan has no confirmed credential leaks
- private-surface scan has no internal-only directories
- package metadata includes license, citation, security, and contribution files
- GitHub remote is explicitly configured for the intended public repo
