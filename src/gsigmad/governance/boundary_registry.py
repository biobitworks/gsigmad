"""Shared deterministic-vs-probabilistic boundary registry."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict

from gsigmad.governance.execution_contract import LaneName, StageName


class BoundaryMode(str, Enum):
    DETERMINISTIC = "deterministic"
    PROBABILISTIC = "probabilistic"
    HUMAN_GATE = "human-gate"


class WaveOwnershipClass(str, Enum):
    DETERMINISTIC_EXECUTION = "deterministic-execution"
    DETERMINISTIC_SIDECAR = "deterministic-sidecar"
    PROBABILISTIC_REASONING = "probabilistic-reasoning"
    HUMAN_GATE = "human-gate"


class StageBoundaryProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: StageName
    mode: BoundaryMode
    requires_human_review: bool = False


class LaneBoundaryProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    lane: LaneName
    mode: BoundaryMode
    ownership: WaveOwnershipClass
    requires_human_review: bool = False


class BoundarySurface(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: StageName
    lane: LaneName
    stage_mode: BoundaryMode
    lane_mode: BoundaryMode
    ownership: WaveOwnershipClass
    requires_human_review: bool


_STAGE_BOUNDARIES: dict[StageName, StageBoundaryProfile] = {
    StageName.PREFLIGHT: StageBoundaryProfile(stage=StageName.PREFLIGHT, mode=BoundaryMode.DETERMINISTIC),
    StageName.SCAFFOLD_MATERIALIZE: StageBoundaryProfile(
        stage=StageName.SCAFFOLD_MATERIALIZE,
        mode=BoundaryMode.DETERMINISTIC,
    ),
    StageName.EXECUTE: StageBoundaryProfile(stage=StageName.EXECUTE, mode=BoundaryMode.DETERMINISTIC),
    StageName.VALIDATE: StageBoundaryProfile(stage=StageName.VALIDATE, mode=BoundaryMode.DETERMINISTIC),
    StageName.SUMMARIZE: StageBoundaryProfile(stage=StageName.SUMMARIZE, mode=BoundaryMode.DETERMINISTIC),
    StageName.INTERPRET_ESCALATE: StageBoundaryProfile(
        stage=StageName.INTERPRET_ESCALATE,
        mode=BoundaryMode.PROBABILISTIC,
        requires_human_review=True,
    ),
}

_LANE_BOUNDARIES: dict[LaneName, LaneBoundaryProfile] = {
    LaneName.OLLARMA_DEFAULT: LaneBoundaryProfile(
        lane=LaneName.OLLARMA_DEFAULT,
        mode=BoundaryMode.DETERMINISTIC,
        ownership=WaveOwnershipClass.DETERMINISTIC_EXECUTION,
    ),
    LaneName.SIDECAR_PARALLEL: LaneBoundaryProfile(
        lane=LaneName.SIDECAR_PARALLEL,
        mode=BoundaryMode.DETERMINISTIC,
        ownership=WaveOwnershipClass.DETERMINISTIC_SIDECAR,
    ),
    LaneName.FRONTIER_ONLY: LaneBoundaryProfile(
        lane=LaneName.FRONTIER_ONLY,
        mode=BoundaryMode.PROBABILISTIC,
        ownership=WaveOwnershipClass.PROBABILISTIC_REASONING,
        requires_human_review=True,
    ),
    LaneName.HUMAN_REVIEW_REQUIRED: LaneBoundaryProfile(
        lane=LaneName.HUMAN_REVIEW_REQUIRED,
        mode=BoundaryMode.HUMAN_GATE,
        ownership=WaveOwnershipClass.HUMAN_GATE,
        requires_human_review=True,
    ),
}


def stage_boundary(stage: StageName) -> StageBoundaryProfile:
    return _STAGE_BOUNDARIES[stage]


def lane_boundary(lane: LaneName) -> LaneBoundaryProfile:
    return _LANE_BOUNDARIES[lane]


def ownership_class_for_lane(lane: LaneName) -> WaveOwnershipClass:
    return lane_boundary(lane).ownership


def resolve_boundary_surface(stage: StageName, lane: LaneName) -> BoundarySurface:
    stage_profile = stage_boundary(stage)
    lane_profile = lane_boundary(lane)
    return BoundarySurface(
        stage=stage,
        lane=lane,
        stage_mode=stage_profile.mode,
        lane_mode=lane_profile.mode,
        ownership=lane_profile.ownership,
        requires_human_review=stage_profile.requires_human_review or lane_profile.requires_human_review,
    )
