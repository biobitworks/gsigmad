"""Tests for the Phase 32 control-plane contract."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from gsigmad.governance.control_plane_contract import (
    CONTROL_PLANE_DECISIONS,
    CONTROL_PLANE_GUARDRAILS,
    CANONICAL_EDGE_TYPES,
    CANONICAL_ENTITY_TYPES,
    DURABLE_RECEIPT_TYPES,
    OWNERSHIP_MATRIX,
    CanonicalEdgeType,
    CanonicalEntityType,
    ControlPlaneDecision,
    ControlPlaneOwner,
    DurableReceipt,
    DurableReceiptType,
    LeaseScope,
    LiveEvent,
    OwnershipSurface,
    RepoClass,
    TruthLayer,
    WorkLease,
    get_surface_owner,
    validate_control_plane_guardrails,
    validate_ownership_matrix,
    validate_work_lease_payload,
)


def test_contract_closes_entity_edge_and_receipt_sets() -> None:
    assert {item.value for item in CanonicalEntityType} == CANONICAL_ENTITY_TYPES
    assert {item.value for item in CanonicalEdgeType} == CANONICAL_EDGE_TYPES
    assert {item.value for item in DurableReceiptType} == DURABLE_RECEIPT_TYPES


def test_comparison_frame_is_closed() -> None:
    assert {item.value for item in ControlPlaneDecision} == CONTROL_PLANE_DECISIONS
    assert CONTROL_PLANE_DECISIONS == {"adopt", "adapt", "reject"}
    assert CONTROL_PLANE_GUARDRAILS == {
        "second-planner",
        "shadow-queue",
        "duplicate-ownership",
        "watchtower-writeback",
        "frozen-repo-mutation",
    }


def test_ownership_matrix_has_one_owner_per_surface_and_overwatch_truth() -> None:
    validated = validate_ownership_matrix(OWNERSHIP_MATRIX)

    assert len(validated) == len(OwnershipSurface)
    assert get_surface_owner(OwnershipSurface.PLANNING_ONTOLOGY) == ControlPlaneOwner.GSIGMAD
    assert get_surface_owner(OwnershipSurface.OPERATOR_VIEW) == ControlPlaneOwner.WATCHTOWER
    assert get_surface_owner(OwnershipSurface.SWARM_BROKER) == ControlPlaneOwner.OLLARMA
    assert get_surface_owner(OwnershipSurface.REVIEW_ESCALATION) == ControlPlaneOwner.ANTIGENCE
    assert get_surface_owner(OwnershipSurface.DURABLE_TRUTH) == ControlPlaneOwner.OVERWATCH


def test_live_event_and_durable_receipt_have_explicit_truth_layers() -> None:
    event = LiveEvent.model_validate(
        {
            "event_id": "evt-32-1",
            "event_type": "heartbeat",
            "owner": "watchtower",
            "subject_type": "Task",
            "subject_id": "TASK-32-1",
            "occurred_at": "2026-04-20T16:00:00Z",
        }
        )
    assert event.truth_layer is TruthLayer.LIVE

    receipt = DurableReceipt.model_validate(
        {
            "receipt_id": "receipt-32-1",
            "receipt_type": "StageReceipt",
            "portfolio_entity_id": "TASK-32-1",
            "owner": "gsigmad",
            "actor": "agent:codex",
            "subject_type": "Task",
            "subject_id": "TASK-32-1",
            "event_time": "2026-04-20T16:05:00Z",
            "status": "pass",
            "reason_code": "CANONICAL_RECEIPT",
            "idempotency_key": "plan-32-01-task-1",
            "parent_receipt_ids": [],
            "artifact_refs": ["reports/contract.json"],
            "content_hash": "sha256:abcdef123456",
        }
    )
    assert receipt.truth_layer is TruthLayer.DURABLE

    with pytest.raises(ValidationError, match="truth_layer"):
        LiveEvent.model_validate(
            {
                "truth_layer": "durable",
                "event_id": "evt-32-2",
                "event_type": "heartbeat",
                "owner": "watchtower",
                "subject_type": "Task",
                "subject_id": "TASK-32-2",
                "occurred_at": "2026-04-20T16:00:00Z",
            }
        )

    with pytest.raises(ValidationError, match="sha256"):
        DurableReceipt.model_validate(
            {
                "receipt_id": "receipt-32-2",
                "receipt_type": "ReviewVerdict",
                "portfolio_entity_id": "TASK-32-2",
                "owner": "antigence",
                "actor": "service:antigence",
                "subject_type": "Task",
                "subject_id": "TASK-32-2",
                "event_time": "2026-04-20T16:05:00Z",
                "status": "review_gated",
                "reason_code": "RISK_SIGNAL",
                "idempotency_key": "review-32-2",
                "parent_receipt_ids": [],
                "artifact_refs": [],
                "content_hash": "invalid",
            }
        )


def test_control_plane_guardrails_reject_phase_32_drift() -> None:
    with pytest.raises(ValueError, match="second planner"):
        validate_control_plane_guardrails({"planner": "airflow"})

    with pytest.raises(ValueError, match="shadow queue"):
        validate_control_plane_guardrails({"queue": "shadow"})

    with pytest.raises(ValueError, match="Watchtower writeback"):
        validate_control_plane_guardrails({"watchtower_writeback": True})

    with pytest.raises(ValueError, match="duplicate ownership"):
        validate_control_plane_guardrails({"duplicate_owner": True})


def test_work_lease_requires_expiry_after_acquisition() -> None:
    acquired = datetime.now(tz=timezone.utc)
    expires = acquired + timedelta(minutes=15)

    lease = WorkLease.model_validate(
        {
            "lease_id": "lease-32-1",
            "task_id": "TASK-32-1",
            "lease_scope": LeaseScope.EXECUTION,
            "holder_system": "ollarma",
            "holder_id": "lane-1",
            "fencing_token": "token-32-1",
            "acquired_at": acquired.isoformat(),
            "expires_at": expires.isoformat(),
            "heartbeat_at": acquired.isoformat(),
            "intent_summary": "execute bounded contract tests",
            "release_policy": "completed",
        }
    )

    assert lease.lease_scope is LeaseScope.EXECUTION

    with pytest.raises(ValueError, match="queue or duplicate ownership fields"):
        validate_work_lease_payload(
            {
                "lease_id": "lease-32-3",
                "queue": "shadow-queue",
            }
        )

    with pytest.raises(ValidationError, match="expires_at"):
        WorkLease.model_validate(
            {
                "lease_id": "lease-32-2",
                "task_id": "TASK-32-2",
                "lease_scope": LeaseScope.REVIEW,
                "holder_system": "antigence",
                "holder_id": "review-lane",
                "fencing_token": "token-32-2",
                "acquired_at": expires.isoformat(),
                "expires_at": acquired.isoformat(),
                "heartbeat_at": acquired.isoformat(),
                "intent_summary": "review claim",
                "release_policy": "completed",
            }
        )


def test_work_lease_rejects_duplicate_owner_fields() -> None:
    now = datetime.now(tz=timezone.utc)
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        WorkLease.model_validate(
            {
                "lease_id": "lease-32-4",
                "task_id": "TASK-32-4",
                "lease_scope": LeaseScope.AGENT,
                "holder_system": "watchtower",
                "holder_id": "agent-1",
                "fencing_token": "token-32-4",
                "acquired_at": now.isoformat(),
                "expires_at": (now + timedelta(minutes=10)).isoformat(),
                "heartbeat_at": now.isoformat(),
                "intent_summary": "claim task",
                "release_policy": "blocked",
                "owner": "watchtower",
            }
        )


def test_work_lease_rejects_implicit_queue_or_inbox_authority() -> None:
    with pytest.raises(ValueError, match="lease authority must not be expressed"):
        validate_work_lease_payload({"lease_id": "lease-33-1", "queue_position": 3})

    with pytest.raises(ValueError, match="lease authority must not be expressed"):
        validate_work_lease_payload({"lease_id": "lease-33-2", "inbox_rank": 1})

    with pytest.raises(ValueError, match="lease authority must not be expressed"):
        validate_work_lease_payload({"lease_id": "lease-33-3", "chat_claim": "THREAD-1"})


def test_repo_class_enum_is_closed() -> None:
    assert {item.value for item in RepoClass} == {"active", "legacy", "frozen"}
