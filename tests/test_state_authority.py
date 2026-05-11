"""Tests for the Phase 33 state authority helpers."""
from __future__ import annotations

from gsigmad.governance.control_plane_contract import (
    DIRECT_DURABLE_DECISION_TYPES,
    DURABLE_RECEIPT_TYPES,
    ControlPlaneOwner,
    LeaseScope,
    LiveEventType,
)
from gsigmad.governance.execution_contract import (
    LaneName,
    ReceiptOutput,
    RetryPolicy,
    StageName,
    StageReceipt,
    StageStatus,
)
from gsigmad.governance.human_gates import HumanReviewGate, build_canon_override_gate
from gsigmad.governance.reliability import BlockedClass, build_dead_letter_receipt
from gsigmad.governance.replay import ReplayIdentity, ReverificationReceipt, build_replay_identity
from gsigmad.governance.state_authority import (
    PROMOTABLE_DURABLE_NAMES,
    ClaimAuthority,
    StateLayer,
    classify_artifact_path,
    classify_claim_authority,
    classify_live_event_type,
    is_advisory_intent,
    is_evidence_only_artifact,
    is_promotable_durable,
    lease_scope_authority,
    system_state_binding,
)


def _stage_receipt() -> StageReceipt:
    return StageReceipt.model_validate(
        {
            "run_id": "RUN-33-1",
            "stage": StageName.EXECUTE,
            "phase": "33",
            "wave": "1",
            "lane": LaneName.OLLARMA_DEFAULT,
            "required_inputs": ["inputs/contract.yaml"],
            "immutable_inputs_hash": "sha256:abc123",
            "outputs": [ReceiptOutput(path="reports/state.json", kind="report")],
            "status": StageStatus.PASS,
            "blocked_class": None,
            "resume_point": "validate",
            "retry_policy": RetryPolicy.BOUNDED_LOCAL,
            "escalation_trigger": None,
            "upstream_receipts": [],
            "receipt_id": "RECEIPT-RUN-33-1-001",
        }
    )


def _reverification_receipt() -> ReverificationReceipt:
    return ReverificationReceipt.model_validate(
        {
            "replay_id": "REPLAY-33-1",
            "exp_id": "EXP-33.1",
            "baseline_results_id": "RESULTS-1",
            "replay_results_id": "RESULTS-2",
            "manifest_diff_path": ".gsigmad/replays/EXP-33.1/manifest-diff.yaml",
            "receipt_diff_path": ".gsigmad/replays/EXP-33.1/receipt-diff.yaml",
            "reverification_status": "review-required",
            "blocked_class": "non-retryable",
            "reasons": [{"code": "IMMUTABLE_INPUT_DRIFT"}],
        }
    )


def test_state_authority_closes_runtime_local_evidence_and_promotable_layers() -> None:
    assert {item.value for item in StateLayer} == {
        "runtime-local-live",
        "repo-local-durable-evidence",
        "promotable-durable-fact",
    }

    assert classify_live_event_type(LiveEventType.HEARTBEAT) is StateLayer.RUNTIME_LOCAL_LIVE
    assert classify_live_event_type(LiveEventType.QUEUE_INTERNAL) is StateLayer.RUNTIME_LOCAL_LIVE
    assert classify_artifact_path(".gsigmad/manifests/EXP-1/RESULTS-1.manifest.yaml") is StateLayer.REPO_LOCAL_DURABLE_EVIDENCE
    assert classify_artifact_path(".gsigmad/replays/EXP-1/receipt-diff.yaml") is StateLayer.REPO_LOCAL_DURABLE_EVIDENCE
    assert classify_artifact_path(".gsigmad/queue/cursor.json") is StateLayer.REPO_LOCAL_DURABLE_EVIDENCE
    assert is_promotable_durable(_stage_receipt()) is True


def test_system_state_bindings_keep_overwatch_as_only_durable_truth_owner() -> None:
    overwatch = system_state_binding(ControlPlaneOwner.OVERWATCH)
    assert overwatch.state_layer is StateLayer.PROMOTABLE_DURABLE_FACT
    assert overwatch.durable_truth_owner is True

    for owner in (
        ControlPlaneOwner.WATCHTOWER,
        ControlPlaneOwner.OLLARMA,
        ControlPlaneOwner.ANTIGENCE,
    ):
        binding = system_state_binding(owner)
        assert binding.state_layer is StateLayer.RUNTIME_LOCAL_LIVE
        assert binding.bounded_live_state_only is True
        assert binding.durable_truth_owner is False


