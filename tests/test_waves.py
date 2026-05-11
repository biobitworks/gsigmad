"""Tests for the Phase 27 wave schema and policy helpers."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from gsigmad.governance.execution_contract import (
    BlockedClass,
    LaneName,
    RetryPolicy,
    StageName,
    StageStatus,
)
from gsigmad.governance.waves import (
    WaveDecisionAction,
    WaveNode,
    WaveSpec,
    ownership_class_for_lane,
    evaluate_wave_decision,
    topological_wave_ids,
)


def _receipt_payload(stage: StageName, *, status: StageStatus = StageStatus.PASS, blocked_class: BlockedClass | None = None) -> dict:
    return {
        "run_id": "RUN-27-1",
        "stage": stage,
        "phase": "27",
        "wave": "1",
        "lane": LaneName.OLLARMA_DEFAULT,
        "required_inputs": ["inputs/config.yaml"],
        "immutable_inputs_hash": "sha256:abc123",
        "outputs": [{"path": "reports/out.json", "kind": "report"}],
        "status": status,
        "blocked_class": blocked_class,
        "resume_point": "next",
        "retry_policy": RetryPolicy.BOUNDED_LOCAL,
        "escalation_trigger": None,
        "upstream_receipts": [],
    }


def test_wave_spec_accepts_parallel_safe_dag() -> None:
    spec = WaveSpec.model_validate(
        {
            "phase": "27",
            "waves": [
                {
                    "wave_id": "w1",
                    "title": "Preflight",
                    "lane": "ollarma-default",
                    "deterministic": True,
                    "receipt_requirements": ["preflight"],
                },
                {
                    "wave_id": "w2",
                    "title": "Review",
                    "lane": "sidecar-parallel",
                    "deterministic": True,
                    "depends_on": ["w1"],
                    "receipt_requirements": ["validate"],
                },
                {
                    "wave_id": "w3",
                    "title": "Human signoff",
                    "lane": "human-review-required",
                    "deterministic": False,
                    "depends_on": ["w1"],
                    "receipt_requirements": ["summarize"],
                },
            ],
        }
    )

    assert topological_wave_ids(spec) == ["w1", "w2", "w3"]


def test_wave_spec_rejects_cycles() -> None:
    with pytest.raises(ValidationError, match="acyclic"):
        WaveSpec.model_validate(
            {
                "phase": "27",
                "waves": [
                    {
                        "wave_id": "w1",
                        "title": "A",
                        "lane": "ollarma-default",
                        "deterministic": True,
                        "depends_on": ["w2"],
                        "receipt_requirements": ["execute"],
                    },
                    {
                        "wave_id": "w2",
                        "title": "B",
                        "lane": "sidecar-parallel",
                        "deterministic": True,
                        "depends_on": ["w1"],
                        "receipt_requirements": ["validate"],
                    },
                ],
            }
        )


def test_wave_node_rejects_runtime_host_fields() -> None:
    with pytest.raises(ValidationError):
        WaveNode.model_validate(
            {
                "wave_id": "w1",
                "title": "Execute",
                "lane": "ollarma-default",
                "deterministic": True,
                "receipt_requirements": ["execute"],
                "worker_routing": {"queue": "gpu"},
            }
        )


def test_lane_ownership_is_derived_from_phase26_lane_vocab() -> None:
    assert ownership_class_for_lane(LaneName.OLLARMA_DEFAULT).value == "deterministic-execution"
    assert ownership_class_for_lane(LaneName.FRONTIER_ONLY).value == "probabilistic-reasoning"


def test_deterministic_wave_auto_advances_only_on_pass_receipts() -> None:
    wave = WaveNode.model_validate(
        {
            "wave_id": "w2",
            "title": "Validation",
            "lane": "sidecar-parallel",
            "deterministic": True,
            "depends_on": ["w1"],
            "receipt_requirements": ["execute", "validate"],
        }
    )

    hold = evaluate_wave_decision(
        wave,
        [_receipt_payload(StageName.EXECUTE, status=StageStatus.PASS)],
        completed_dependencies={"w1"},
    )
    assert hold.action == WaveDecisionAction.HOLD

    ready = evaluate_wave_decision(
        wave,
        [
            _receipt_payload(StageName.EXECUTE, status=StageStatus.PASS),
            _receipt_payload(StageName.VALIDATE, status=StageStatus.PASS),
        ],
        completed_dependencies={"w1"},
    )
    assert ready.action == WaveDecisionAction.AUTO_ADVANCE


@pytest.mark.parametrize(
    ("blocked_class", "expected_action"),
    [
        (BlockedClass.RETRYABLE, WaveDecisionAction.RETRY_WAVE),
        (BlockedClass.NON_RETRYABLE, WaveDecisionAction.REQUIRE_HUMAN_REVIEW),
        (BlockedClass.ESCALATE_NOW, WaveDecisionAction.FRONTIER_HANDOFF),
    ],
)
def test_blocked_waves_follow_normalized_escalation_matrix(
    blocked_class: BlockedClass,
    expected_action: WaveDecisionAction,
) -> None:
    wave = WaveNode.model_validate(
        {
            "wave_id": "w1",
            "title": "Execute",
            "lane": "ollarma-default",
            "deterministic": True,
            "receipt_requirements": ["execute"],
        }
    )

    decision = evaluate_wave_decision(
        wave,
        [_receipt_payload(StageName.EXECUTE, status=StageStatus.BLOCKED, blocked_class=blocked_class)],
        completed_dependencies=set(),
    )

    assert decision.action == expected_action
    assert decision.blocked_class == blocked_class


def test_frontier_and_human_lanes_require_explicit_handoff() -> None:
    frontier = WaveNode.model_validate(
        {
            "wave_id": "w3",
            "title": "Reasoning",
            "lane": "frontier-only",
            "deterministic": False,
            "receipt_requirements": ["interpret/escalate"],
        }
    )
    human = WaveNode.model_validate(
        {
            "wave_id": "w4",
            "title": "Operator approval",
            "lane": "human-review-required",
            "deterministic": False,
            "receipt_requirements": ["summarize"],
        }
    )

    frontier_decision = evaluate_wave_decision(frontier, [], completed_dependencies=set())
    human_decision = evaluate_wave_decision(human, [], completed_dependencies=set())

    assert frontier_decision.action == WaveDecisionAction.FRONTIER_HANDOFF
    assert human_decision.action == WaveDecisionAction.REQUIRE_HUMAN_REVIEW
