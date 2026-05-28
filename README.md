# gsigmad

`gsigmad` is a local-first science governance CLI and Agent Skills bundle for
research workflows that use AI assistants.

It provides deterministic guardrails around probabilistic model work:

- preregistered experiment prompts
- EXP lifecycle and lab-notebook closure
- claim classification and audit gates
- reproducibility and FAIR checks
- publication/source custody prompts
- no-writeback defaults for risky integrations
- bounded handoff surfaces for local agents and review systems

`gsigmad` does not validate biological, clinical, or scientific claims by
itself. It helps keep hypotheses, evidence, provenance, and promotion decisions
explicit so humans can review them.

## Install

```bash
pip install gsigmad
```

For local development:

```bash
git clone https://github.com/biobitworks/gsigmad.git
cd gsigmad
uv sync --all-extras
uv run pytest
uv run python scripts/release_smoke.py
```

## CLI

```bash
gsigmad --help
gsigmad init .
gsigmad status
gsigmad register EXP-001
gsigmad audit EXP-001
gsigmad redteam EXP-001
```

## Agent Skills

Source skills live in `skills/gsigmad-*/SKILL.md`.

The Python package also bundles the same skills under
`src/gsigmad/skill_bundle/skills/` so `gsigmad init` can install them into:

- `.claude/skills/`
- `.agents/skills/`

High-value entry points:

- `gsigmad` — namespace router and gsd-vs-gsigmad disambiguation
- `gsigmad-quick` — fast triage for an image, dataset, publication, claim, or output
- `gsigmad-create-prompt` — preregistration artifact creation
- `gsigmad-redteam-research-remediate` — red-team, research, and remediation prompt chain
- `gsigmad-audit-claims` — claim and causal-overreach audit
- `gsigmad-audit-output` — reproducibility and output audit
- `gsigmad-import-publications-json` / `gsigmad-ingest-publications-json` — JSON-first publication custody
- `gsigmad-import-web-discussion-json` / `gsigmad-ingest-web-discussion-json` — public web-discussion source-seed custody

## Boundary

`gsigmad` is the public release repo. Internal development happens in a private
upstream repository. This public repo is a sanitized release cut, not a fork;
please use the public issue tracker before opening implementation PRs here.

This public repo intentionally excludes private planning state, private project
adapters, live database configuration, raw experiment data, internal
dashboards, and operator-only receipts.

Integrations with systems such as Watchtower, Ollarma, Antigence, Overwatch,
SeedGraph, ProTHub, or ProAtlas should be treated as optional or local
governance surfaces unless a project supplies its own configured adapter.
Missing adapters are `not_configured`, never PASS.

## Release Smoke

Before tagging a public release, run:

```bash
uv run python scripts/release_smoke.py
```

The smoke creates a disposable local project, exercises the offline CLI
lifecycle, verifies installed skill bundles, checks the npm shim, builds the
sdist and wheel, and writes `release_smoke_receipt.json` in the smoke
workspace.

## License

Apache-2.0. See [LICENSE](LICENSE).
