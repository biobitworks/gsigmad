"""Tests for Phase 06 parallel track ID allocation."""
from pathlib import Path

from typer.testing import CliRunner

from gsigmad.cli import app
from gsigmad.governance.versioning.track_ids import allocate_track_id, next_rerun_version

runner = CliRunner()


def _init_project(path: Path) -> None:
    result = runner.invoke(app, ["init", str(path)])
    assert result.exit_code == 0, result.output


def test_allocate_track_id_sequential(tmp_path: Path) -> None:
    _init_project(tmp_path)

    first = allocate_track_id("EXP", tmp_path)
    second = allocate_track_id("EXP", tmp_path)
    prompt = allocate_track_id("PROMPT", tmp_path)

    assert first == "EXP-1.1"
    assert second == "EXP-1.2"
    assert prompt == "PROMPT-1.1"


def test_allocate_track_id_reconciles_existing_experiments(tmp_path: Path) -> None:
    _init_project(tmp_path)
    experiments_dir = tmp_path / ".gsigmad" / "experiments"
    experiments_dir.mkdir(exist_ok=True)
    (experiments_dir / "EXP-1.3.yaml").write_text("exp_id: EXP-1.3\n", encoding="utf-8")

    allocated = allocate_track_id("EXP", tmp_path)
    assert allocated == "EXP-1.4"


def test_next_rerun_version_updates_legacy_file(tmp_path: Path) -> None:
    _init_project(tmp_path)

    rerun_id = next_rerun_version("EXP-1.1", tmp_path)
    assert rerun_id == "EXP-1.1.1"

    legacy_file = tmp_path / ".agent" / "exp_versions.json"
    assert legacy_file.is_file()
    assert '"EXP-1.1": 1' in legacy_file.read_text(encoding="utf-8")
