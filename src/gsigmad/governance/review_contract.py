"""Phase 34 Antigence review and escalation contract helpers."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gsigmad.governance.adapter_contracts import SidecarReviewKind
from gsigmad.governance.control_plane_contract import ControlPlaneOwner, LeaseScope


def _non_empty(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("value must be non-empty")
    return normalized


class ReviewRiskClass(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReviewDecision(str, Enum):
    PASS = "pass"
    ADVISORY = "advisory"
    BLOCK = "block"
    ESCALATE = "escalate"


class ReviewAction(str, Enum):
    OBSERVE = "observe"
    REMEDIATE = "remediate"
    REQUIRE_HUMAN_REVIEW = "require-human-review"
    ESCALATE_WITH_EVIDENCE = "escalate-with-evidence"


class ReviewEvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref_kind: str
    ref: str

    @field_validator("ref_kind", "ref")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        return _non_empty(value)


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    request_id: str
    task_id: str
    lease_id: str
    fencing_token: str
    lease_scope: LeaseScope = LeaseScope.REVIEW
    reviewer: ControlPlaneOwner = ControlPlaneOwner.ANTIGENCE
    review_kind: SidecarReviewKind
    subject_type: str
    subject_id: str
    source_receipt_ids: list[str] = Field(min_length=1)
    evidence_refs: list[ReviewEvidenceRef] = Field(min_length=1)
    request_summary: str
    escalation_bundle_id: str | None = None

    @field_validator(
        "request_id",
        "task_id",
        "lease_id",
        "fencing_token",
        "subject_type",
        "subject_id",
        "request_summary",
        "escalation_bundle_id",
    )
    @classmethod
    def _validate_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _non_empty(value)

    @field_validator("source_receipt_ids")
    @classmethod
    def _validate_receipt_ids(cls, value: list[str]) -> list[str]:
        return [_non_empty(item) for item in value]

    @model_validator(mode="after")
    def _validate_surface(self) -> "ReviewRequest":
        if self.lease_scope is not LeaseScope.REVIEW:
            raise ValueError("review requests require a review lease")
        if self.reviewer is not ControlPlaneOwner.ANTIGENCE:
            raise ValueError("review requests must be owned by antigence")
        return self


class ReviewVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    verdict_id: str
    task_id: str
    lease_id: str
    fencing_token: str
    reviewer: ControlPlaneOwner = ControlPlaneOwner.ANTIGENCE
    review_kind: SidecarReviewKind
    subject_type: str
    subject_id: str
    evidence_refs: list[ReviewEvidenceRef] = Field(min_length=1)
    risk_class: ReviewRiskClass
    decision: ReviewDecision
    recommended_action: ReviewAction
    escalation_bundle_id: str | None = None
    human_decision_required: bool = False

    @field_validator(
        "verdict_id",
        "task_id",
        "lease_id",
        "fencing_token",
        "subject_type",
        "subject_id",
        "escalation_bundle_id",
    )
    @classmethod
    def _validate_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _non_empty(value)

    @model_validator(mode="after")
    def _validate_surface(self) -> "ReviewVerdict":
        if self.reviewer is not ControlPlaneOwner.ANTIGENCE:
            raise ValueError("review verdicts must be owned by antigence")
        if self.decision is ReviewDecision.ESCALATE and not self.escalation_bundle_id:
            raise ValueError("escalated verdicts require escalation evidence")
        if self.recommended_action is ReviewAction.ESCALATE_WITH_EVIDENCE and not self.escalation_bundle_id:
            raise ValueError("escalation action requires escalation evidence")
        if self.human_decision_required and self.recommended_action not in {
            ReviewAction.REQUIRE_HUMAN_REVIEW,
            ReviewAction.ESCALATE_WITH_EVIDENCE,
        }:
            raise ValueError("human decision requirement must route through human review or escalation")
        return self
