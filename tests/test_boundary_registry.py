"""Tests for the Phase 31 deterministic-vs-probabilistic boundary registry."""
from __future__ import annotations

from gsigmad.governance.boundary_registry import (
    BoundaryMode,
    lane_boundary,
    resolve_boundary_surface,
    stage_boundary,
)
from gsigmad.governance.execution_contract import LaneName, StageName


def test_stage_boundary_freezes_deterministic_vs_probabilistic_split() -> None:
    deterministic_stages = (
        StageName.PREFLIGHT,
        StageName.SCAFFOLD_MATERIALIZE,
        StageName.EXECUTE,
        StageName.VALIDATE,
        StageName.SUMMARIZE,
    )
    for stage in deterministic_stages:
        profile = stage_boundary(stage)
        assert profile.mode == BoundaryMode.DETERMINISTIC
        assert profile.requires_human_review is False

    interpret = stage_boundary(StageName.INTERPRET_ESCALATE)
    assert interpret.mode == BoundaryMode.PROBABILISTIC
    assert interpret.requires_human_review is True


def test_lane_boundary_reuses_shared_wave_ownership_posture() -> None:
    ollarma = lane_boundary(LaneName.OLLARMA_DEFAULT)
    assert ollarma.mode == BoundaryMode.DETERMINISTIC
    assert ollarma.ownership.value == "deterministic-execution"

    frontier = lane_boundary(LaneName.FRONTIER_ONLY)
    assert frontier.mode == BoundaryMode.PROBABILISTIC
    assert frontier.ownership.value == "probabilistic-reasoning"

    human = lane_boundary(LaneName.HUMAN_REVIEW_REQUIRED)
    assert human.mode == BoundaryMode.HUMAN_GATE
    assert human.requires_human_review is True


def test_resolve_boundary_surface_returns_machine_readable_posture() -> None:
    summarize_surface = resolve_boundary_surface(StageName.SUMMARIZE, LaneName.SIDECAR_PARALLEL)
    assert summarize_surface.stage.value == "summarize"
    assert summarize_surface.stage_mode == BoundaryMode.DETERMINISTIC
    assert summarize_surface.lane_mode == BoundaryMode.DETERMINISTIC
    assert summarize_surface.requires_human_review is False

    interpret_surface = resolve_boundary_surface(StageName.INTERPRET_ESCALATE, LaneName.FRONTIER_ONLY)
    assert interpret_surface.stage_mode == BoundaryMode.PROBABILISTIC
    assert interpret_surface.lane_mode == BoundaryMode.PROBABILISTIC
    assert interpret_surface.requires_human_review is True
