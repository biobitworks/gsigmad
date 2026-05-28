"""
Evidence-class guardrail — v2.4 remediation gate.

Deterministic guardrail that catches *evidence-class inflation*: claims whose
``claim_type`` is causal (or whose ``claim_text`` uses causal language) but
whose supporting ``evidence_type`` is correlational/observational and which
were not produced by an intervention.

This plugs the v2.3 main-factorial leak where the ``evidence-class-inflation``
violation slipped through 0/10 in all 8 cells (4 domains x 2 envs): there was
no gate category responsible for catching it. The existing ``audit_claims``
gate enforces effect-size + CI but not causal-vs-correlational classification.

Pure-function module:

* deterministic
* no LLM
* no network
* no file I/O

Reference: CANON-CORE §causal-evidence (no causal claims from correlational
evidence absent intervention/RCT/instrumental variable), EXPERIMENT_STANDARDS
§15 (no arbitrary shortcuts — evidence classification follows the same rules
as data).
"""
from __future__ import annotations

import re
from typing import Optional

# -- TRAITS pillar mapping --

TRAITS_PILLARS: dict[str, list[str]] = {
    "evidence_class_guardrail": ["Accurate", "Interpretable"],
}


# ─── Violation type constants ────────────────────────────────────────────────

CAUSAL_FROM_CORRELATIONAL = "CAUSAL_CLAIM_FROM_CORRELATIONAL_EVIDENCE"
CAUSAL_MISSING_EVIDENCE = "CAUSAL_CLAIM_MISSING_EVIDENCE_TYPE"
CAUSAL_LANGUAGE_IN_CORRELATIONAL = "CAUSAL_LANGUAGE_IN_CORRELATIONAL_CLAIM"


# ─── Causal-language detection ───────────────────────────────────────────────
# Each phrase is matched as a whole-token sequence to avoid false positives on
# substrings like "because" (which contains "cause" but is not a causal claim
# marker on its own here).
_CAUSAL_LANGUAGE_PHRASES: tuple[str, ...] = (
    "causes",
    "causally drives",
    "causally produces",
    "is caused to",
    "caused by",
    "causal effect of",
)

_CAUSAL_LANGUAGE_PATTERN = re.compile(
    r"\b(?:"
    + "|".join(re.escape(p) for p in _CAUSAL_LANGUAGE_PHRASES)
    + r")\b",
    re.IGNORECASE,
)


# ─── Evidence-type categorisation ────────────────────────────────────────────
# Evidence types that, on their own, cannot support a causal claim without an
# explicit intervention (RCT, perturbation, knockout, instrumental variable,
# regression discontinuity, etc.).
_NON_CAUSAL_EVIDENCE_TYPES: frozenset[str] = frozenset({
    "correlational",
    "observational",
})


# ─── Public API ──────────────────────────────────────────────────────────────

def check_evidence_class_match(claim: dict) -> dict:
    """
    Check that a claim's declared causal status matches its evidence type.

    Catches three flavours of evidence-class inflation:

    a. ``claim_type == "causal"`` AND ``evidence_type`` in
       ``{"correlational", "observational"}`` AND ``intervention`` is not
       ``True`` → ``CAUSAL_CLAIM_FROM_CORRELATIONAL_EVIDENCE``.
    b. ``claim_type == "causal"`` AND ``evidence_type`` is missing/None →
       ``CAUSAL_CLAIM_MISSING_EVIDENCE_TYPE``.
    c. ``claim_text`` contains causal language (e.g. "causes",
       "causally drives", "caused by") AND ``evidence_type`` is
       ``"correlational"`` or ``"observational"`` →
       ``CAUSAL_LANGUAGE_IN_CORRELATIONAL_CLAIM``. This fires even if
       ``claim_type`` is benign (e.g. "descriptive", "correlational"),
       because the *text* makes a causal assertion the evidence cannot
       support.

    Args:
        claim: A claim dict with optional keys:
            - ``claim_type``: str — e.g. "causal", "correlational",
              "descriptive".
            - ``evidence_type``: Optional[str] — e.g. "correlational",
              "observational", "experimental", "interventional".
            - ``claim_text``: Optional[str] — the claim text itself.
            - ``intervention``: Optional[bool] — True if the evidence comes
              from an intervention/RCT/perturbation that justifies a causal
              claim.

    Returns:
        ``{"pass": bool, "error": Optional[str], "violation_type": Optional[str]}``

        On pass: ``{"pass": True, "error": None, "violation_type": None}``.
        On fail: ``error`` includes the ``violation_type`` token plus a
        one-sentence explanation; ``violation_type`` is one of the constants
        above.
    """
    claim_type = claim.get("claim_type")
    evidence_type = claim.get("evidence_type")
    claim_text = claim.get("claim_text") or ""
    intervention = claim.get("intervention", False) is True

    # Normalise string-valued fields to lowercase for comparison while leaving
    # the original dict untouched.
    claim_type_norm = claim_type.lower() if isinstance(claim_type, str) else None
    evidence_type_norm = (
        evidence_type.lower() if isinstance(evidence_type, str) else None
    )

    # Rule (b): causal claim with no evidence_type at all.
    # Checked before rule (a) so a missing evidence_type produces the more
    # specific error rather than silently being treated as "not correlational".
    if claim_type_norm == "causal" and evidence_type_norm is None:
        return {
            "pass": False,
            "error": (
                f"{CAUSAL_MISSING_EVIDENCE}: Claim declares claim_type='causal' "
                "but provides no evidence_type — causal claims require an "
                "explicit evidence type (experimental/interventional) and an "
                "intervention=True flag."
            ),
            "violation_type": CAUSAL_MISSING_EVIDENCE,
        }

    # Rule (a): causal claim from correlational/observational evidence without
    # an explicit intervention flag.
    if (
        claim_type_norm == "causal"
        and evidence_type_norm in _NON_CAUSAL_EVIDENCE_TYPES
        and not intervention
    ):
        return {
            "pass": False,
            "error": (
                f"{CAUSAL_FROM_CORRELATIONAL}: Claim declares claim_type='causal' "
                f"but evidence_type='{evidence_type}' is correlational/"
                "observational and no intervention=True flag is set — "
                "correlational evidence cannot support a causal claim without "
                "an explicit intervention (RCT, perturbation, instrumental "
                "variable, or equivalent)."
            ),
            "violation_type": CAUSAL_FROM_CORRELATIONAL,
        }

    # Rule (c): causal language in the claim text while evidence is
    # correlational/observational, regardless of claim_type field.
    if (
        evidence_type_norm in _NON_CAUSAL_EVIDENCE_TYPES
        and _CAUSAL_LANGUAGE_PATTERN.search(claim_text)
    ):
        return {
            "pass": False,
            "error": (
                f"{CAUSAL_LANGUAGE_IN_CORRELATIONAL}: claim_text uses causal "
                f"language while evidence_type='{evidence_type}' is "
                "correlational/observational — rewrite the claim in "
                "associative/correlational terms (e.g. 'is associated with', "
                "'co-occurs with') or upgrade the evidence to an intervention."
            ),
            "violation_type": CAUSAL_LANGUAGE_IN_CORRELATIONAL,
        }

    # Otherwise pass.
    return {"pass": True, "error": None, "violation_type": None}


__all__ = [
    "check_evidence_class_match",
    "CAUSAL_FROM_CORRELATIONAL",
    "CAUSAL_MISSING_EVIDENCE",
    "CAUSAL_LANGUAGE_IN_CORRELATIONAL",
    "TRAITS_PILLARS",
]
