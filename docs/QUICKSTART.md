# gsigmad Quickstart

This quickstart uses a disposable local project. It does not require external
databases, private adapters, cloud services, or live writeback targets.

## 1. Install

For this beta candidate, install from source until the matching PyPI upload is
complete:

```bash
git clone https://github.com/biobitworks/gsigmad.git
cd gsigmad
uv sync --all-extras
uv run python -m gsigmad --help
```

After the package is published to PyPI for this version:

```bash
pip install gsigmad
```

## 2. Create a Local Project

```bash
mkdir gsigmad-demo
cd gsigmad-demo
gsigmad init .
gsigmad status
```

The `init` command creates local governance state under `.gsigmad/` and installs
the bundled Agent Skills into `.agents/skills/` and `.claude/skills/`.

## 3. Register an Exploratory Experiment

```bash
EXP_ID=$(gsigmad --json register \
  --type exploratory \
  --hypothesis "H0: the toy feature distribution is unchanged." \
  --title "Toy feature drift check" \
  | python -c 'import json,sys; print(json.load(sys.stdin)["exp_id"])')
echo "$EXP_ID"
```

Record the returned `exp_id`; do not assume a fixed value. Fresh projects in
the 1.2.0b1 surface commonly return `EXP-2.1`, and future numbering may change.

## 4. Run Offline Gates

```bash
gsigmad run --dry-run "$EXP_ID"
gsigmad audit "$EXP_ID" --skip-citations
gsigmad redteam "$EXP_ID"
```

`--dry-run` exercises the local gate path without executing external
integrations. `--skip-citations` keeps the audit fully offline for this toy
project.

## 5. Read the Boundary

`gsigmad` provides deterministic guardrails around experiment governance:
preregistration shape, claim classification surfaces, local provenance, skill
installation, no-writeback defaults, and repeatable gate receipts.

It does not validate scientific truth, prove a biological mechanism, guarantee
statistical adequacy for arbitrary study designs, or publish results. Missing
external adapters must be treated as `not_configured`, never as passing
evidence.

Confirmatory and replication experiments require stricter preregistration than
the exploratory toy path above. At minimum, record H0/H1, statistical test,
alpha, minimum effect size of interest, power assumptions, dataset/source
identity, seed/environment details where applicable, and any permitted
deviation rules before looking at results.