def test_promotion_boundary_allows_only_closed_durable_classes_and_promoted_claims() -> None:
    stage_receipt = _stage_receipt()
    dead_letter = build_dead_letter_receipt(
        _stage_receipt().model_copy(update={"status": StageStatus.BLOCKED, "blocked_class": BlockedClass.NON_RETRYABLE}),
        reason="terminal contract failure",
        evidence_paths=[".gsigmad/dead_letters/RUN-33-1/001-dead-letter.yaml"],
    )
    replay_identity = build_replay_identity(
        exp_id="EXP-33.1",
        baseline_results_id="RESULTS-1",
        replay_results_id="RESULTS-2",
        baseline_receipt_run_id="RUN-33-1",
        replay_receipt_run_id="RUN-33-2",
        baseline_manifest_path=".gsigmad/manifests/EXP-33.1/RESULTS-1.manifest.yaml",
        replay_manifest_path=".gsigmad/manifests/EXP-33.1/RESULTS-2.manifest.yaml",
    )

    assert is_promotable_durable(stage_receipt) is True
    assert is_promotable_durable(dead_letter) is True
    assert is_promotable_durable(replay_identity) is True
    assert is_promotable_durable(_reverification_receipt()) is True
    assert is_promotable_durable("HumanDecision") is True
    assert is_promotable_durable("Claim") is True
    assert PROMOTABLE_DURABLE_NAMES == set(DURABLE_RECEIPT_TYPES) | {"Claim"}


def test_evidence_only_artifacts_are_rejected_for_direct_promotion() -> None:
    evidence_paths = [
        ".gsigmad/manifests/EXP-1/RESULTS-1.manifest.yaml",
        ".gsigmad/replays/EXP-1/receipt-diff.yaml",
        ".gsigmad/queue/retry-journal.jsonl",
        ".gsigmad/queue/cursor.json",
        ".gsigmad/packets/raw-payload.json",
    ]
    for path in evidence_paths:
        assert is_evidence_only_artifact(path) is True
        assert is_promotable_durable(path) is False


def test_replay_reliability_and_human_gate_artifacts_are_classified_without_ontology_drift() -> None:
    replay_identity = build_replay_identity(
        exp_id="EXP-33.2",
        baseline_results_id="RESULTS-A",
        replay_results_id="RESULTS-B",
        baseline_receipt_run_id="RUN-A",
        replay_receipt_run_id="RUN-B",
        baseline_manifest_path=".gsigmad/manifests/EXP-33.2/RESULTS-A.manifest.yaml",
        replay_manifest_path=".gsigmad/manifests/EXP-33.2/RESULTS-B.manifest.yaml",
    )
    dead_letter = build_dead_letter_receipt(
        _stage_receipt().model_copy(update={"status": StageStatus.BLOCKED, "blocked_class": BlockedClass.ESCALATE_NOW}),
        reason="escalation required",
        evidence_paths=["reports/escalation.json"],
    )
    human_gate = build_canon_override_gate(subject="contract-boundary", justification="Audited override")

    assert isinstance(human_gate, HumanReviewGate)
    assert is_promotable_durable(replay_identity) is True
    assert is_promotable_durable(dead_letter) is True
    assert is_evidence_only_artifact(human_gate) is True
    assert DIRECT_DURABLE_DECISION_TYPES == {"HumanDecision"}


def test_lease_scope_authority_distinguishes_context_from_execution_review_and_operator_approval() -> None:
    chat = lease_scope_authority(LeaseScope.CHAT)
    agent = lease_scope_authority(LeaseScope.AGENT)
    execution = lease_scope_authority(LeaseScope.EXECUTION)
    review = lease_scope_authority(LeaseScope.REVIEW)
    approval = lease_scope_authority(LeaseScope.OPERATOR_APPROVAL)

    assert chat.reserves_context is True
    assert agent.reserves_context is True
    assert chat.may_execute is False and chat.may_promote_truth is False
    assert agent.may_review is False and agent.may_promote_truth is False
    assert execution.may_execute is True
    assert review.may_review is True
    assert approval.may_operator_approve is True
    assert approval.may_promote_truth is True


def test_operator_and_chat_intent_stay_advisory_except_for_human_decision() -> None:
    assert classify_claim_authority("watchtower-intent") is ClaimAuthority.ADVISORY
    assert classify_claim_authority("chat-message") is ClaimAuthority.ADVISORY
    assert is_advisory_intent("operator-note") is True
    assert is_advisory_intent("inbox-label") is True
    assert classify_claim_authority("watchtower-intent", backed_by_receipt=True) is ClaimAuthority.RECEIPT_BACKED
    assert classify_claim_authority("HumanDecision") is ClaimAuthority.DIRECT_DURABLE
    assert is_advisory_intent("HumanDecision") is False
