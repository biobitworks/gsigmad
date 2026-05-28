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
- expected gate
- expected status
- observed public status
- observed private status, if measured
- deterministic replicate count
- unique output count
- runner limitations, if any
- claim ceiling
- PI ratification status

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
