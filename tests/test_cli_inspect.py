"""Tests for the coexistence-aware inspect command."""
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from gsigmad.cli import app

runner = CliRunner()


def _write_manifest(repo_root: Path, target_root: Path) -> None:
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
                "command_modes:",
                "  status: legacy",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_inspect_native_project(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "native"
    result = runner.invoke(app, ["init", str(project)], catch_exceptions=False)
    assert result.exit_code == 0, result.output

    monkeypatch.chdir(tmp_path)
    inspect_result = runner.invoke(app, ["inspect", str(project)], catch_exceptions=False)

    assert inspect_result.exit_code == 0, inspect_result.output
    assert "gsigmad" in inspect_result.output
    assert "native_gsigmad" in inspect_result.output


def test_inspect_manifest_project_json_output(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    target_root = tmp_path / "shadow-seeds"
    target_root.mkdir(parents=True)
    _write_manifest(repo_root, target_root)

    monkeypatch.chdir(repo_root)
    result = runner.invoke(app, ["--json", "inspect", str(target_root)], catch_exceptions=False)

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["runtime_mode"] == "legacy"
    assert payload["namespace_prefix"] == "shadow:"
    assert payload["compatibility"]["commands"]["status"] == "legacy"
    assert payload["compatibility"]["commands"]["run"] == "unsupported"
