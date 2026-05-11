"""Tests for gsigmad resume command."""
import json
from pathlib import Path

from typer.testing import CliRunner

from gsigmad.cli import app

runner = CliRunner()


def _init_project(path: Path) -> None:
    result = runner.invoke(app, ["init", str(path)])
    assert result.exit_code == 0, result.output


def test_resume_restores_latest_checkpoint(tmp_path: Path, monkeypatch) -> None:
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    pause_result = runner.invoke(app, ["pause", "--note", "restore-me"], catch_exceptions=False)
    assert pause_result.exit_code == 0, pause_result.output

    result = runner.invoke(app, ["--json", "resume"], catch_exceptions=False)
    assert result.exit_code == 0, result.output

    payload = json.loads(result.output)
    assert payload["note"] == "restore-me"
    assert payload["recommended_command"]
