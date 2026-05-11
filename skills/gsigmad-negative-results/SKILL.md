---
name: gsigmad-negative-results
description: "Register and document negative experimental results. Use when an experiment fails to confirm a hypothesis. Updates NEGATIVE_RESULTS_REGISTRY.md and enforces forward-link requirements for future experiments."
allowed-tools:
  - Read
  - Write
  - Bash
---

# Negative Result Protection

Register falsified findings and enforce forward-linking in new prompts/experiments.

## Protocol

1. Identify the negative result or falsified hypothesis.
2. Register it in the project's negative results registry.
3. Ensure forward-linking: any future experiment touching the same proteins, parameters, or hypotheses must reference this negative result.

## Registration Format

Add to `experiments/NEGATIVE_RESULTS_REGISTRY.md` (create if missing):

| Date | EXP-### | H₀ | H₁ | Test | p-value | Effect Size | Power | Decision | Implication | Forward-Link |
|------|---------|-----|-----|------|---------|-------------|-------|----------|-------------|-------------|
| YYYY-MM-DD | EXP-### | [null hypothesis] | [alternative] | [test name] | [p] | [effect size (measure)] | [power] | FAIL-TO-REJECT / FALSIFIED | [what this means] | Yes: any EXP touching [X] must cite this |

**Power column is critical**: Distinguish between "true null" (high power, small effect — the hypothesis is genuinely wrong) and "underpowered" (low power — we cannot tell; need more data or a better design).

## Forward-Link Enforcement

When creating new experiments or prompts:
1. Check the negative results registry for conflicts
2. If the new work touches a previously falsified hypothesis:
   - Cite the negative result explicitly
   - Explain why the new approach differs
   - Document what new evidence justifies revisiting

## Report Back

- Negative result registered (EXP-### and hypothesis)
- Forward-link requirements set
- Registry path
