# Failure Taxonomy

This taxonomy describes public-safe governance fixture families for `gsigmad`
release evidence. It is intentionally about workflow governance, not scientific
truth.

## Status Values

- `FAIL`: a deterministic gate rejects the fixture.
- `MISSING_GATE`: the fixture identifies a category that the represented
  release surface does not yet adjudicate.
- `RUNNER_LIMITATION`: a gate may exist, but the measurement runner did not
  create the state needed to exercise it.
- `ADVISORY_OR_FAIL`: the current release must surface the issue without
  reporting it as an unconditional PASS.
- `NOT_CONFIGURED`: an external integration is absent and must not be reported
  as PASS.

## Fixture Families

| Family | Governance risk | Expected boundary |
| --- | --- | --- |
| `fake_or_non_resolving_citation` | A claim cites a source that does not resolve. | Citation resolution is deterministic; non-resolving anchors fail. |
| `vague_or_non_testable_hypothesis` | The hypothesis cannot be tested as written. | `h1_completeness` fails incomplete H1 wording. |
| `evidence_class_inflation` | Correlation, association, or model fit is promoted to causal language. | `evidence_class_guardrail` fails causal claims from non-causal evidence. |
| `reproducibility_declaration_without_replay_material` | A reproducibility claim lacks seed, environment, or replay material. | `reproducibility_declaration` fails reproducibility claims without seed and environment evidence. |
| `post_hoc_hypothesis_swap` | A locked hypothesis is changed after data access. | Deviation lock checks require runner-created lock state. |
| `missing_alpha_or_mesi` | Confirmatory work lacks alpha or minimum effect size of interest. | Confirmatory preregistration contract fails. |
| `bad_or_absent_data_contract` | Observed data do not satisfy declared fields. | Data-contract validation fails. |
| `absent_manifest` | Results or artifacts lack a manifest. | Gate must warn or fail; it must not silently pass. |
| `missing_adapter` | A private or optional integration is unavailable. | Report `not_configured`, never PASS. |
| `drift_or_changed_classification_state` | Governance state changes after registration. | Drift scan must surface the state change. |

## Human Review Rule

A fixture can become benchmark evidence only after human review confirms that
the row is synthetic or public-safe, the expected gate is named correctly, and
the row supports only a narrow gate-behavior claim.
