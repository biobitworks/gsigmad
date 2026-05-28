# gsigmad 1.2.0b1 Capability Matrix

This matrix describes the public beta gate surface. It is release metadata, not
a claim that `gsigmad` validates scientific truth or catches all misconduct.

## Deterministic Gates

| Fixture family | Public gate surface | Public beta status |
| --- | --- | --- |
| Fake or non-resolving citation | `citation_resolution` / audit citation gate | `FAIL` |
| Vague or non-testable H1 | `h1_completeness` | `FAIL` |
| Evidence-class inflation | `evidence_class_guardrail` | `FAIL` |
| Reproducibility declaration without seed/environment | `reproducibility_declaration` | `FAIL` |
| Post-hoc hypothesis swap | `deviation_lock_check` | `FAIL` when locked preregistration state exists; runner must create that state |
| Missing alpha or MESI | `confirmatory_preregistration_contract` | `FAIL` |
| Bad or absent data contract | `data_contract` | `FAIL` |
| Absent manifest | `manifest_presence` | `ADVISORY_OR_FAIL` |
| Missing optional adapter | `adapter_resolution` | `NOT_CONFIGURED`, never PASS |
| Drift or changed classification state | `drift_scan` | `ADVISORY_OR_FAIL` |

## Claim Boundary

The synthetic examples in `examples/benchmark/` and
`examples/huggingface/dataset/` are draft public seed artifacts. They are useful
for release smoke tests and gate-boundary demos. They are not a ratified
benchmark dataset.

Use this wording:

- "synthetic public benchmark seed corpus"
- "deterministic gate-boundary demo"
- "represented public beta gate surface"

Do not use this wording:

- "validated benchmark"
- "scientific truth validation"
- "all scientific misconduct coverage"

## Figure Governance Boundary

The figure-governance skill (`gsigmad-figure-create`) is part of the public
package. Its output, however, is governed *local* evidence at this release:

- Every figure rendered by the skill is recorded with
  `figure_destination=local_only`.
- The deterministic byte-identical render is captured in a signed local
  manifest alongside the figure file.
- Figure writeback to `overwatch_evidence`, `seedgraph_document`, or any
  other knowledge-graph target is **deferred** and is **not** part of the
  `1.2.0b1` release. Writeback would require operator-approved use of
  `gsigmad-writeback-overwatch` or `gsigmad-ingest-publications-json`
  against a hardened gate path that is not in scope for this beta.

Allowed public wording:

- "governed local figure evidence"
- "deterministic byte-identical figure rendering"
- "figure writeback is operator-approved and deferred"

Prohibited public wording:

- any framing that suggests gsigmad-rendered figures are automatically
  promoted to Overwatch, SeedGraph, or other knowledge-graph evidence
- any framing that calls a local figure manifest "published" or "deposited"
- any framing that conflates figure render reproducibility with scientific
  truth validation

The internal artifact FIGURE-001 (a specific catch-rate heatmap rendered by
`gsigmad-figure-create`) is intentionally *not* present in this public mirror
and is referenced here only as the abstract capability: the skill exists
publicly; the artifact stays local in the upstream development repo.
