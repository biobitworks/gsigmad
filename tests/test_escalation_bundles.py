"""Tests for the Phase 31 escalation bundle contracts."""
from __future__ import annotations

from gsigmad.governance.escalation_bundles import (
    build_blocked_diagnosis_bundle,
    build_interpretation_bundle,
)
from gsigmad.governance.execution_contract import BlockedClass, LaneName, StageName


def test_interpretation_bundle_wraps_frontier_packet_with_human_approval() -> None:
    bundle = build_interpretation_bundle(
        run_id="RUN-31-1",
        wave_id="w3",
        source_stage=StageName.INTERPRET_ESCALATE,
        receipt_ids=["RECEIPT-RUN-31-1-004"],
        evidence_paths=["reports/summary.json"],
        request_summary="Interpret the summary findings.",
    )

    assert bundle.lane == LaneName.FRONTIER_ONLY
    assert bundle.frontier_packet is not None
    assert bundle.frontier_packet.reason.value == "scientific-interpretation"
    assert bundle.approval_lane == LaneName.HUMAN_REVIEW_REQUIRED


def test_blocked_diagnosis_bundle_routes_non_retryable_work_to_human_review() -> None:
    bundle = build_blocked_diagnosis_bundle(
        run_id="RUN-31-2",
        wave_id="w4",
        source_stage=StageName.SUMMARIZE,
        receipt_ids=["RECEIPT-RUN-31-2-005"],
        evidence_paths=["reports/replay-diff.yaml"],
        request_summary="Review non-retryable blocked replay output.",
        blocked_class=BlockedClass.NON_RETRYABLE,
        reverification_status="review-required",
    )

    assert bundle.lane == LaneName.HUMAN_REVIEW_REQUIRED
    assert bundle.frontier_packet is None
    assert bundle.blocked_class == BlockedClass.NON_RETRYABLE


def test_blocked_diagnosis_bundle_escalates_now_when_frontier_reasoning_is_required() -> None:
    bundle = build_blocked_diagnosis_bundle(
        run_id="RUN-31-3",
        wave_id="w5",
        source_stage=StageName.SUMMARIZE,
        receipt_ids=["RECEIPT-RUN-31-3-005"],
        evidence_paths=["reports/replay-diff.yaml"],
        request_summary="Escalate blocked replay for frontier diagnosis.",
        blocked_class=BlockedClass.ESCALATE_NOW,
        reverification_status="escalate-now",
    )

    assert bundle.lane == LaneName.FRONTIER_ONLY
    assert bundle.frontier_packet is not None
    assert bundle.frontier_packet.reason.value == "blocked-run-diagnosis"
