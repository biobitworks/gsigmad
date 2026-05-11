"""Tests for the Phase 35 Overwatch truth-ingestion contract."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from gsigmad.governance.control_plane_contract import ControlPlaneOwner, LiveEventType
from gsigmad.governance.overwatch_truth_contract import (
    KGIngestionReceiptContract,
    GraphProjectionRef,
    TruthProjectionCandidate,
    TruthSubjectClass,
    is_ingestible_truth_subject,
    validate_truth_projection_payload,
)


def _graph_projection() -> GraphProjectionRef:
    return GraphProjectionRef.model_validate(
        {
            "projection_kind": "claim-node",
            "canonical_type": "Claim",
            "canonical_id": "CLAIM-35-1",
            "artifact_ref": "reports/kg/CLAIM-35-1.json",
        }
    )


def test_truth_projection_accepts_closed_durable_classes_and_promoted_claims() -> None:
    receipt_candidate = TruthProjectionCandidate.model_validate(
        {
            "candidate_id": "candidate-35-1",
            "source_owner": "gsigmad",
            "source_repo_class": "active",
            "subject_class": "durable-receipt",
            "promoted_type": "StageReceipt",
            "promoted_id": "RECEIPT-35-1",
            "source_ref": ".gsigmad/receipts/RUN-35-1/001-execute.yaml",
            "graph_projection_refs": [_graph_projection().model_dump(mode="json")],
        }
    )
    claim_candidate = TruthProjectionCandidate.model_validate(
        {
            "candidate_id": "candidate-35-2",
            "source_owner": "gsigmad",
            "source_repo_class": "legacy",
            "subject_class": "promoted-claim",
            "promoted_type": "Claim",
            "promoted_id": "CLAIM-35-2",
            "source_ref": "reports/claims/CLAIM-35-2.json",
            "graph_projection_refs": [_graph_projection().model_dump(mode="json")],
        }
    )
    decision_candidate = TruthProjectionCandidate.model_validate(
        {
            "candidate_id": "candidate-35-3",
            "source_owner": "human",
            "source_repo_class": "active",
            "subject_class": "direct-durable",
            "promoted_type": "HumanDecision",
            "promoted_id": "DECISION-35-3",
            "source_ref": "reports/approvals/DECISION-35-3.json",
            "graph_projection_refs": [_graph_projection().model_dump(mode="json")],
        }
    )

    assert receipt_candidate.promoted_type == "StageReceipt"
    assert claim_candidate.promoted_type == "Claim"
    assert decision_candidate.promoted_type == "HumanDecision"
    assert is_ingestible_truth_subject("StageReceipt") is True
    assert is_ingestible_truth_subject("Claim") is True
    assert is_ingestible_truth_subject("HumanDecision") is True


def test_truth_projection_rejects_live_and_evidence_only_subjects() -> None:
    assert is_ingestible_truth_subject(LiveEventType.HEARTBEAT) is False
    assert is_ingestible_truth_subject(".gsigmad/queue/cursor.json") is False
    assert is_ingestible_truth_subject(".gsigmad/packets/raw-payload.json") is False

    with pytest.raises(ValidationError, match="evidence-only"):
        TruthProjectionCandidate.model_validate(
            {
                "candidate_id": "candidate-35-4",
                "source_owner": "gsigmad",
                "source_repo_class": "active",
                "subject_class": "durable-receipt",
                "promoted_type": "StageReceipt",
                "promoted_id": "RECEIPT-35-4",
                "source_ref": ".gsigmad/queue/cursor.json",
                "graph_projection_refs": [_graph_projection().model_dump(mode="json")],
            }
        )

    with pytest.raises(ValidationError, match="Watchtower projections cannot originate"):
        TruthProjectionCandidate.model_validate(
            {
                "candidate_id": "candidate-35-5",
                "source_owner": "watchtower",
                "source_repo_class": "active",
                "subject_class": "durable-receipt",
                "promoted_type": "StageReceipt",
                "promoted_id": "RECEIPT-35-5",
                "source_ref": ".gsigmad/receipts/RUN-35-5/001.yaml",
                "graph_projection_refs": [_graph_projection().model_dump(mode="json")],
            }
        )


def test_kg_ingestion_receipt_requires_overwatch_owner_and_graph_projection_refs() -> None:
    receipt = KGIngestionReceiptContract.model_validate(
        {
            "receipt_id": "kg-35-1",
            "owner": "overwatch",
            "source_owner": "antigence",
            "source_repo_class": "legacy",
            "candidate_id": "candidate-35-6",
            "promoted_type": "ReviewVerdict",
            "promoted_id": "VERDICT-35-6",
            "ingested_at": datetime.now(tz=timezone.utc).isoformat(),
            "idempotency_key": "kg-35-1",
            "source_artifact_refs": ["reports/review/VERDICT-35-6.json"],
            "graph_projection_refs": [_graph_projection().model_dump(mode="json")],
        }
    )

    assert receipt.owner is ControlPlaneOwner.OVERWATCH
    assert receipt.graph_projection_refs[0].canonical_id == "CLAIM-35-1"

    with pytest.raises(ValidationError, match="Overwatch must own KG ingestion receipts"):
        KGIngestionReceiptContract.model_validate(
            {
                "receipt_id": "kg-35-2",
                "owner": "watchtower",
                "source_owner": "gsigmad",
                "source_repo_class": "active",
                "candidate_id": "candidate-35-7",
                "promoted_type": "StageReceipt",
                "promoted_id": "RECEIPT-35-7",
                "ingested_at": datetime.now(tz=timezone.utc).isoformat(),
                "idempotency_key": "kg-35-2",
                "source_artifact_refs": ["reports/receipts/RECEIPT-35-7.json"],
                "graph_projection_refs": [_graph_projection().model_dump(mode="json")],
            }
        )


def test_truth_projection_payload_rejects_second_planner_shadow_queue_and_evidence_only_refs() -> None:
    normalized = validate_truth_projection_payload(
        {
            "owner": "overwatch",
            "queue": "none",
            "planner": "gsigmad",
        }
    )
    assert normalized["owner"] == "overwatch"

    with pytest.raises(ValueError, match="second planner"):
        validate_truth_projection_payload({"planner": "airflow"})

    with pytest.raises(ValueError, match="shadow queue"):
        validate_truth_projection_payload({"queue": "shadow"})

    with pytest.raises(ValueError, match="evidence-only"):
        validate_truth_projection_payload({"source_ref": ".gsigmad/queue/cursor.json"})
