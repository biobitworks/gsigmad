# gsigmad Public Benchmark Seed

This directory contains public-safe synthetic seed artifacts for future
benchmark work. It is not a ratified benchmark dataset and should not be used
to claim scientific truth validation or broad misconduct coverage.

## Files

- `bad_science_fixtures.jsonl`: synthetic adversarial workflow fixtures across
  the public failure taxonomy.
- `claim_boundary_corpus.jsonl`: examples of where creative inference is
  allowed and where deterministic gates must take over before claim promotion.
- `failure_taxonomy.md`: public taxonomy for deterministic gate failures,
  missing gates, runner limitations, and no-writeback boundaries.

## Claim Boundary

Rows in this directory support narrow release-evidence statements only:

- this fixture family is represented in the public seed corpus
- this deterministic gate is expected to adjudicate the fixture
- this creative-inference stage is explicitly bounded
- this row is synthetic and public-safe

Rows do not support claims that `gsigmad` catches all scientific misconduct,
validates biological or mathematical truth, or replaces workflow engines,
registries, ELNs, or ML run trackers.
