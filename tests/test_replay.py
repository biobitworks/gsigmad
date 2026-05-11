"""Tests for replay identity, receipt diff, and divergence helpers."""
from __future__ import annotations

from pathlib import Path

import yaml

from gsigmad.governance.execution_contract import (
    BlockedClass,
    LaneName,
    ReceiptOutput,
    RetryPolicy,
    StageName,
    StageStatus,
)
from gsigmad.governance.receipts import write_stage_receipt
from gsigmad.governance.replay import (
    build_replay_identity,
    build_replay_escalation_bundle,
    diagnose_replay_divergence,
    diff_receipt_runs,
    write_replay_identity,
)


def _receipt_payload(run_id: str, stage: StageName, *, resume_point: str = "next") -> dict:
    return {
        "run_id": run_id,
        "stage": stage,
        "phase": "30",
        "wave": "1",
        "lane": LaneName.OLLARMA_DEFAULT,
        "required_inputs": ["inputs/config.yaml"],
        "immutable_inputs_hash": "sha256:abc123",
        "outputs": [ReceiptOutput(path="reports/out.json", kind="report")],
        "status": StageStatus.PASS,
        "blocked_class": None,
        "resume_point": resume_point,
        "retry_policy": RetryPolicy.BOUNDED_LOCAL,
        "escalation_trigger": None,
        "upstream_receipts": [],
    }


def test_replay_identity_writes_append_only_artifact(tmp_path: Path) -> None:
    identity = build_replay_identity(
        exp_id="EXP-1.1",
        baseline_results_id="RESULTS-EXP-1.1-1",
        replay_results_id="RESULTS-EXP-1.1-2",
        baseline_receipt_run_id="RUN-EXP-1.1-1",
        replay_receipt_run_id="RUN-EXP-1.1-2",
        baseline_manifest_path=".gsigmad/manifests/EXP-1.1/RESULTS-EXP-1.1-1.manifest.yaml",
        replay_manifest_path=".gsigmad/manifests/EXP-1.1/RESULTS-EXP-1.1-2.manifest.yaml",
    )

    relpath = write_replay_identity(tmp_path, identity)
    payload = yaml.safe_load((tmp_path / relpath).read_text(encoding="utf-8"))
    assert payload["baseline_results_id"] == "RESULTS-EXP-1.1-1"
    assert payload["replay_receipt_run_id"] == "RUN-EXP-1.1-2"


def test_diff_receipt_runs_reports_resume_point_changes(tmp_path: Path) -> None:
    write_stage_receipt(tmp_path, _receipt_payload("RUN-BASELINE", StageName.EXECUTE, resume_point="validate"))
    write_stage_receipt(tmp_path, _receipt_payload("RUN-CANDIDATE", StageName.EXECUTE, resume_point="summarize"))

    diff = diff_receipt_runs(tmp_path, baseline_run_id="RUN-BASELINE", candidate_run_id="RUN-CANDIDATE")

    assert any(reason["code"] == "RESUME_POINT_CHANGED" for reason in diff["reasons"])


def test_diagnose_replay_divergence_normalizes_resume_and_review_routes() -> None:
    resume = diagnose_replay_divergence([{"code": "RESUME_POINT_CHANGED"}])
    assert resume["reverification_status"] == "resume-available"
    assert resume["blocked_class"] == BlockedClass.RETRYABLE.value

    review = diagnose_replay_divergence([{"code": "IMMUTABLE_INPUT_DRIFT"}])
    assert review["reverification_status"] == "review-required"
    assert review["blocked_class"] == BlockedClass.NON_RETRYABLE.value


def test_build_replay_escalation_bundle_reuses_shared_boundary_bundle_surface() -> None:
    bundle = build_replay_escalation_bundle(
        replay_id="REPLAY-EXP-1.1-RESULTS-EXP-1.1-2",
        run_id="RUN-EXP-1.1-2",
        receipt_ids=["RECEIPT-RUN-EXP-1.1-2-004"],
        evidence_paths=[".gsigmad/replays/EXP-1.1/RESULTS-EXP-1.1-2.reverification.yaml"],
        diagnosis={"reverification_status": "escalate-now", "blocked_class": BlockedClass.ESCALATE_NOW.value},
    )

    assert bundle.lane.value == "frontier-only"
    assert bundle.frontier_packet is not None
    assert bundle.frontier_packet.reason.value == "blocked-run-diagnosis"
