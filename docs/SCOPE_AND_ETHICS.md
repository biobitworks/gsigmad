# Scope and Ethics

`gsigmad` is not a truth machine.

It is a local-first governance layer for AI-assisted research workflows. Its
job is to make hypotheses, experiment state, evidence classes, provenance, and
promotion decisions explicit enough for humans and downstream tools to review.

## Safe Public Claims

Use these claims unless stronger evidence has been produced and reviewed:

- Local-first science governance layer for AI-assisted research.
- Agent Skills bundle plus CLI for preregistration, lab-notebook closure, claim
  audit, provenance, and no-writeback defaults.
- Deterministic boundary harness for identifying where AI-assisted scientific
  workflows leave rules and enter inference.
- Public release mirror with sanitized examples, offline quickstart, package
  smoke tests, and optional Hugging Face demo artifacts.

## Claims to Avoid

Do not claim that `gsigmad`:

- validates biological, clinical, mathematical, or scientific truth
- catches all scientific misconduct
- replaces OSF, Galaxy, Renku, WorkflowHub, Arvados, MLflow, W&B, ELNs, or
  workflow engines
- performs autonomous scientific discovery
- publishes, deposits, or writes to external science databases by default
- turns missing adapters, skipped citations, or unavailable databases into PASS

## Deterministic vs Creative Work

Creative inference may enter when a human or model proposes a hypothesis,
interpretation, model choice, literature synthesis, or next experiment.

Deterministic gates start after that proposal exists. Gates can check recorded
structure, local files, citations, claim labels, manifests, preregistration
fields, and no-writeback boundaries. A passing gate means the checked rule
passed for the available artifact. It does not mean the claim is true.

## Evidence Classes

Use the lowest defensible claim class:

- `HYPOTHESIS`: proposed but not measured.
- `INFERRED`: derived from measured or cited evidence but not directly measured
  in the current experiment.
- `MEASURED`: directly measured under the recorded experiment conditions.

Any causal wording needs explicit causal evidence. Correlation, association, or
model fit is not enough by itself.

## Data and Privacy

Do not put these in public examples, release artifacts, Hugging Face demo
datasets, issues, or pull requests:

- secrets, API keys, credentials, database URLs, or tokens
- private adapters, internal project names, or operator-only receipts
- patient data, controlled-access data, row-level research data, raw sequences,
  or personally identifiable information
- unpublished manuscript contents, confidential invention disclosures, or
  embargoed reviewer material

Synthetic examples must be labeled as synthetic. Missing integrations must be
reported as `not_configured`, never PASS.

## Public Benchmark Boundary

Public benchmark fixtures should be treated as adversarial governance fixtures,
not as a scientific dataset. They can support narrow statements such as:

- this gate caught this synthetic violation class
- this gate missed this fixture class
- this runner could not exercise this gate
- public and private release behavior matched for this fixture set

They do not support broad statements about scientific misconduct prevalence,
truth validation, clinical validity, or domain-wide governance coverage.

## Human Review

Human review remains required for:

- accepting or revising hypotheses and fixtures
- selecting statistical tests and minimum effect sizes of interest
- deciding whether evidence justifies claim promotion
- approving external publication, DOI deposit, or database writeback
- handling restricted data, human-subjects data, and institutional policy
