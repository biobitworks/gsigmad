"""Tests for gsigmad export command."""
import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from gsigmad.cli import app

runner = CliRunner()


def _init_project(path: Path) -> None:
    result = runner.invoke(app, ["init", str(path)])
    assert result.exit_code == 0, result.output


def test_export_json_output(tmp_path: Path, monkeypatch):
    _init_project(tmp_path)
    exp_record = {
        "exp_id": "EXP-1.1",
        "title": "Export test",
        "output_files": ["results/exp1.csv"],
    }
    (tmp_path / ".gsigmad" / "experiments" / "EXP-1.1.yaml").write_text(
        yaml.safe_dump(exp_record, sort_keys=False), encoding="utf-8"
    )
    results_dir = tmp_path / "results"
    results_dir.mkdir(exist_ok=True)
    (results_dir / "exp1.csv").write_text("value\n1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["--json", "export", "EXP-1.1"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert "bundle_path" in data
    assert (tmp_path / "exports" / "EXP-1.1" / "manifest.json").is_file()
