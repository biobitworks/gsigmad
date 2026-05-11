"""Tests for the Phase 34 Watchtower operator surface contract."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from gsigmad.governance.operator_surface_contract import (
    ActivityRailItem,
    InboxItem,
    NextStepView,
    operator_view_is_advisory,
)


def _ref(ref_kind: str, ref_id: str) -> dict[str, str]:
    return {"ref_kind": ref_kind, "ref_id": ref_id}


def test_next_step_view_uses_canonical_refs_and_is_advisory_by_default() -> None:
    view = NextStepView.model_validate(
        {
            "next_step_id": "NEXT-34-1",
            "task_id": "TASK-34-1",
            "backing_refs": [
                _ref("task", "TASK-34-1"),
                _ref("lease", "LEASE-34-1"),
                _ref("blocker", "BLOCKER-34-1"),
            ],
            "route_hint": "ollarma-default",
            "intent_summary": "Render the next bounded execution step.",
        }
    )

    assert view.advisory is True
    assert operator_view_is_advisory(view) is True


def test_non_advisory_views_require_receipt_or_human_decision_backing() -> None:
    inbox = InboxItem.model_validate(
        {
            "inbox_item_id": "INBOX-34-1",
            "task_id": "TASK-34-1",
            "backing_refs": [
                _ref("task", "TASK-34-1"),
                _ref("receipt", "RECEIPT-RUN-34-1-001"),
            ],
            "rank": 1,
            "title": "Receipt-backed operator work",
            "advisory": False,
        }
    )

    assert inbox.advisory is False
    assert operator_view_is_advisory(inbox) is False

    with pytest.raises(ValidationError, match="receipt-backed or human-decision backing"):
        InboxItem.model_validate(
            {
                "inbox_item_id": "INBOX-34-2",
                "task_id": "TASK-34-2",
                "backing_refs": [
                    _ref("task", "TASK-34-2"),
                    _ref("lease", "LEASE-34-2"),
                ],
                "rank": 2,
                "title": "Lease-only view",
                "advisory": False,
            }
        )


def test_activity_rail_rejects_shadow_queue_and_writeback_drift() -> None:
    with pytest.raises(ValidationError, match="shadow queue"):
        ActivityRailItem.model_validate(
            {
                "activity_id": "ACT-34-1",
                "task_id": "TASK-34-1",
                "backing_refs": [_ref("task", "TASK-34-1")],
                "activity_kind": "progress",
                "summary": "Queue semantics must stay out of operator projections.",
                "queue": "shadow",
            }
        )

    with pytest.raises(ValidationError, match="Watchtower writeback"):
        ActivityRailItem.model_validate(
            {
                "activity_id": "ACT-34-2",
                "task_id": "TASK-34-2",
                "backing_refs": [_ref("task", "TASK-34-2")],
                "activity_kind": "approval",
                "summary": "Writeback must stay out of the operator surface.",
                "watchtower_writeback": True,
            }
        )


def test_operator_views_reject_duplicate_truth_owner_drift() -> None:
    with pytest.raises(ValidationError):
        NextStepView.model_validate(
            {
                "next_step_id": "NEXT-34-2",
                "task_id": "TASK-34-2",
                "backing_refs": [_ref("task", "TASK-34-2")],
                "route_hint": "ollarma-default",
                "intent_summary": "Truth-owner drift must not be accepted.",
                "durable_truth_owner": "overwatch",
            }
        )
