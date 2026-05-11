"""Shared escalation bundle helpers for probabilistic reasoning and human review."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gsigmad.governance.adapter_contracts import (
    EscalationReason,
    FrontierEscalationPacket,
    HumanApprovalKind,
)
from gsigmad.governance.execution_contract import BlockedClass, LaneName, StageName


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _non_empty(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("value must be non-empty")
    return normalized


class EscalationBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bundle_id: str
    run_id: str
    wave_id: str
    source_stage: StageName
    lane: LaneName
    reason: EscalationReason
    receipt_ids: list[str] = Field(min_length=1)
    evidence_paths: list[str] = Field(min_length=1)
    request_summary: str
    approval_lane: LaneName = LaneName.HUMAN_REVIEW_REQUIRED
    approval_kind: HumanApprovalKind = HumanApprovalKind.OPERATOR_REVIEW_REQUIRED
    blocked_class: Optional[BlockedClass] = None
    reverification_status: Optional[str] = None
    frontier_packet: Optional[FrontierEscalationPacket] = None
    created_at: str = Field(default_factory=_utc_now)

    @field_validator("bundle_id", "run_id", "wave_id", "request_summary")
    @classmethod
    def _validate_non_empty_fields(cls, value: str) -> str:
        return _non_empty(value)

    @field_validator("receipt_ids", "evidence_paths")
    @classmethod
    def _validate_paths(cls, value: list[str]) -> list[str]:
        return [_non_empty(item) for item in value]

    @model_validator(mode="after")
    def _validate_surface(self) -> "EscalationBundle":
        if self.lane not in {LaneName.FRONTIER_ONLY, LaneName.HUMAN_REVIEW_REQUIRED}:
            raise ValueError("escalation bundles must route to frontier-only or human-review-required lanes")
        if self.source_stage not in {StageName.SUMMARIZE, StageName.INTERPRET_ESCALATE}:
            raise ValueError("escalation bundles must originate from summarize or interpret/escalate")
        if self.approval_lane != LaneName.HUMAN_REVIEW_REQUIRED:
            raise ValueError("escalation bundles must route approval through human-review-required")
        if self.lane == LaneName.FRONTIER_ONLY and self.frontier_packet is None:
            raise ValueError("frontier-only escalation bundles require a wrapped frontier escalation packet")
        if self.lane == LaneName.HUMAN_REVIEW_REQUIRED and self.frontier_packet is not None:
            raise ValueError("human-review-required escalation bundles must not embed a frontier packet")
        if self.reverification_status == "escalate-now" and self.lane != LaneName.FRONTIER_ONLY:
            raise ValueError("escalate-now reverification must route through frontier-only")
        if self.blocked_class == BlockedClass.ESCALATE_NOW and self.lane != LaneName.FRONTIER_ONLY:
            raise ValueError("escalate-now blocked work must route through frontier-only")
        return self


def build_interpretation_bundle(
    *,
    run_id: str,
    wave_id: str,
    source_stage: StageName,
    receipt_ids: list[str],
    evidence_paths: list[str],
    request_summary: str,
    approval_kind: HumanApprovalKind = HumanApprovalKind.OPERATOR_REVIEW_REQUIRED,
) -> EscalationBundle:
    packet = FrontierEscalationPacket.model_validate(
        {
            "packet_id": f"ESC-{run_id}-{wave_id}-interpret",
            "run_id": run_id,
            "wave_id": wave_id,
            "lane": LaneName.FRONTIER_ONLY,
            "source_stage": source_stage,
            "reason": EscalationReason.SCIENTIFIC_INTERPRETATION,
            "receipt_ids": receipt_ids,
            "evidence_paths": evidence_paths,
            "request_summary": request_summary,
            "approval_lane": LaneName.HUMAN_REVIEW_REQUIRED,
            "approval_kind": approval_kind,
        }
    )
    return EscalationBundle.model_validate(
        {
            "bundle_id": f"BUNDLE-{run_id}-{wave_id}-interpret",
            "run_id": run_id,
            "wave_id": wave_id,
            "source_stage": source_stage,
            "lane": LaneName.FRONTIER_ONLY,
            "reason": EscalationReason.SCIENTIFIC_INTERPRETATION,
            "receipt_ids": receipt_ids,
            "evidence_paths": evidence_paths,
            "request_summary": request_summary,
            "approval_lane": LaneName.HUMAN_REVIEW_REQUIRED,
            "approval_kind": approval_kind,
            "frontier_packet": packet,
        }
    )


def build_blocked_diagnosis_bundle(
    *,
    run_id: str,
    wave_id: str,
    source_stage: StageName,
    receipt_ids: list[str],
    evidence_paths: list[str],
    request_summary: str,
    blocked_class: BlockedClass,
    reverification_status: Optional[str] = None,
    approval_kind: HumanApprovalKind = HumanApprovalKind.OPERATOR_REVIEW_REQUIRED,
) -> EscalationBundle:
    lane = (
        LaneName.FRONTIER_ONLY
        if blocked_class == BlockedClass.ESCALATE_NOW or reverification_status == "escalate-now"
        else LaneName.HUMAN_REVIEW_REQUIRED
    )
    packet = None
    if lane == LaneName.FRONTIER_ONLY:
        packet = FrontierEscalationPacket.model_validate(
            {
                "packet_id": f"ESC-{run_id}-{wave_id}-diagnosis",
                "run_id": run_id,
                "wave_id": wave_id,
                "lane": LaneName.FRONTIER_ONLY,
                "source_stage": source_stage,
                "reason": EscalationReason.BLOCKED_RUN_DIAGNOSIS,
                "receipt_ids": receipt_ids,
                "evidence_paths": evidence_paths,
                "request_summary": request_summary,
                "approval_lane": LaneName.HUMAN_REVIEW_REQUIRED,
                "approval_kind": approval_kind,
            }
        )

    return EscalationBundle.model_validate(
        {
            "bundle_id": f"BUNDLE-{run_id}-{wave_id}-diagnosis",
            "run_id": run_id,
            "wave_id": wave_id,
            "source_stage": source_stage,
            "lane": lane,
            "reason": EscalationReason.BLOCKED_RUN_DIAGNOSIS,
            "receipt_ids": receipt_ids,
            "evidence_paths": evidence_paths,
            "request_summary": request_summary,
            "approval_lane": LaneName.HUMAN_REVIEW_REQUIRED,
            "approval_kind": approval_kind,
            "blocked_class": blocked_class,
            "reverification_status": reverification_status,
            "frontier_packet": packet,
        }
    )
