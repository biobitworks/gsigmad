"""Phase 34 Ollarma broker and lane contract helpers."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gsigmad.governance.control_plane_contract import ControlPlaneOwner, LeaseScope
from gsigmad.governance.execution_contract import BlockedClass, LaneName, StageName

_BROKER_LANES = {
    LaneName.OLLARMA_DEFAULT,
    LaneName.SIDECAR_PARALLEL,
}


def _non_empty(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("value must be non-empty")
    return normalized


class SwarmRunStatus(str, Enum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    ESCALATED = "escalated"


class LaneRunStatus(str, Enum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    ESCALATED = "escalated"


class SwarmRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    task_id: str
    lease_id: str
    fencing_token: str
    lease_scope: LeaseScope = LeaseScope.EXECUTION
    broker: ControlPlaneOwner = ControlPlaneOwner.OLLARMA
    source_stage: StageName
    allowed_lanes: list[LaneName] = Field(min_length=1)
    request_summary: str
    immutable_input_paths: list[str] = Field(min_length=1)
    expected_output_roots: list[str] = Field(min_length=1)
    operator_approval_ref: Optional[str] = None
    review_required: bool = False

    @field_validator(
        "task_id",
        "lease_id",
        "fencing_token",
        "request_summary",
        "operator_approval_ref",
    )
    @classmethod
    def _validate_non_empty(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return _non_empty(value)

    @field_validator("immutable_input_paths", "expected_output_roots")
    @classmethod
    def _validate_paths(cls, value: list[str]) -> list[str]:
        return [_non_empty(item) for item in value]

    @model_validator(mode="after")
    def _validate_boundary(self) -> "SwarmRunRequest":
        if self.broker is not ControlPlaneOwner.OLLARMA:
            raise ValueError("swarm broker requests must be owned by ollarma")
        if self.lease_scope is not LeaseScope.EXECUTION:
            raise ValueError("swarm broker requests require an execution lease")
        if self.source_stage is StageName.INTERPRET_ESCALATE:
            raise ValueError("interpret/escalate is outside the bounded broker contract")
        unsupported = sorted(lane.value for lane in self.allowed_lanes if lane not in _BROKER_LANES)
        if unsupported:
            raise ValueError(
                "swarm broker requests are limited to bounded execution lanes: " + ", ".join(unsupported)
            )
        return self


class SwarmRunReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    swarm_run_id: str
    task_id: str
    lease_id: str
    fencing_token: str
    broker: ControlPlaneOwner = ControlPlaneOwner.OLLARMA
    status: SwarmRunStatus
    lane_receipt_ids: list[str] = Field(default_factory=list)
    receipt_paths: list[str] = Field(default_factory=list)
    checkpoint_paths: list[str] = Field(default_factory=list)
    artifact_paths: list[str] = Field(default_factory=list)
    blocked_class: Optional[BlockedClass] = None

    @field_validator(
        "swarm_run_id",
        "task_id",
        "lease_id",
        "fencing_token",
        "lane_receipt_ids",
        "receipt_paths",
        "checkpoint_paths",
        "artifact_paths",
        mode="before",
    )
    @classmethod
    def _normalize_fields(cls, value):  # type: ignore[no-untyped-def]
        if isinstance(value, str):
            return _non_empty(value)
        if isinstance(value, list):
            return [_non_empty(item) for item in value]
        return value

    @model_validator(mode="after")
    def _validate_surface(self) -> "SwarmRunReceipt":
        if self.broker is not ControlPlaneOwner.OLLARMA:
            raise ValueError("swarm broker receipts must be owned by ollarma")
        if self.status is SwarmRunStatus.BLOCKED and self.blocked_class is None:
            raise ValueError("blocked_class is required for blocked swarm broker receipts")
        if self.status is not SwarmRunStatus.BLOCKED and self.blocked_class is not None:
            raise ValueError("blocked_class is only allowed for blocked swarm broker receipts")
        if self.status in {
            SwarmRunStatus.COMPLETED,
            SwarmRunStatus.BLOCKED,
            SwarmRunStatus.ESCALATED,
        } and not (
            self.lane_receipt_ids or self.receipt_paths or self.checkpoint_paths or self.artifact_paths
        ):
            raise ValueError("terminal swarm broker receipts must include lane ids, receipts, checkpoints, or artifacts")
        return self


class LaneRunReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    lane_run_id: str
    swarm_run_id: str
    lane: LaneName
    executor: str
    stage: StageName
    status: LaneRunStatus
    receipt_paths: list[str] = Field(default_factory=list)
    checkpoint_paths: list[str] = Field(default_factory=list)
    artifact_paths: list[str] = Field(default_factory=list)
    blocked_class: Optional[BlockedClass] = None

    @field_validator("lane_run_id", "swarm_run_id", "executor")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        return _non_empty(value)

    @field_validator("receipt_paths", "checkpoint_paths", "artifact_paths")
    @classmethod
    def _validate_paths(cls, value: list[str]) -> list[str]:
        return [_non_empty(item) for item in value]

    @model_validator(mode="after")
    def _validate_lane_receipt(self) -> "LaneRunReceipt":
        if self.lane not in _BROKER_LANES:
            raise ValueError("lane run receipts are limited to bounded execution lanes")
        if self.stage is StageName.INTERPRET_ESCALATE:
            raise ValueError("lane run receipts cannot claim interpret/escalate ownership")
        if self.status is LaneRunStatus.BLOCKED and self.blocked_class is None:
            raise ValueError("blocked_class is required for blocked lane run receipts")
        if self.status is not LaneRunStatus.BLOCKED and self.blocked_class is not None:
            raise ValueError("blocked_class is only allowed for blocked lane run receipts")
        if self.status in {
            LaneRunStatus.COMPLETED,
            LaneRunStatus.BLOCKED,
            LaneRunStatus.ESCALATED,
        } and not (self.receipt_paths or self.checkpoint_paths or self.artifact_paths):
            raise ValueError("terminal lane run receipts must include receipts, checkpoints, or artifacts")
        return self
