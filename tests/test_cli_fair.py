"""Tests for gsigmad fair command."""
import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from gsigmad.cli import app

runner = CliRunner()


def _init_project(path: Path) -> None:
    result = runner.invoke(app, ["init", str(path)])
    assert result.exit_code == 0, result.output


def test_fair_json_output(tmp_path: Path, monkeypatch):
    _init_project(tmp_path)
    exp_record = {
        "exp_id": "EXP-1.1",
        "title": "FAIR test",
        "description": "desc",
        "keywords": ["fair"],
        "creator": "Tester",
        "identifiers": {"doi": "10.1234/fair.test"},
        "license": "cc-by-4.0",
        "methodology": "Do the thing",
        "variables": [{"name": "x", "definition": "signal", "unit": "a.u."}],
        "output_files": ["results/exp1.csv", "results/exp1.prov.json"],
    }
    (tmp_path / ".gsigmad" / "experiments" / "EXP-1.1.yaml").write_text(
        yaml.safe_dump(exp_record, sort_keys=False), encoding="utf-8"
    )
    results_dir = tmp_path / "results"
    results_dir.mkdir(exist_ok=True)
    (results_dir / "exp1.csv").write_text("value\n1\n", encoding="utf-8")
    (results_dir / "exp1.prov.json").write_text(
        json.dumps({"entity": {}, "activity": {}, "wasGeneratedBy": {}}), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["--json", "fair", "EXP-1.1"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["exp_id"] == "EXP-1.1"
    assert (tmp_path / ".gsigmad" / "fair" / "EXP-1.1_fair.json").is_file()
