"""Tests for the Phase 26 execution contract and receipt helpers."""
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from gsigmad.governance.execution_contract import (
    DEFAULT_EXECUTION_CONTRACT_VERSION,
    BlockedClass,
    LaneName,
    ReceiptOutput,
    RetryPolicy,
    STAGE_ORDER,
    StageName,
    StageReceipt,
    StageStatus,
    build_immutable_inputs_hash,
)
from gsigmad.governance.receipts import load_stage_receipt, write_stage_receipt


def _base_receipt_payload() -> dict:
    return {
        "run_id": "RUN-1.9.26.1",
        "stage": StageName.PREFLIGHT,
        "phase": "26",
        "wave": "1",
        "lane": LaneName.OLLARMA_DEFAULT,
        "required_inputs": ["adapters/runtime/shadow-seeds.yaml", "configs/run.yaml"],
        "immutable_inputs_hash": "sha256:abc123",
        "outputs": [
            ReceiptOutput(path="reports/preflight.json", kind="report"),
        ],
        "status": StageStatus.PASS,
        "blocked_class": None,
        "resume_point": "scaffold/materialize",
        "retry_policy": RetryPolicy.BOUNDED_LOCAL,
        "escalation_trigger": None,
        "upstream_receipts": [],
        "contract_version": DEFAULT_EXECUTION_CONTRACT_VERSION,
    }


def test_stage_receipt_exposes_fixed_stage_order() -> None:
    assert [stage.value for stage in STAGE_ORDER] == [
        "preflight",
        "scaffold/materialize",
        "execute",
        "validate",
        "summarize",
        "interpret/escalate",
    ]


@pytest.mark.parametrize(
    "field_name",
    [
        "lane",
        "immutable_inputs_hash",
        "outputs",
        "status",
        "resume_point",
        "retry_policy",
        "escalation_trigger",
        "upstream_receipts",
    ],
)
def test_stage_receipt_requires_canonical_fields(field_name: str) -> None:
    payload = _base_receipt_payload()
    payload.pop(field_name)

    with pytest.raises(ValidationError):
        StageReceipt.model_validate(payload)


def test_stage_receipt_blocked_class_rules() -> None:
    blocked_payload = _base_receipt_payload() | {
        "status": StageStatus.BLOCKED,
        "blocked_class": BlockedClass.RETRYABLE,
        "escalation_trigger": "missing-local-dependency",
    }
    blocked_receipt = StageReceipt.model_validate(blocked_payload)
    assert blocked_receipt.blocked_class == BlockedClass.RETRYABLE

    missing_blocked_class = blocked_payload.copy()
    missing_blocked_class["blocked_class"] = None
    with pytest.raises(ValidationError):
        StageReceipt.model_validate(missing_blocked_class)

    invalid_non_blocked = _base_receipt_payload() | {
        "blocked_class": BlockedClass.NON_RETRYABLE,
    }
    with pytest.raises(ValidationError):
        StageReceipt.model_validate(invalid_non_blocked)


def test_immutable_hash_payload_rejects_bulky_mutable_runtime_state() -> None:
    with pytest.raises(ValueError, match="bulky or mutable runtime field"):
        build_immutable_inputs_hash(
            {
                "contract_version": DEFAULT_EXECUTION_CONTRACT_VERSION,
                "runtime_state": {"chunk": 4, "workers": 2},
            }
        )


def test_immutable_hash_payload_rejects_runtime_host_control_fields() -> None:
    with pytest.raises(ValueError, match="runtime host control field"):
        build_immutable_inputs_hash(
            {
                "contract_version": DEFAULT_EXECUTION_CONTRACT_VERSION,
                "worker_routing": {"queue": "gpu-fleet"},
            }
        )


@pytest.mark.parametrize("field_name", ["worker_routing", "gpu_schedule", "frontier_execution_defaults"])
def test_stage_receipt_rejects_runtime_host_control_fields(field_name: str) -> None:
    payload = _base_receipt_payload() | {field_name: {"unexpected": True}}

    with pytest.raises(ValidationError):
        StageReceipt.model_validate(payload)


def test_receipt_helpers_append_and_reload(tmp_path: Path) -> None:
    first_payload = _base_receipt_payload()
    first = write_stage_receipt(tmp_path, first_payload)
    second = write_stage_receipt(
        tmp_path,
        _base_receipt_payload()
        | {
            "stage": StageName.EXECUTE,
            "outputs": [ReceiptOutput(path="results/RUN-1/raw.tsv", kind="results")],
            "resume_point": "validate",
            "upstream_receipts": [first["receipt_id"]],
        },
    )

    first_path = tmp_path / first["receipt_relpath"]
    second_path = tmp_path / second["receipt_relpath"]
    assert first_path.is_file()
    assert second_path.is_file()
    assert first["receipt_id"] != second["receipt_id"]
    assert first_path.name.startswith("001-")
    assert second_path.name.startswith("002-")

    loaded = load_stage_receipt(tmp_path, second["receipt_relpath"])
    assert loaded.stage == StageName.EXECUTE
    assert loaded.upstream_receipts == [first["receipt_id"]]
