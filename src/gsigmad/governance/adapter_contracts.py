"""Frozen adapter packet contracts for offload, sidecar review, and frontier escalation."""
from __future__ import annotations

from enum import Enum
from typing import Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gsigmad.governance.execution_contract import BlockedClass, LaneName, StageName


class CheckpointPolicy(str, Enum):
    NONE = "none"
    OPTIONAL = "optional"
    REQUIRED = "required"


class OffloadStatus(str, Enum):
    ACCEPTED = "accepted"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class SidecarReviewKind(str, Enum):
    ANOMALY = "anomaly"
    CONTRADICTION = "contradiction"
    SECURITY = "security"
    SAFETY = "safety"


class HumanApprovalKind(str, Enum):
    COUNTERSIGN_REQUIRED = "countersign-required"
    OPERATOR_REVIEW_REQUIRED = "operator-review-required"


class EscalationReason(str, Enum):
    ANOMALY_REVIEW = "anomaly-review"
    CONTRADICTION_RESOLUTION = "contradiction-resolution"
    BLOCKED_RUN_DIAGNOSIS = "blocked-run-diagnosis"
    REPLAN_NEEDED = "replan-needed"
    SCIENTIFIC_INTERPRETATION = "scientific-interpretation"


class OffloadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    run_id: str
    wave_id: str
    stage: StageName
    lane: LaneName
    command: str
    immutable_input_paths: list[str] = Field(min_length=1)
    expected_output_roots: list[str] = Field(min_length=1)
    max_attempts: int = Field(default=1, ge=1, le=3)
    checkpoint_policy: CheckpointPolicy = CheckpointPolicy.REQUIRED

    @field_validator("request_id", "run_id", "wave_id", "command")
    @classmethod
    def _validate_non_empty(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must be non-empty")
        return normalized

    @field_validator("immutable_input_paths", "expected_output_roots")
    @classmethod
    def _validate_paths(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item for item in normalized):
            raise ValueError("paths must be non-empty")
        return normalized

    @model_validator(mode="after")
    def _validate_boundary(self) -> "OffloadRequest":
        if self.lane != LaneName.OLLARMA_DEFAULT:
            raise ValueError("offload requests must use the ollarma-default lane")
        if self.stage == StageName.INTERPRET_ESCALATE:
            raise ValueError("interpret/escalate is outside bounded offload")
        return self


class OffloadReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    run_id: str
    wave_id: str
    lane: LaneName
    status: OffloadStatus
    receipt_paths: list[str] = Field(default_factory=list)
    checkpoint_paths: list[str] = Field(default_factory=list)
    blocked_class: Optional[BlockedClass] = None

    @model_validator(mode="after")
    def _validate_surface(self) -> "OffloadReceipt":
        if self.lane != LaneName.OLLARMA_DEFAULT:
            raise ValueError("offload receipts must use the ollarma-default lane")
        if self.status == OffloadStatus.BLOCKED and self.blocked_class is None:
            raise ValueError("blocked_class is required for blocked offload receipts")
        if self.status != OffloadStatus.BLOCKED and self.blocked_class is not None:
            raise ValueError("blocked_class is only allowed for blocked offload receipts")
        if self.status in {OffloadStatus.COMPLETED, OffloadStatus.BLOCKED} and not (
            self.receipt_paths or self.checkpoint_paths
        ):
            raise ValueError("completed or blocked offload receipts must return receipt or checkpoint paths")
        return self


class SidecarReviewBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bundle_id: str
    run_id: str
    wave_id: str
    lane: LaneName
    source_stage: StageName
    review_kind: SidecarReviewKind
    receipt_ids: list[str] = Field(min_length=1)
    artifact_paths: list[str] = Field(min_length=1)
    summary_path: Optional[str] = None

    @model_validator(mode="after")
    def _validate_surface(self) -> "SidecarReviewBundle":
        if self.lane != LaneName.SIDECAR_PARALLEL:
            raise ValueError("sidecar review bundles must use the sidecar-parallel lane")
        if self.source_stage not in {StageName.VALIDATE, StageName.SUMMARIZE}:
            raise ValueError("sidecar review bundles are limited to validate or summarize surfaces")
        return self


class FrontierEscalationPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    packet_id: str
    run_id: str
    wave_id: str
    lane: LaneName
    source_stage: StageName
    reason: EscalationReason
    receipt_ids: list[str] = Field(min_length=1)
    evidence_paths: list[str] = Field(min_length=1)
    request_summary: str
    approval_lane: LaneName = LaneName.HUMAN_REVIEW_REQUIRED
    approval_kind: HumanApprovalKind = HumanApprovalKind.OPERATOR_REVIEW_REQUIRED

    @field_validator("packet_id", "run_id", "wave_id", "request_summary")
    @classmethod
    def _validate_non_empty(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must be non-empty")
        return normalized

    @model_validator(mode="after")
    def _validate_surface(self) -> "FrontierEscalationPacket":
        if self.lane != LaneName.FRONTIER_ONLY:
            raise ValueError("frontier escalation packets must use the frontier-only lane")
        if self.source_stage not in {StageName.SUMMARIZE, StageName.INTERPRET_ESCALATE}:
            raise ValueError("frontier escalation packets must originate from summarize or interpret/escalate")
        if self.approval_lane != LaneName.HUMAN_REVIEW_REQUIRED:
            raise ValueError("frontier escalation packets must route to human-review-required approval")
        return self
