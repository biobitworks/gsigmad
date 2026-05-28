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

For local development and release verification:

```bash
uv sync --all-extras
uv run pytest
uv run python scripts/release_smoke.py
uv run python scripts/huggingface_artifact_smoke.py
uv run python scripts/homebrew_artifact_smoke.py
uv run python scripts/clean_install_smoke.py
uv run python scripts/npm_package_smoke.py
```

For a first local run, see [docs/QUICKSTART.md](docs/QUICKSTART.md).

Public positioning docs:

- [Scope and ethics](docs/SCOPE_AND_ETHICS.md)
- [Comparison and positioning](docs/COMPARISON.md)
- [Capability matrix](docs/CAPABILITY_MATRIX.md)
- [Release and DOI process](docs/RELEASE_DOI_PROCESS.md)
- [Public benchmark plan](docs/PUBLIC_BENCHMARK_PLAN.md)

## CLI

```bash
gsigmad --help
gsigmad init .
gsigmad status
gsigmad register --type exploratory --hypothesis "H0: toy data are unchanged."
gsigmad run --dry-run EXP-1.1
gsigmad audit EXP-1.1 --skip-citations
gsigmad redteam EXP-1.1
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

## Public Demo Artifacts

Optional Hugging Face templates live under
[examples/huggingface/](examples/huggingface/):

- a dataset-card template with synthetic deterministic gate-trace JSONL rows
- a static Space template for showing the same gate-boundary summary

Public benchmark seed artifacts live under
[examples/benchmark/](examples/benchmark/):

- synthetic adversarial workflow fixtures across the failure taxonomy
- a claim-boundary corpus separating creative inference from deterministic gates
- a public failure taxonomy for missing gates, runner limits, and no-writeback
  boundaries

These examples are public-safe release artifacts, not a full benchmark and not
evidence that gsigmad validates scientific truth.

## Citation and DOI

Citation metadata lives in [CITATION.cff](CITATION.cff).

**DOI: pending.** The first public DOI will be minted by Zenodo from an
archived GitHub release after the public tag. Until Zenodo issues that DOI,
`CITATION.cff` intentionally has no DOI field; please do not cite a
placeholder. Once the DOI is issued, this README and `CITATION.cff` will be
updated in the next docs commit. The DOI cites the archived software release,
not a peer-reviewed paper or validated benchmark.

## Release Smoke

Before tagging a public release, run:

```bash
uv run python scripts/release_smoke.py
```

The smoke creates a disposable local project, exercises the offline CLI
lifecycle, verifies installed skill bundles, checks the npm shim, validates the
Hugging Face dataset-card and static Space artifacts, builds the sdist and
wheel, and writes `release_smoke_receipt.json` in the smoke workspace.

For a Hugging Face artifact dry run, run:

```bash
uv run python scripts/huggingface_artifact_smoke.py
```

That smoke validates the dataset-card YAML, JSONL rows, benchmark seed corpus,
claim-boundary corpus, static Space metadata, and offline HTML shape. It writes
a local dry-run publish bundle without uploading anything.

For a Homebrew tap dry run, run:

```bash
uv run python scripts/homebrew_artifact_smoke.py
```

That smoke validates the formula template and writes a local dry-run tap bundle.
Until PyPI release values and Python resource stanzas are added, Homebrew status
is `deferred_until_pypi_and_resources`.

For a clean install proof, run:

```bash
uv run python scripts/clean_install_smoke.py
```

That smoke builds a wheel, installs it into a disposable virtual environment,
runs the same offline CLI lifecycle outside the source tree, verifies packaged
skills and release assets, and checks that the npm shim can delegate to the
installed Python package.

For a local npm package proof, run:

```bash
uv run python scripts/npm_package_smoke.py
```

That smoke packs `npm/` into a local `.tgz`, installs it into a disposable Node
project, and drives the offline CLI lifecycle through
`node_modules/.bin/gsigmad` while delegating to the clean installed Python
wheel.

## License

Apache-2.0. See [LICENSE](LICENSE).
