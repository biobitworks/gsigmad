# Public Benchmark Plan

This is the public-safe shape of a future "bad science workflow" benchmark.
It is not yet a ratified benchmark dataset.

A draft public seed corpus now lives in `examples/benchmark/`:

- `bad_science_fixtures.jsonl` covers the minimum fixture families below.
- `claim_boundary_corpus.jsonl` records where creative inference enters and
  where deterministic gates must take over.
- `failure_taxonomy.md` defines release-evidence status values and fixture
  families.

These files are synthetic public release artifacts. They remain
`draft_public_seed` until a human reviewer ratifies the rows for a versioned
benchmark release.

## Purpose

The benchmark should measure whether deterministic gates catch specific
governance violations and whether public release behavior matches private
development behavior for the same sanitized fixtures.

It should not estimate the real-world prevalence of misconduct or imply that a
passing gate validates scientific truth.

## Fixture Families

Minimum public fixture families:

- fake or non-resolving citations
- vague or non-testable hypotheses
- evidence-class inflation, including correlation promoted to causation
- reproducibility declarations without seed, environment, or replay material
- post-hoc hypothesis swaps after locked preregistration
- missing alpha or minimum effect size of interest for confirmatory work
- bad or absent data contracts
- absent manifests
- missing adapters reported as `not_configured`
- drift or changed classification state

## Required Row Fields

Each benchmark row should include:

- stable fixture ID
- domain
- synthetic fixture text or file path
- violation family
- expected gate (a canonical module-resolvable identifier where one exists,
  e.g. `h1_completeness`, `evidence_class_guardrail`, `reproducibility_declaration`)
- expected status
- observed public status
- observed private status, if measured
- deterministic replicate count
- unique output count
- runner limitations, if any
- claim ceiling
- PI ratification status
- **`gate_surface_version`** - the package version string of the gate surface
  the row was measured against (e.g. `"1.2.0b1"`). Required on every row;
  a row without this field is treated as `unmeasured` and may not be cited
  in any public claim about gate coverage.

Recommended (add when the row's evidence requires explicit historicization):

- `measurement_version` - `pre_remediation` | `post_remediation` | `unmeasured`.
  Use when a row records evidence about a gate that was added in a later
  package version (e.g. v2.4 remediation gates) and the row's status reflects
  the older surface.
- `artifact_status` - `synced` | `stale` | `pending_remeasurement` |
  `historical_pre_remediation` | `draft_public_seed`. Use when the row's
  observed status disagrees with the current package's gate surface.
- `expected_gate_module` - the canonical dotted module path
  (`gsigmad.governance.gates.h1_completeness`) when one exists, or
  `not_applicable` for runner-state requirements. Use to remove ambiguity
  between human-readable gate names and the shipped module.

## Synchronization Rule

Public benchmark and demo rows must remain synchronized with the shipped gate
surface (see `docs/CAPABILITY_MATRIX.md`). Before each public tag:

- No row may report `MISSING_GATE` for a category that the current package
  ships a gate for. Such a row must either (a) be re-measured against the
  current gate surface with `gate_surface_version` set to the current package
  version, or (b) be explicitly labeled `measurement_version: pre_remediation`
  AND `artifact_status: historical_pre_remediation`.
- No row may name a gate identifier that does not resolve to either a shipped
  module or a documented runner-state requirement.
- A "claim-surface sync" check is part of the pre-tag release gate.

## Demo Dataset vs Benchmark Dataset

The Hugging Face artifact at `examples/huggingface/dataset/` is a *demo
dataset*, not a benchmark dataset. The GitHub artifacts at
`examples/benchmark/` are a *seed corpus*, not a benchmark dataset. A separate
"benchmark dataset" will only be published after the PI ratification gate
below passes; until then, both surfaces use only "demo" or "seed" wording.

## Ratification Gate

No fixture becomes public benchmark evidence until a human reviewer confirms:

- it is synthetic or public-safe
- the expected violation is unambiguous
- the expected gate is named correctly
- no private project names, data, adapters, paths, or receipts are exposed
- the row supports only a narrow gate-behavior claim

## Output Surfaces

- GitHub: benchmark generator, fixtures, tests, and release receipts.
- Hugging Face dataset card: sanitized benchmark rows and caveats.
- Hugging Face Space: static or interactive visualization of deterministic gate
  outcomes and creative-inference boundaries.
- Zenodo: archived software release and, only after ratification, versioned
  benchmark artifacts.
