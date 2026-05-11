"""Tests for the Phase 34 Antigence review contract."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from gsigmad.governance.review_contract import (
    ReviewEvidenceRef,
    ReviewRequest,
    ReviewVerdict,
)


def _evidence(kind: str = "receipt", ref: str = "RECEIPT-RUN-34-1-001") -> dict[str, str]:
    return {"ref_kind": kind, "ref": ref}


def test_review_request_requires_review_lease_and_structured_evidence() -> None:
    request = ReviewRequest.model_validate(
        {
            "request_id": "REVIEW-34-1",
            "task_id": "TASK-34-1",
            "lease_id": "LEASE-34-1",
            "fencing_token": "token-34-1",
            "lease_scope": "review",
            "reviewer": "antigence",
            "review_kind": "anomaly",
            "subject_type": "StageReceipt",
            "subject_id": "RECEIPT-RUN-34-1-001",
            "source_receipt_ids": ["RECEIPT-RUN-34-1-001"],
            "evidence_refs": [_evidence(), _evidence("artifact", "reports/summary.json")],
            "request_summary": "Review anomalous validate output.",
        }
    )

    assert request.lease_scope.value == "review"
    assert request.reviewer.value == "antigence"
    assert isinstance(request.evidence_refs[0], ReviewEvidenceRef)

    with pytest.raises(ValidationError, match="review lease"):
        ReviewRequest.model_validate(
            {
                "request_id": "REVIEW-34-2",
                "task_id": "TASK-34-2",
                "lease_id": "LEASE-34-2",
                "fencing_token": "token-34-2",
                "lease_scope": "execution",
                "reviewer": "antigence",
                "review_kind": "safety",
                "subject_type": "Artifact",
                "subject_id": "reports/summary.json",
                "source_receipt_ids": ["RECEIPT-RUN-34-2-001"],
                "evidence_refs": [_evidence()],
                "request_summary": "Execution state must not stand in for review authority.",
            }
        )


def test_review_request_rejects_non_antigence_owner() -> None:
    with pytest.raises(ValidationError, match="owned by antigence"):
        ReviewRequest.model_validate(
            {
                "request_id": "REVIEW-34-3",
                "task_id": "TASK-34-3",
                "lease_id": "LEASE-34-3",
                "fencing_token": "token-34-3",
                "lease_scope": "review",
                "reviewer": "watchtower",
                "review_kind": "contradiction",
                "subject_type": "Claim",
                "subject_id": "CLAIM-34-1",
                "source_receipt_ids": ["RECEIPT-RUN-34-3-001"],
                "evidence_refs": [_evidence()],
                "request_summary": "Watchtower must not become review authority.",
            }
        )


def test_review_verdict_is_structured_evidence_not_human_approval() -> None:
    verdict = ReviewVerdict.model_validate(
        {
            "verdict_id": "VERDICT-34-1",
            "task_id": "TASK-34-1",
            "lease_id": "LEASE-34-1",
            "fencing_token": "token-34-1",
            "reviewer": "antigence",
            "review_kind": "security",
            "subject_type": "Artifact",
            "subject_id": "results/RUN-34-1/output.json",
            "evidence_refs": [_evidence("artifact", "results/RUN-34-1/output.json")],
            "risk_class": "high",
            "decision": "block",
            "recommended_action": "require-human-review",
            "human_decision_required": True,
        }
    )

    assert verdict.reviewer.value == "antigence"
    assert verdict.human_decision_required is True

    with pytest.raises(ValidationError, match="escalated verdicts require escalation evidence"):
        ReviewVerdict.model_validate(
            {
                "verdict_id": "VERDICT-34-2",
                "task_id": "TASK-34-2",
                "lease_id": "LEASE-34-2",
                "fencing_token": "token-34-2",
                "reviewer": "antigence",
                "review_kind": "anomaly",
                "subject_type": "StageReceipt",
                "subject_id": "RECEIPT-RUN-34-2-001",
                "evidence_refs": [_evidence()],
                "risk_class": "critical",
                "decision": "escalate",
                "recommended_action": "escalate-with-evidence",
            }
        )


def test_review_verdict_rejects_human_promotion_or_truth_owner_drift() -> None:
    with pytest.raises(ValidationError):
        ReviewVerdict.model_validate(
            {
                "verdict_id": "VERDICT-34-3",
                "task_id": "TASK-34-3",
                "lease_id": "LEASE-34-3",
                "fencing_token": "token-34-3",
                "reviewer": "antigence",
                "review_kind": "safety",
                "subject_type": "Claim",
                "subject_id": "CLAIM-34-3",
                "evidence_refs": [_evidence()],
                "risk_class": "medium",
                "decision": "advisory",
                "recommended_action": "observe",
                "approval_kind": "operator-review-required",
            }
        )

    with pytest.raises(ValidationError):
        ReviewVerdict.model_validate(
            {
                "verdict_id": "VERDICT-34-4",
                "task_id": "TASK-34-4",
                "lease_id": "LEASE-34-4",
                "fencing_token": "token-34-4",
                "reviewer": "antigence",
                "review_kind": "contradiction",
                "subject_type": "Claim",
                "subject_id": "CLAIM-34-4",
                "evidence_refs": [_evidence()],
                "risk_class": "low",
                "decision": "pass",
                "recommended_action": "observe",
                "durable_truth_owner": "overwatch",
            }
        )
