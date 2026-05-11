---
name: gsigmad-model-identifiability
description: "Assess whether a model's parameters are identifiable from available data. Use before CONFIRMATORY model fitting. Classifies each parameter as estimable_now, estimable_with_new_data, or hypothesis_only."
allowed-tools:
  - Read
  - Bash
---

# Model Identifiability Audit

Run an identifiability audit on model equations and classify parameters.

## Audit Protocol

1. Find the target script or model definition file.
2. Extract all tunable parameters (weights, thresholds, constants).
3. For each parameter, classify:

| Classification | Meaning | Action |
|---|---|---|
| **estimable_now** | Can be estimated from currently available data | Document data source and estimation method |
| **estimable_with_new_data** | Estimable if specific new measurements are obtained | Specify what data is needed |
| **hypothesis_only** | Cannot be estimated; based on intuition or literature analogy | Label HYPOTHESIS; set parameterization_allowed=no for hard use |

4. Check for structural identifiability issues:
   - Parameters that trade off against each other (collinear)
   - Parameters with no observable effect on outputs
   - Parameters whose values are absorbed by normalization

## Report Format

| Parameter | Current Value | Source | Classification | Evidence |
|---|---|---|---|---|
| W_AA | 0.15 | manual | hypothesis_only | No calibration data |
| K_NEIGHBORS | 15 | literature | estimable_with_new_data | Needs PPI network |

## Report Back

- Total parameters audited
- Classification counts (estimable_now / estimable_with_new_data / hypothesis_only)
- Collinearity warnings
- Recommended next measurements to improve identifiability
