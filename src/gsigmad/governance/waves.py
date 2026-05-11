"""Canonical wave schema and policy helpers for portfolio execution."""
from __future__ import annotations

from collections import deque
from enum import Enum
from typing import Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gsigmad.governance.boundary_registry import (
    WaveOwnershipClass,
    ownership_class_for_lane as boundary_ownership_class_for_lane,
)
from gsigmad.governance.execution_contract import (
    BlockedClass,
    LaneName,
    StageName,
    StageReceipt,
    StageStatus,
)

class WaveDecisionAction(str, Enum):
    HOLD = "hold"
    AUTO_ADVANCE = "auto-advance"
    RETRY_WAVE = "retry-wave"
    REQUIRE_HUMAN_REVIEW = "require-human-review"
    FRONTIER_HANDOFF = "frontier-handoff"


BLOCKED_ROUTE_MATRIX: dict[BlockedClass, WaveDecisionAction] = {
    BlockedClass.RETRYABLE: WaveDecisionAction.RETRY_WAVE,
    BlockedClass.NON_RETRYABLE: WaveDecisionAction.REQUIRE_HUMAN_REVIEW,
    BlockedClass.ESCALATE_NOW: WaveDecisionAction.FRONTIER_HANDOFF,
}

_BLOCKED_PRIORITY: dict[BlockedClass, int] = {
    BlockedClass.RETRYABLE: 1,
    BlockedClass.NON_RETRYABLE: 2,
    BlockedClass.ESCALATE_NOW: 3,
}


class WaveNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wave_id: str
    title: str
    lane: LaneName
    deterministic: bool
    depends_on: list[str] = Field(default_factory=list)
    receipt_requirements: list[StageName] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_lane_boundary(self) -> "WaveNode":
        if self.lane in {LaneName.FRONTIER_ONLY, LaneName.HUMAN_REVIEW_REQUIRED} and self.deterministic:
            raise ValueError("frontier-only and human-review-required waves cannot be deterministic")
        if self.lane in {LaneName.OLLARMA_DEFAULT, LaneName.SIDECAR_PARALLEL} and not self.deterministic:
            raise ValueError("ollarma-default and sidecar-parallel waves must declare deterministic=True")
        return self


class WaveSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    phase: str
    waves: list[WaveNode] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_graph(self) -> "WaveSpec":
        ids = [wave.wave_id for wave in self.waves]
        if len(ids) != len(set(ids)):
            raise ValueError("wave ids must be unique")

        known = set(ids)
        for wave in self.waves:
            missing = [dep for dep in wave.depends_on if dep not in known]
            if missing:
                raise ValueError(f"wave '{wave.wave_id}' depends on unknown waves: {', '.join(missing)}")

        topological_wave_ids(self)
        return self


class WaveDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wave_id: str
    action: WaveDecisionAction
    reason: str
    blocked_class: Optional[BlockedClass] = None
    ownership: WaveOwnershipClass


def ownership_class_for_lane(lane: LaneName) -> WaveOwnershipClass:
    return boundary_ownership_class_for_lane(lane)


def topological_wave_ids(spec: WaveSpec) -> list[str]:
    by_id = {wave.wave_id: wave for wave in spec.waves}
    indegree = {wave.wave_id: 0 for wave in spec.waves}
    outgoing: dict[str, list[str]] = {wave.wave_id: [] for wave in spec.waves}

    for wave in spec.waves:
        for dependency in wave.depends_on:
            indegree[wave.wave_id] += 1
            outgoing[dependency].append(wave.wave_id)

    ready = deque(sorted(wave_id for wave_id, degree in indegree.items() if degree == 0))
    ordered: list[str] = []
    while ready:
        wave_id = ready.popleft()
        ordered.append(wave_id)
        for child in sorted(outgoing[wave_id]):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)

    if len(ordered) != len(by_id):
        raise ValueError("wave dependency graph must be acyclic")
    return ordered


def evaluate_wave_decision(
    wave: WaveNode,
    receipts: list[Union[StageReceipt, dict]],
    *,
    completed_dependencies: Optional[set[str]] = None,
) -> WaveDecision:
    ownership = ownership_class_for_lane(wave.lane)

    if completed_dependencies is not None:
        missing_dependencies = sorted(set(wave.depends_on) - set(completed_dependencies))
        if missing_dependencies:
            return WaveDecision(
                wave_id=wave.wave_id,
                action=WaveDecisionAction.HOLD,
                reason=f"waiting on dependencies: {', '.join(missing_dependencies)}",
                ownership=ownership,
            )

    if wave.lane == LaneName.FRONTIER_ONLY:
        return WaveDecision(
            wave_id=wave.wave_id,
            action=WaveDecisionAction.FRONTIER_HANDOFF,
            reason="frontier-only lane requires explicit frontier handoff",
            ownership=ownership,
        )

    if wave.lane == LaneName.HUMAN_REVIEW_REQUIRED:
        return WaveDecision(
            wave_id=wave.wave_id,
            action=WaveDecisionAction.REQUIRE_HUMAN_REVIEW,
            reason="human-review-required lane requires explicit operator review",
            ownership=ownership,
        )

    relevant = [
        receipt if isinstance(receipt, StageReceipt) else StageReceipt.model_validate(receipt)
        for receipt in receipts
        if (receipt.stage if isinstance(receipt, StageReceipt) else receipt.get("stage")) in wave.receipt_requirements
    ]

    strongest_block = _strongest_blocked_class(relevant)
    if strongest_block is not None:
        return WaveDecision(
            wave_id=wave.wave_id,
            action=BLOCKED_ROUTE_MATRIX[strongest_block],
            reason=f"blocked via {strongest_block.value}",
            blocked_class=strongest_block,
            ownership=ownership,
        )

    if any(receipt.status == StageStatus.FAIL for receipt in relevant):
        return WaveDecision(
            wave_id=wave.wave_id,
            action=WaveDecisionAction.HOLD,
            reason="one or more required receipts failed",
            ownership=ownership,
        )

    passed = {receipt.stage for receipt in relevant if receipt.status == StageStatus.PASS}
    required = set(wave.receipt_requirements)
    if required.issubset(passed):
        return WaveDecision(
            wave_id=wave.wave_id,
            action=WaveDecisionAction.AUTO_ADVANCE,
            reason="all required receipts passed",
            ownership=ownership,
        )

    missing_receipts = ", ".join(stage.value for stage in sorted(required - passed, key=lambda item: item.value))
    return WaveDecision(
        wave_id=wave.wave_id,
        action=WaveDecisionAction.HOLD,
        reason=f"awaiting pass receipts: {missing_receipts}",
        ownership=ownership,
    )


def _strongest_blocked_class(receipts: list[StageReceipt]) -> Optional[BlockedClass]:
    blocked = [receipt.blocked_class for receipt in receipts if receipt.status == StageStatus.BLOCKED]
    blocked = [item for item in blocked if item is not None]
    if not blocked:
        return None
    return max(blocked, key=lambda item: _BLOCKED_PRIORITY[item])
