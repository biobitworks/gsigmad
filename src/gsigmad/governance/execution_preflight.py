"""Execution preflight helpers for Phase 20 run governance."""
from __future__ import annotations

from gsigmad.commands.classify import _classify_text
from gsigmad.governance.gates.audit_claims import audit_claims_gate
from gsigmad.governance.human_gates import resolve_promotion_gate

RATIFIED_PROMOTION_AUTHORITY = "phase20-local-text-classifier-v1"
_TIER_RANK = {"HYPOTHESIS": 0, "INFERRED": 1, "MEASURED": 2}


def _normalize_tier(value: object) -> str | None:
    tier = str(value or "").strip().upper()
    return tier if tier in _TIER_RANK else None


def check_hypothesis_promotion(exp_record: dict) -> dict:
    """Compare declared claim tiers against the local text classifier."""
    failures: list[str] = []
    warnings: list[str] = []
    details: list[dict] = []
    promotion_gate = resolve_promotion_gate(
        exp_record,
        ratified_authority=RATIFIED_PROMOTION_AUTHORITY,
    )
    authority = promotion_gate["authority"]

    for index, claim in enumerate(exp_record.get("claims", [])):
        text = str(claim.get("text", "")).strip()
        declared_tier = _normalize_tier(
            claim.get("classification", claim.get("evidence_class"))
        ) or _normalize_tier(claim.get("evidence_class"))
        detected_tier, _ = _classify_text(text)
        ratified = bool(promotion_gate["approved"])
        detail = {
            "claim_index": index,
            "authority": authority,
            "declared_tier": declared_tier,
            "detected_tier": detected_tier,
            "ratified": ratified,
        }
        details.append(detail)

        if declared_tier is None:
            warnings.append(
                f"HYPOTHESIS_PROMOTION_UNDECLARED: claim[{index}] has no declared tier"
            )
            continue

        if _TIER_RANK[declared_tier] <= _TIER_RANK[detected_tier]:
            continue

        message = (
            f"claim[{index}] declares {declared_tier} above detected {detected_tier}"
        )
        if ratified:
            failures.append(f"HYPOTHESIS_PROMOTION_VIOLATION: {message}")
        else:
            warnings.append(f"HYPOTHESIS_PROMOTION_UNRATIFIED: {message}")

    return {
        "pass": len(failures) == 0,
        "error": failures[0] if failures else None,
        "warnings": warnings,
        "details": details,
    }


def run_execution_preflight(exp_record: dict) -> dict:
    """Run local claim-lint and hypothesis-promotion checks before the gate chain."""
    claim_lint = audit_claims_gate(exp_record.get("claims", []), verify_citations=False)
    promotion = check_hypothesis_promotion(exp_record)

    claim_lint_error = None
    if claim_lint.get("failures"):
        first_failure = claim_lint["failures"][0]
        claim_lint_error = first_failure.get("error") or str(first_failure)

    checks = [
        {
            "name": "claim_lint",
            "pass": claim_lint.get("pass", False),
            "error": claim_lint_error,
            "warnings": list(claim_lint.get("warnings", [])),
        },
        {
            "name": "hypothesis_promotion",
            "pass": promotion.get("pass", False),
            "error": promotion.get("error"),
            "warnings": list(promotion.get("warnings", [])),
        },
    ]

    failures = [check["error"] for check in checks if check["error"]]
    warnings: list[str] = []
    for check in checks:
        warnings.extend(check["warnings"])

    return {
        "checks": checks,
        "passed": len(failures) == 0,
        "failures": failures,
        "warnings": warnings,
        "authority": exp_record.get("promotion_authority"),
        "details": {
            "claim_lint": claim_lint.get("failures", []),
            "hypothesis_promotion": promotion.get("details", []),
        },
    }
