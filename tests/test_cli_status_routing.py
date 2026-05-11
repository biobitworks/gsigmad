"""Tests for coexistence-aware routing in the status command."""
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from gsigmad.cli import app

runner = CliRunner()


def _write_manifest(repo_root: Path, target_root: Path, *, status_mode: str = "legacy") -> None:
    registry = repo_root / "adapters" / "runtime"
    registry.mkdir(parents=True)
    (registry / "shadow-seeds.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "project_name: shadow-seeds",
                f"project_root: {target_root}",
                'namespace_prefix: "shadow:"',
                "runtime_mode: legacy",
                "surfaces:",
                "  canon_path: CANON.md",
                "  experiments_dir: experiments",
                "  legacy_state_dir: .agent",
                "  lab_notebook_path: LAB_NOTEBOOK.md",
                "command_modes:",
                f"  status: {status_mode}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_legacy_project(project_root: Path) -> None:
    experiments = project_root / "experiments"
    experiments.mkdir(parents=True)
    (project_root / ".agent").mkdir()
    (project_root / "CANON.md").write_text("# Canon\n", encoding="utf-8")
    (project_root / "LAB_NOTEBOOK.md").write_text("EXP-001: note\n", encoding="utf-8")
    (experiments / "EXP-001.md").write_text(
        "\n".join(
            [
                "Project: shadow-seeds",
                "Classification: exploratory",
                "Status: planned",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_status_routes_legacy_project_without_creating_gsigmad(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    target_root = tmp_path / "shadow-seeds"
    _write_legacy_project(target_root)
    _write_manifest(repo_root, target_root)

    monkeypatch.chdir(repo_root)
    result = runner.invoke(app, ["status", str(target_root)], catch_exceptions=False)

    assert result.exit_code == 0, result.output
    assert "EXP-001" in result.output
    assert "legacy" in result.output.lower()
    assert not (target_root / ".gsigmad").exists()


def test_status_routes_legacy_project_in_json_mode(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    target_root = tmp_path / "shadow-seeds"
    _write_legacy_project(target_root)
    _write_manifest(repo_root, target_root)

    monkeypatch.chdir(repo_root)
    result = runner.invoke(app, ["--json", "status", str(target_root)], catch_exceptions=False)

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["routing"]["runtime_mode"] == "legacy"
    assert payload["experiments"]["exps"][0]["exp_id"] == "EXP-001"
    assert payload["drift"]["error"] == "not yet tracked"


def test_status_unsupported_route_errors_cleanly(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    target_root = tmp_path / "shadow-seeds"
    _write_legacy_project(target_root)
    _write_manifest(repo_root, target_root, status_mode="unsupported")

    monkeypatch.chdir(repo_root)
    result = runner.invoke(app, ["status", str(target_root)], catch_exceptions=False)

    assert result.exit_code == 1, result.output
    assert "not routed safely" in result.output
