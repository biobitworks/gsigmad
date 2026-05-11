"""Tests for the Phase 31 human review gate helpers."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from gsigmad.governance.human_gates import (
    HumanGateKind,
    build_canon_override_gate,
    build_policy_exception_gate,
    build_promotion_gate,
)


def test_build_promotion_gate_marks_only_ratified_authority_approved() -> None:
    approved = build_promotion_gate("phase20-local-text-classifier-v1")
    advisory = build_promotion_gate("other-authority")

    assert approved.gate_kind == HumanGateKind.PROMOTION
    assert approved.approved is True
    assert advisory.approved is False


def test_canon_override_gate_requires_justification() -> None:
    with pytest.raises(ValidationError, match="justification"):
        build_canon_override_gate(subject="invariant-3", justification="")


def test_policy_exception_gate_requires_evidence_and_justification() -> None:
    gate = build_policy_exception_gate(
        subject="frontier-policy-exception",
        justification="Manual exception approved for audited incident triage.",
        evidence_paths=["reports/incident-review.md"],
    )

    assert gate.gate_kind == HumanGateKind.POLICY_EXCEPTION
    assert gate.evidence_paths == ["reports/incident-review.md"]
