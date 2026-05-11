"""Tests for the Phase 29 blocked-lifecycle and dead-letter helpers."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from gsigmad.governance.execution_contract import (
    BlockedClass,
    LaneName,
    ReceiptOutput,
    RetryPolicy,
    StageName,
    StageReceipt,
    StageStatus,
)
from gsigmad.governance.reliability import (
    BlockedLifecycleEvent,
    DeadLetterReceipt,
    build_dead_letter_receipt,
    write_blocked_lifecycle_event,
    write_dead_letter_receipt,
)


def _blocked_receipt(*, blocked_class: BlockedClass) -> StageReceipt:
    return StageReceipt.model_validate(
        {
            "run_id": "RUN-29-1",
            "stage": StageName.EXECUTE,
            "phase": "29",
            "wave": "1",
            "lane": LaneName.OLLARMA_DEFAULT,
            "required_inputs": ["inputs/run.yaml"],
            "immutable_inputs_hash": "sha256:abc123",
            "outputs": [ReceiptOutput(path="reports/execute.json", kind="report")],
            "status": StageStatus.BLOCKED,
            "blocked_class": blocked_class,
            "resume_point": "execute",
            "retry_policy": RetryPolicy.QUEUE_REPLAY,
            "escalation_trigger": "runtime-failure",
            "upstream_receipts": [],
            "receipt_id": "RECEIPT-RUN-29-1-001",
        }
    )


def test_blocked_lifecycle_event_requires_retry_route_for_retryable_class() -> None:
    event = BlockedLifecycleEvent.model_validate(
        {
            "event_id": "BLOCKED-RUN-29-1-001",
            "source_receipt_id": "RECEIPT-RUN-29-1-001",
            "run_id": "RUN-29-1",
            "phase": "29",
            "wave": "1",
            "stage": "execute",
            "blocked_class": "retryable",
            "route_action": "retry-wave",
            "event_kind": "retry-scheduled",
            "reason": "temporary connectivity loss",
        }
    )

    assert event.route_action == "retry-wave"

    with pytest.raises(ValidationError, match="retry-wave"):
        BlockedLifecycleEvent.model_validate(
            {
                "event_id": "BLOCKED-RUN-29-1-002",
                "source_receipt_id": "RECEIPT-RUN-29-1-001",
                "run_id": "RUN-29-1",
                "phase": "29",
                "wave": "1",
                "stage": "execute",
                "blocked_class": "retryable",
                "route_action": "require-human-review",
                "event_kind": "retry-scheduled",
                "reason": "temporary connectivity loss",
            }
        )


def test_build_dead_letter_receipt_preserves_blocked_class_and_receipt_link() -> None:
    dead_letter = build_dead_letter_receipt(
        _blocked_receipt(blocked_class=BlockedClass.NON_RETRYABLE),
        reason="schema validation failed",
        evidence_paths=[".agent/kg_queue_failed.jsonl"],
        queue_entry_id="queue-entry-1",
    )

    assert isinstance(dead_letter, DeadLetterReceipt)
    assert dead_letter.source_receipt_id == "RECEIPT-RUN-29-1-001"
    assert dead_letter.blocked_class == BlockedClass.NON_RETRYABLE
    assert dead_letter.route_action == "require-human-review"


def test_reliability_artifacts_write_append_only(tmp_path: Path) -> None:
    lifecycle_relpath = write_blocked_lifecycle_event(
        tmp_path,
        {
            "event_id": "BLOCKED-RUN-29-1-001",
            "source_receipt_id": "RECEIPT-RUN-29-1-001",
            "run_id": "RUN-29-1",
            "phase": "29",
            "wave": "1",
            "stage": "execute",
            "blocked_class": "escalate-now",
            "route_action": "frontier-handoff",
            "event_kind": "blocked",
            "reason": "scientific escalation required",
        },
    )
    dead_letter_relpath = write_dead_letter_receipt(
        tmp_path,
        build_dead_letter_receipt(
            _blocked_receipt(blocked_class=BlockedClass.ESCALATE_NOW),
            reason="manual escalation required",
            evidence_paths=["reports/escalation.json"],
        ),
    )

    lifecycle_path = tmp_path / lifecycle_relpath
    dead_letter_path = tmp_path / dead_letter_relpath
    assert lifecycle_path.is_file()
    assert dead_letter_path.is_file()

    lifecycle_payload = [yaml.safe_load(line) for line in lifecycle_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lifecycle_payload[0]["event_kind"] == "blocked"
    dead_letter_payload = yaml.safe_load(dead_letter_path.read_text(encoding="utf-8"))
    assert dead_letter_payload["blocked_class"] == "escalate-now"
