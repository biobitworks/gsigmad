---
name: gsigmad-ablation
description: "Run a systematic ablation study removing one component at a time. Use when isolating the contribution of model components. Generates baseline + ablation matrix with metrics, thresholds, and statistical test plan."
allowed-tools:
  - Read
  - Write
  - Bash
  - Glob
  - Grep
---

# Ablation Orchestrator

Generate a baseline + module ablation matrix with metrics, thresholds, and statistical test plan.

## Protocol

1. Identify the model/pipeline to ablate.
2. Define the baseline configuration (C0 = all modules active).
3. For each module that can be independently disabled:
   - Create configuration Ci (module i disabled, all others active)
   - Define the expected impact metric(s)
   - Define the significance threshold

## Ablation Matrix

| Config | Description | Modules Active | Expected Metric | Threshold |
|--------|-------------|----------------|-----------------|-----------|
| C0 | Baseline (all active) | all | [metric] | — |
| C1 | No AA disorder | all except Level 0 | [metric] | p < 0.05 |
| C2 | No metapredict | all except Level 0.5 | [metric] | p < 0.05 |
| C3 | No pLDDT | all except Level 1 | [metric] | p < 0.05 |
| C4 | No fragments | all except Level 2 | [metric] | p < 0.05 |
| C5 | No SEED interaction | all except Grid 2 | [metric] | p < 0.05 |

## Statistical Test Plan

For each ablation:
- Metric: [e.g., Spearman rank correlation with baseline ranking]
- Test: [e.g., Wilcoxon signed-rank, permutation test]
- Correction: [e.g., Bonferroni for N comparisons]
- Power: [estimated based on sample size]

## Execution

Generate the ablation script that:
1. Runs each configuration
2. Collects metrics
3. Computes statistical comparisons
4. Produces summary table

## Report Back

- Ablation matrix (table)
- Statistical test plan
- Script path (if generated)
- Key findings (which modules matter most)
