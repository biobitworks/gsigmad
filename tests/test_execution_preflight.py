"""Unit tests for Phase 20 execution preflight helpers (EXEC-02)."""
from __future__ import annotations

from gsigmad.governance import execution_preflight as preflight
from gsigmad.governance.execution_preflight import (
    RATIFIED_PROMOTION_AUTHORITY,
    check_hypothesis_promotion,
)
from gsigmad.governance.human_gates import build_promotion_gate


def _claims_fixture() -> list[dict]:
    return [
        {
            "id": "claim-measured-mismatch",
            "text": "We hypothesize this treatment could improve response rates.",
            "classification": "MEASURED",
        },
        {
            "id": "claim-inferred",
            "text": "The pattern suggests a treatment effect (p < 0.01).",
            "classification": "INFERRED",
        },
        {
            "id": "claim-unclassified",
            "text": "Additional follow-up work may clarify the mechanism.",
        },
    ]


def _exp_record(
    classification: str = "CONFIRMATORY",
    *,
    promotion_authority: str | None = None,
    claims: list[dict] | None = None,
) -> dict:
    record = {
        "exp_id": "EXP-20.1",
        "classification": classification,
        "status": "planned",
        "scaffold_state": "ready",
        "claims": claims if claims is not None else _claims_fixture(),
    }
    if promotion_authority is not None:
        record["promotion_authority"] = promotion_authority
    return record


def test_run_execution_preflight_calls_claim_lint_without_citation_verification(monkeypatch):
    """Preflight reuses audit_claims_gate offline and normalizes findings."""
    captured: dict[str, object] = {}

    def fake_audit(claims, verify_citations=True):
        captured["claims"] = claims
        captured["verify_citations"] = verify_citations
        return {
            "pass": False,
            "failures": [{"error": "STAT_RIGOR_VIOLATION: missing effect size"}],
            "warnings": ["CLAIM_LINT_WARNING: citation verification skipped"],
        }

    monkeypatch.setattr(preflight, "audit_claims_gate", fake_audit)
    monkeypatch.setattr(
        preflight,
        "check_hypothesis_promotion",
        lambda exp_record: {
            "pass": True,
            "error": None,
            "warnings": ["HYPOTHESIS_PROMOTION_UNDECLARED: claim[2] has no declared tier"],
            "details": [],
        },
    )

    result = preflight.run_execution_preflight(_exp_record())

    assert captured["claims"] == _claims_fixture()
    assert captured["verify_citations"] is False
    assert result["passed"] is False
    assert result["failures"] == ["STAT_RIGOR_VIOLATION: missing effect size"]
    assert result["warnings"] == [
        "CLAIM_LINT_WARNING: citation verification skipped",
        "HYPOTHESIS_PROMOTION_UNDECLARED: claim[2] has no declared tier",
    ]
    assert result["checks"] == [
        {
            "name": "claim_lint",
            "pass": False,
            "error": "STAT_RIGOR_VIOLATION: missing effect size",
            "warnings": ["CLAIM_LINT_WARNING: citation verification skipped"],
        },
        {
            "name": "hypothesis_promotion",
            "pass": True,
            "error": None,
            "warnings": ["HYPOTHESIS_PROMOTION_UNDECLARED: claim[2] has no declared tier"],
        },
    ]


def test_check_hypothesis_promotion_flags_ratified_promotions_only_when_classifier_authorized():
    """Ratified promotion violations become blocking only with the exact EXP authority."""
    result = check_hypothesis_promotion(
        _exp_record(
            promotion_authority=RATIFIED_PROMOTION_AUTHORITY,
            claims=[
                {
                    "id": "claim-measured-mismatch",
                    "text": "We hypothesize this treatment could improve response rates.",
                    "classification": "MEASURED",
                }
            ],
        )
    )

    assert result["pass"] is False
    assert result["error"] == (
        "HYPOTHESIS_PROMOTION_VIOLATION: claim[0] declares MEASURED above detected HYPOTHESIS"
    )
    assert result["warnings"] == []
    assert result["details"] == [
        {
            "claim_index": 0,
            "authority": RATIFIED_PROMOTION_AUTHORITY,
            "declared_tier": "MEASURED",
            "detected_tier": "HYPOTHESIS",
            "ratified": True,
        }
    ]


def test_check_hypothesis_promotion_emits_advisories_for_unratified_and_undeclared_claims():
    """Missing tiers and unratified mismatches stay advisory in Phase 20."""
    result = check_hypothesis_promotion(
        _exp_record(
            promotion_authority="other-authority",
            claims=[
                {
                    "id": "claim-measured-mismatch",
                    "text": "We hypothesize this treatment could improve response rates.",
                    "classification": "MEASURED",
                },
                {
                    "id": "claim-unclassified",
                    "text": "Additional follow-up work may clarify the mechanism.",
                },
            ],
        )
    )

    assert result["pass"] is True
    assert result["error"] is None
    assert result["warnings"] == [
        "HYPOTHESIS_PROMOTION_UNRATIFIED: claim[0] declares MEASURED above detected HYPOTHESIS",
        "HYPOTHESIS_PROMOTION_UNDECLARED: claim[1] has no declared tier",
    ]
    assert result["details"] == [
        {
            "claim_index": 0,
            "authority": "other-authority",
            "declared_tier": "MEASURED",
            "detected_tier": "HYPOTHESIS",
            "ratified": False,
        },
        {
            "claim_index": 1,
            "authority": "other-authority",
            "declared_tier": None,
            "detected_tier": "HYPOTHESIS",
            "ratified": False,
        },
    ]


def test_check_hypothesis_promotion_accepts_approved_human_gate_surface() -> None:
    gate = build_promotion_gate(RATIFIED_PROMOTION_AUTHORITY)
    record = _exp_record(
        promotion_authority=None,
        claims=[
            {
                "id": "claim-measured-mismatch",
                "text": "We hypothesize this treatment could improve response rates.",
                "classification": "MEASURED",
            }
        ],
    )
    record["human_review_gates"] = [gate.model_dump(mode="json")]

    result = check_hypothesis_promotion(record)

    assert result["pass"] is False
    assert result["details"][0]["authority"] == RATIFIED_PROMOTION_AUTHORITY
    assert result["details"][0]["ratified"] is True
