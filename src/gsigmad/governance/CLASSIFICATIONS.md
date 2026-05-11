# gsigmad Canonical PROMPT Classification Taxonomy

**Status:** ACTIVE
**Owner:** gsigmad governance
**First authored:** 2026-05-10 (PROMPT-001 EXP-007 remediation)
**Pre-registration SIG (originating EXP):** SIG-20260510T191755Z-claude-c08e

This is the canonical contract for what classification a `PROMPT-NNN` may
declare in any `PROMPT_EXP_MAP.md` across the active-projects portfolio.

A classification listed here is **canonical**. Any classification used by a
PROMPT but not listed here fails `EXP-007` (PROMPT classification
canonical-membership compliance) and must be either (a) added to this
contract via the addition procedure below, or (b) replaced by a canonical
class.

## Canonical classes

### `CONFIRMATORY`

A pre-registered hypothesis test against an explicitly stated null. Required
fields in the PROMPT artifact:

- `H0` (null hypothesis, exact statistical statement)
- `H1` (alternative hypothesis, directional or two-sided)
- `test` (statistical test name)
- `alpha` (significance threshold; typically 0.05)
- `MESI` (minimum effect size of interest, justified, not arbitrary)
- `N` (sample size + power justification for ≥ 0.80 to detect MESI at alpha)
- `decision_rule` (explicit mapping from observed statistic to {H0_retained, H1_supported, INCONCLUSIVE_*})

A CONFIRMATORY classification mandates a reserved EXP-NNN with its
pre-registration block git-frozen before any data collection.

### `REPLICATION`

A reproduction of a published or prior-recorded CONFIRMATORY result. Required
fields are identical to CONFIRMATORY, plus:

- `replicates` (citation or PROMPT/EXP id of the original CONFIRMATORY)

### `EXPLORATORY`

Hypothesis-generating work that does **not** carry the strict pre-registration
gate. Permitted fields are looser, but the PROMPT must explicitly mark itself
EXPLORATORY in this column so downstream audits do not promote its outputs
into claim-grade evidence. EXPLORATORY work may not promote scientific claims
without first becoming a CONFIRMATORY follow-up.

## Conditional classes (require explicit gate definition)

A class outside the three above is admissible only if this contract defines
its own gate. The procedure:

1. Operator drafts an addition proposal under `.planning/quick/<date>-classification-addition-<slug>/`.
2. The proposal must specify:
   - the class name in SCREAMING_SNAKE_CASE
   - what gate the class enforces (e.g. "no-claim-promotion", "must-cite-existing-PROMPT", "operator-attestation-required")
   - which PROMPT fields are required vs forbidden under the class
   - which downstream destinations the class permits / blocks
3. PROMPT-001 program (or successor) opens an EXP-NNN to validate the gate.
4. On EXP closure, this file is updated with the new class block.

**Until step 4 ships, the class is non-canonical and EXP-007 fails the row.**

### Currently pending addition: `GOVERNANCE_EXPORT_TRACEABILITY`

Identified in SeedGraph PROMPT_EXP_MAP.md (PROMPT-001 + PROMPT-002,
PROMPT-001 sub-rows). Used informally to mean "this PROMPT produces
governance/export artifacts; no scientific claim is promoted; no EXP is
reserved." That use case is real but the gate is not defined in this
contract. Operator action required:

- (a) Author addition proposal per the procedure above, **or**
- (b) Re-classify the affected SeedGraph PROMPTs to `EXPLORATORY` with an
  explicit "no-claim-promotion" boundary statement.

Either action closes EXP-007 post-remediation.

## What this contract does NOT cover

- PROMPT *status* (ACTIVE / CLOSED / SUPERSEDED) — separate column.
- Classifier of EXP outcome — that is `decision ∈ {H0_retained, H1_supported, INCONCLUSIVE_*, PENDING_HUMAN_PARTICIPANTS}`.
- Outcome verdicts like `COMPLETE_PASS` — those are run-level results, not
  PROMPT-level classifications, and should not appear in the classification
  column.

## Audit hook

`EXP-007` (`experiments/EXP_007_PROMPT_CLASSIFICATION_COMPLIANCE.md`) re-runs
on every gsigmad release candidate. The audit cross-references every
PROMPT_EXP_MAP.md classification cell across the active-projects portfolio
against this file. Any mismatch fails the release.

## Hard rails

- This contract is read-only for runtime systems. Mutation requires a
  governed PROMPT (typically PROMPT-NNN under PROMPT-001's program).
- No live writeback is implied by classifying a PROMPT.
- Classification does not bestow truth-promotion authority; truth promotion
  remains gated by Overwatch.
