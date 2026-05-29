# Non-science software repo - standalone

Matrix version: `v1.2.0b1`

Returned experiment id: `EXP-2.1`

## Commands

- `git init`
- `standalone gsigmad path`
- `gsigmad init .`
- `gsigmad status`
- `gsigmad register --type exploratory --hypothesis <project hypothesis>`
- `gsigmad run --dry-run EXP-2.1`
- `gsigmad audit EXP-2.1 --skip-citations`
- `gsigmad redteam EXP-2.1`

## Expected Artifacts

- `.gsigmad/config.yaml`
- `.gsigmad/LAB_NOTEBOOK.md`
- `.agents/skills/gsigmad/SKILL.md`
- `.claude/skills/gsigmad/SKILL.md`
- `.gsigmad/experiments/EXP-2.1.yaml`
- `adapters/runtime/optional-overwatch.yaml`

## Failure Modes To Watch

- claim framed as scientific evidence instead of engineering evidence
- missing adapters must remain `not_configured`, never PASS
- no live writeback is performed by this example
