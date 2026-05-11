---
name: gsigmad-audit-claims
description: "Lint documents for unsupported claims, evidence-class mismatches, and causal overreach. Use when reviewing scientific claims for statistical rigor, citation traceability, and evidence classification compliance."
allowed-tools:
  - Read
  - Bash
  - Grep
---

# Audit Claims

Lint documents for unsupported claims, evidence-class mismatches, and causal overreach.

## Effect Size Enforcement Gate (REQUIRED — run per claim)

For every claim containing a p-value, run the effect size gate before any other linting:

```python
from gsigmad.governance.gates.audit_claims import audit_claims_gate, check_effect_size_reporting

# Per-claim effect size check
result = check_effect_size_reporting(claim_text)
if not result["pass"]:
    raise SystemExit(result["error"])  # HALT — error contains STAT_RIGOR_VIOLATION
    # result["recommendation"] provides the fix template
```

Per CANON-CORE Invariant 6: every statistical test must report BOTH an effect size measure AND a 95% confidence interval. A p-value without effect size + CI triggers `STAT_RIGOR_VIOLATION`.

## Claim Audit Gate (batch)

```python
from gsigmad.governance.gates.audit_claims import audit_claims_gate

result = audit_claims_gate(claims=claims_list, verify_citations=True)
if not result["pass"]:
    raise SystemExit(result["error"])  # HALT
```

## Claim Linter

Scan the specified document(s) for:
1. Claims without supporting evidence anchors (PMID/DOI/figure/table reference)
2. Evidence-class mismatches (e.g., "measured" label on an inferred value)
3. Missing Claim-to-Evidence Map entries
4. Parameters used in hard formulas that trace back to HYPOTHESIS-class claims

Output a fix list with:
- Line number, claim text, current evidence class, recommended action

## Hypothesis Promotion

For each claim found, classify as:
- **MEASURED**: Direct experimental observation with anchored evidence
- **INFERRED**: Derived from measured data via documented computation
- **HYPOTHESIS**: Unsubstantiated or weakly supported

Rules:
- HYPOTHESIS claims: set parameterization_allowed=no
- Promote only when new evidence is anchored (not when reasoning sounds plausible)
- Demote when evidence is retracted or contradicted

## DOI/PMID Verification

For every cited DOI or PMID, verify existence:

```python
from gsigmad.governance.gates.audit_claims import verify_doi, verify_pmid

# DOI check
doi_result = verify_doi(doi)
# Returns: {"verified": True, "title": str}          — exists
#          {"verified": False, "error": "DOI_NOT_FOUND: ..."}  — does not exist (hard fail)
#          {"verified": "TIMEOUT", "warning": "..."}           — network timeout (soft fail: UNVERIFIED_PENDING)

# PMID check
pmid_result = verify_pmid(pmid)
```

Per Pitfall 5 (DOI timeout policy):
- Network timeout → soft fail: mark claim `UNVERIFIED_PENDING`; do not block research
- Explicit 404 (DOI does not exist) → hard fail: `DOI_NOT_FOUND` error
- `UNVERIFIED_PENDING` claims cannot support CONFIRMATORY evidence chains

## Causal Guardrail

Find causal-overreach language:
- "X causes Y" without causal evidence (intervention/RCT)
- "X leads to Y" when only correlation is shown
- "demonstrates" or "proves" for observational data

Rewrite to correlation-safe phrasing unless causal evidence exists:
- "X is associated with Y"
- "X correlates with Y"
- "X may contribute to Y"

## Report Back

- Total claims audited
- Claims by evidence class (MEASURED/INFERRED/HYPOTHESIS)
- Fix list (unsupported claims, mismatches, causal overreach)
- Recommended promotions/demotions
- Citation verification results (verified / DOI_NOT_FOUND / UNVERIFIED_PENDING counts)
