"""Tests for gsigmad drift command."""
import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from gsigmad.cli import app

runner = CliRunner()


def _init_project(path: Path) -> None:
    result = runner.invoke(app, ["init", str(path)])
    assert result.exit_code == 0, result.output


def test_drift_json_output(tmp_path: Path, monkeypatch):
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    with patch("gsigmad.governance.compiler.drift_check.check_drift", return_value={"pass": True, "triggered": False, "counter": 1}):
        result = runner.invoke(app, ["--json", "drift"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["counter"] == 1


def test_drift_failures_exit_1(tmp_path: Path, monkeypatch):
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    with patch("gsigmad.governance.compiler.drift_check.check_drift", return_value={"pass": False, "triggered": True, "error": "DRIFT_WARNING"}):
        result = runner.invoke(app, ["drift"], catch_exceptions=False)
    assert result.exit_code == 1, result.output
