"""Phase 34 Watchtower operator projection contract helpers."""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gsigmad.governance.control_plane_contract import validate_control_plane_guardrails
from gsigmad.governance.state_authority import is_advisory_intent


def _non_empty(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("value must be non-empty")
    return normalized


class OperatorRefKind(str, Enum):
    TASK = "task"
    LEASE = "lease"
    BLOCKER = "blocker"
    REVIEW_VERDICT = "review-verdict"
    RECEIPT = "receipt"
    HUMAN_DECISION = "human-decision"


class OperatorSurfaceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref_kind: OperatorRefKind
    ref_id: str

    @field_validator("ref_id")
    @classmethod
    def _validate_ref_id(cls, value: str) -> str:
        return _non_empty(value)


class _BaseOperatorProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    backing_refs: list[OperatorSurfaceRef] = Field(min_length=1)
    advisory: bool = True

    @model_validator(mode="before")
    @classmethod
    def _validate_guardrails(cls, data: Any) -> Any:
        if isinstance(data, dict):
            validate_control_plane_guardrails(data)
        return data

    @field_validator("task_id")
    @classmethod
    def _validate_task_id(cls, value: str) -> str:
        return _non_empty(value)

    @model_validator(mode="after")
    def _validate_authority(self) -> "_BaseOperatorProjection":
        ref_kinds = {item.ref_kind for item in self.backing_refs}
        if not self.advisory and not (
            OperatorRefKind.RECEIPT in ref_kinds or OperatorRefKind.HUMAN_DECISION in ref_kinds
        ):
            raise ValueError("non-advisory operator views require receipt-backed or human-decision backing")
        return self


class NextStepView(_BaseOperatorProjection):
    next_step_id: str
    route_hint: str
    intent_summary: str

    @field_validator("next_step_id", "route_hint", "intent_summary")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        return _non_empty(value)


class InboxItem(_BaseOperatorProjection):
    inbox_item_id: str
    rank: int = Field(ge=1)
    title: str

    @field_validator("inbox_item_id", "title")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        return _non_empty(value)


class ActivityRailItem(_BaseOperatorProjection):
    activity_id: str
    activity_kind: str
    summary: str

    @field_validator("activity_id", "activity_kind", "summary")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        return _non_empty(value)


def operator_view_is_advisory(view: _BaseOperatorProjection) -> bool:
    if any(ref.ref_kind is OperatorRefKind.HUMAN_DECISION for ref in view.backing_refs):
        return is_advisory_intent("HumanDecision")
    if any(ref.ref_kind is OperatorRefKind.RECEIPT for ref in view.backing_refs):
        return False if not view.advisory else True
    return view.advisory
