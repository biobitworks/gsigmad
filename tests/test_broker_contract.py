"""Tests for the Phase 34 Ollarma broker contract."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from gsigmad.governance.broker_contract import (
    LaneRunReceipt,
    SwarmRunReceipt,
    SwarmRunRequest,
)


def test_swarm_run_request_requires_execution_lease_and_bounded_lanes() -> None:
    request = SwarmRunRequest.model_validate(
        {
            "task_id": "TASK-34-1",
            "lease_id": "LEASE-34-1",
            "fencing_token": "token-34-1",
            "lease_scope": "execution",
            "broker": "ollarma",
            "source_stage": "execute",
            "allowed_lanes": ["ollarma-default", "sidecar-parallel"],
            "request_summary": "Run bounded execution work under the canonical lease.",
            "immutable_input_paths": ["scripts/run.py", "configs/run.yaml"],
            "expected_output_roots": ["results/RUN-34-1"],
        }
    )

    assert request.lease_scope.value == "execution"
    assert request.broker.value == "ollarma"

    with pytest.raises(ValidationError, match="execution lease"):
        SwarmRunRequest.model_validate(
            {
                "task_id": "TASK-34-1",
                "lease_id": "LEASE-34-1",
                "fencing_token": "token-34-1",
                "lease_scope": "chat",
                "broker": "ollarma",
                "source_stage": "execute",
                "allowed_lanes": ["ollarma-default"],
                "request_summary": "Chat state must not authorize execution.",
                "immutable_input_paths": ["scripts/run.py"],
                "expected_output_roots": ["results/RUN-34-1"],
            }
        )

    with pytest.raises(ValidationError, match="bounded execution lanes"):
        SwarmRunRequest.model_validate(
            {
                "task_id": "TASK-34-1",
                "lease_id": "LEASE-34-1",
                "fencing_token": "token-34-1",
                "lease_scope": "execution",
                "broker": "ollarma",
                "source_stage": "execute",
                "allowed_lanes": ["human-review-required"],
                "request_summary": "Human approval is not a broker lane.",
                "immutable_input_paths": ["scripts/run.py"],
                "expected_output_roots": ["results/RUN-34-1"],
            }
        )


def test_swarm_run_request_rejects_non_ollarma_or_interpret_stage() -> None:
    with pytest.raises(ValidationError, match="owned by ollarma"):
        SwarmRunRequest.model_validate(
            {
                "task_id": "TASK-34-2",
                "lease_id": "LEASE-34-2",
                "fencing_token": "token-34-2",
                "lease_scope": "execution",
                "broker": "watchtower",
                "source_stage": "execute",
                "allowed_lanes": ["ollarma-default"],
                "request_summary": "Watchtower must not become the broker.",
                "immutable_input_paths": ["scripts/run.py"],
                "expected_output_roots": ["results/RUN-34-2"],
            }
        )

    with pytest.raises(ValidationError, match="outside the bounded broker contract"):
        SwarmRunRequest.model_validate(
            {
                "task_id": "TASK-34-2",
                "lease_id": "LEASE-34-2",
                "fencing_token": "token-34-2",
                "lease_scope": "execution",
                "broker": "ollarma",
                "source_stage": "interpret/escalate",
                "allowed_lanes": ["ollarma-default"],
                "request_summary": "Interpretation is outside bounded execution.",
                "immutable_input_paths": ["scripts/run.py"],
                "expected_output_roots": ["results/RUN-34-2"],
            }
        )


def test_swarm_run_receipt_requires_terminal_execution_evidence() -> None:
    receipt = SwarmRunReceipt.model_validate(
        {
            "swarm_run_id": "SWARM-34-1",
            "task_id": "TASK-34-1",
            "lease_id": "LEASE-34-1",
            "fencing_token": "token-34-1",
            "broker": "ollarma",
            "status": "completed",
            "lane_receipt_ids": ["LANE-34-1"],
            "receipt_paths": [".gsigmad/receipts/RUN-34-1/001-execute.yaml"],
        }
    )

    assert receipt.status.value == "completed"

    with pytest.raises(ValidationError, match="blocked_class is required"):
        SwarmRunReceipt.model_validate(
            {
                "swarm_run_id": "SWARM-34-2",
                "task_id": "TASK-34-2",
                "lease_id": "LEASE-34-2",
                "fencing_token": "token-34-2",
                "broker": "ollarma",
                "status": "blocked",
                "receipt_paths": [".gsigmad/receipts/RUN-34-2/001-execute.yaml"],
            }
        )

    with pytest.raises(ValidationError, match="terminal swarm broker receipts"):
        SwarmRunReceipt.model_validate(
            {
                "swarm_run_id": "SWARM-34-3",
                "task_id": "TASK-34-3",
                "lease_id": "LEASE-34-3",
                "fencing_token": "token-34-3",
                "broker": "ollarma",
                "status": "escalated",
            }
        )


def test_lane_run_receipt_is_execution_evidence_not_planning_or_truth() -> None:
    receipt = LaneRunReceipt.model_validate(
        {
            "lane_run_id": "LANE-34-1",
            "swarm_run_id": "SWARM-34-1",
            "lane": "ollarma-default",
            "executor": "qwen-local",
            "stage": "execute",
            "status": "completed",
            "artifact_paths": ["results/RUN-34-1/output.json"],
        }
    )

    assert receipt.lane.value == "ollarma-default"

    with pytest.raises(ValidationError, match="bounded execution lanes"):
        LaneRunReceipt.model_validate(
            {
                "lane_run_id": "LANE-34-2",
                "swarm_run_id": "SWARM-34-2",
                "lane": "human-review-required",
                "executor": "operator",
                "stage": "execute",
                "status": "completed",
                "artifact_paths": ["results/RUN-34-2/output.json"],
            }
        )

    with pytest.raises(ValidationError):
        LaneRunReceipt.model_validate(
            {
                "lane_run_id": "LANE-34-3",
                "swarm_run_id": "SWARM-34-3",
                "lane": "ollarma-default",
                "executor": "qwen-local",
                "stage": "execute",
                "status": "completed",
                "artifact_paths": ["results/RUN-34-3/output.json"],
                "planner": "gsigmad",
            }
        )

    with pytest.raises(ValidationError):
        LaneRunReceipt.model_validate(
            {
                "lane_run_id": "LANE-34-4",
                "swarm_run_id": "SWARM-34-4",
                "lane": "sidecar-parallel",
                "executor": "antigence-sidecar",
                "stage": "validate",
                "status": "completed",
                "artifact_paths": ["results/RUN-34-4/output.json"],
                "durable_truth_owner": "overwatch",
            }
        )
