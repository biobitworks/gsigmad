"""Tests for the Phase 28 adapter packet contracts."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from gsigmad.governance.adapter_contracts import (
    FrontierEscalationPacket,
    OffloadReceipt,
    OffloadRequest,
    SidecarReviewBundle,
)


def test_offload_request_accepts_bounded_ollarma_contract() -> None:
    request = OffloadRequest.model_validate(
        {
            "request_id": "OFFLOAD-1",
            "run_id": "RUN-1",
            "wave_id": "w1",
            "stage": "execute",
            "lane": "ollarma-default",
            "command": "python scripts/run_chunk.py",
            "immutable_input_paths": ["scripts/run_chunk.py", "configs/run.yaml"],
            "expected_output_roots": ["results/RUN-1"],
            "max_attempts": 2,
            "checkpoint_policy": "required",
        }
    )

    assert request.lane.value == "ollarma-default"


def test_offload_request_rejects_non_ollarma_or_interpret_stage() -> None:
    with pytest.raises(ValidationError, match="ollarma-default lane"):
        OffloadRequest.model_validate(
            {
                "request_id": "OFFLOAD-1",
                "run_id": "RUN-1",
                "wave_id": "w1",
                "stage": "execute",
                "lane": "frontier-only",
                "command": "python scripts/run_chunk.py",
                "immutable_input_paths": ["scripts/run_chunk.py"],
                "expected_output_roots": ["results/RUN-1"],
            }
        )

    with pytest.raises(ValidationError, match="outside bounded offload"):
        OffloadRequest.model_validate(
            {
                "request_id": "OFFLOAD-1",
                "run_id": "RUN-1",
                "wave_id": "w1",
                "stage": "interpret/escalate",
                "lane": "ollarma-default",
                "command": "python scripts/run_chunk.py",
                "immutable_input_paths": ["scripts/run_chunk.py"],
                "expected_output_roots": ["results/RUN-1"],
            }
        )


def test_offload_receipt_requires_receipts_or_checkpoints_for_terminal_states() -> None:
    receipt = OffloadReceipt.model_validate(
        {
            "request_id": "OFFLOAD-1",
            "run_id": "RUN-1",
            "wave_id": "w1",
            "lane": "ollarma-default",
            "status": "completed",
            "receipt_paths": [".gsigmad/receipts/RUN-1/001-execute.yaml"],
        }
    )
    assert receipt.status.value == "completed"

    with pytest.raises(ValidationError, match="receipt or checkpoint paths"):
        OffloadReceipt.model_validate(
            {
                "request_id": "OFFLOAD-1",
                "run_id": "RUN-1",
                "wave_id": "w1",
                "lane": "ollarma-default",
                "status": "completed",
            }
        )


def test_sidecar_review_bundle_is_limited_to_validate_or_summarize_surfaces() -> None:
    bundle = SidecarReviewBundle.model_validate(
        {
            "bundle_id": "SIDECAR-1",
            "run_id": "RUN-1",
            "wave_id": "w2",
            "lane": "sidecar-parallel",
            "source_stage": "validate",
            "review_kind": "anomaly",
            "receipt_ids": ["RECEIPT-RUN-1-001"],
            "artifact_paths": ["reports/validate.json"],
        }
    )
    assert bundle.review_kind.value == "anomaly"

    with pytest.raises(ValidationError, match="validate or summarize"):
        SidecarReviewBundle.model_validate(
            {
                "bundle_id": "SIDECAR-1",
                "run_id": "RUN-1",
                "wave_id": "w2",
                "lane": "sidecar-parallel",
                "source_stage": "execute",
                "review_kind": "safety",
                "receipt_ids": ["RECEIPT-RUN-1-001"],
                "artifact_paths": ["reports/validate.json"],
            }
        )


def test_frontier_escalation_packet_requires_frontier_lane_and_human_approval() -> None:
    packet = FrontierEscalationPacket.model_validate(
        {
            "packet_id": "ESC-1",
            "run_id": "RUN-1",
            "wave_id": "w3",
            "lane": "frontier-only",
            "source_stage": "interpret/escalate",
            "reason": "scientific-interpretation",
            "receipt_ids": ["RECEIPT-RUN-1-004"],
            "evidence_paths": ["reports/summary.json", "reports/anomaly.json"],
            "request_summary": "Interpret contradictory summary evidence.",
            "approval_lane": "human-review-required",
            "approval_kind": "countersign-required",
        }
    )
    assert packet.approval_lane.value == "human-review-required"

    with pytest.raises(ValidationError, match="frontier-only lane"):
        FrontierEscalationPacket.model_validate(
            {
                "packet_id": "ESC-1",
                "run_id": "RUN-1",
                "wave_id": "w3",
                "lane": "ollarma-default",
                "source_stage": "interpret/escalate",
                "reason": "scientific-interpretation",
                "receipt_ids": ["RECEIPT-RUN-1-004"],
                "evidence_paths": ["reports/summary.json"],
                "request_summary": "Interpret contradictory summary evidence.",
            }
        )


@pytest.mark.parametrize(
    ("model_cls", "payload"),
    [
        (
            OffloadRequest,
            {
                "request_id": "OFFLOAD-1",
                "run_id": "RUN-1",
                "wave_id": "w1",
                "stage": "execute",
                "lane": "ollarma-default",
                "command": "python scripts/run_chunk.py",
                "immutable_input_paths": ["scripts/run_chunk.py"],
                "expected_output_roots": ["results/RUN-1"],
                "worker_routing": {"queue": "gpu"},
            },
        ),
        (
            SidecarReviewBundle,
            {
                "bundle_id": "SIDECAR-1",
                "run_id": "RUN-1",
                "wave_id": "w2",
                "lane": "sidecar-parallel",
                "source_stage": "validate",
                "review_kind": "anomaly",
                "receipt_ids": ["RECEIPT-RUN-1-001"],
                "artifact_paths": ["reports/validate.json"],
                "gpu_schedule": {"profile": "a100"},
            },
        ),
        (
            FrontierEscalationPacket,
            {
                "packet_id": "ESC-1",
                "run_id": "RUN-1",
                "wave_id": "w3",
                "lane": "frontier-only",
                "source_stage": "interpret/escalate",
                "reason": "scientific-interpretation",
                "receipt_ids": ["RECEIPT-RUN-1-004"],
                "evidence_paths": ["reports/summary.json"],
                "request_summary": "Interpret contradictory summary evidence.",
                "frontier_execution_defaults": {"model": "gpt-frontier"},
            },
        ),
    ],
)
def test_adapter_packets_reject_runtime_host_control_fields(model_cls, payload: dict) -> None:
    with pytest.raises(ValidationError):
        model_cls.model_validate(payload)
