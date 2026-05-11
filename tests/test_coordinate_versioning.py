"""Tests for Phase 06 coordinate versioning."""
from pathlib import Path

from typer.testing import CliRunner

from gsigmad.cli import app
from gsigmad.governance.versioning.coordinate import (
    advance_coordinate,
    bootstrap_coordination_state,
    load_coordination_state,
    resolve_coordinate,
)

runner = CliRunner()


def _init_project(path: Path) -> None:
    result = runner.invoke(app, ["init", str(path)])
    assert result.exit_code == 0, result.output


def test_init_bootstraps_coordination_registry(tmp_path: Path) -> None:
    _init_project(tmp_path)

    coordination_file = tmp_path / ".gsigmad" / "coordination.json"
    assert coordination_file.is_file()

    state = load_coordination_state(tmp_path)
    assert state["coordinate"]["version"] >= 1
    assert state["coordinate"]["milestone"] >= 1
    assert state["coordinate"]["phase"] == 1
    assert state["coordinate"]["wave"] == 1


def test_resolve_coordinate_returns_project_coordinate(tmp_path: Path) -> None:
    _init_project(tmp_path)

    coordinate = resolve_coordinate(tmp_path)
    assert coordinate is not None
    assert coordinate.startswith("v")
    assert coordinate.count(".") == 3


def test_advance_coordinate_resets_lower_slots(tmp_path: Path) -> None:
    _init_project(tmp_path)

    assert advance_coordinate(tmp_path, level="wave").endswith(".2")
    assert advance_coordinate(tmp_path, level="phase").endswith(".2.1")

    state = load_coordination_state(tmp_path)
    assert state["coordinate"]["phase"] == 2
    assert state["coordinate"]["wave"] == 1


def test_coordinate_slot_overflow_raises(tmp_path: Path) -> None:
    _init_project(tmp_path)
    state = load_coordination_state(tmp_path)
    state["coordinate"]["wave"] = 9
    bootstrap_coordination_state(tmp_path)

    from gsigmad.governance.versioning.coordinate import save_coordination_state

    save_coordination_state(tmp_path, state)

    try:
        advance_coordinate(tmp_path, level="wave")
    except ValueError as exc:
        assert "overflow" in str(exc).lower()
    else:  # pragma: no cover - explicit failure branch
        raise AssertionError("Expected wave overflow to raise ValueError")
