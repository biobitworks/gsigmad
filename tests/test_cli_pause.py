"""Tests for gsigmad pause command."""
import json
from pathlib import Path

from typer.testing import CliRunner

from gsigmad.cli import app

runner = CliRunner()


def _init_project(path: Path) -> None:
    result = runner.invoke(app, ["init", str(path)])
    assert result.exit_code == 0, result.output


def test_pause_writes_checkpoint(tmp_path: Path, monkeypatch) -> None:
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["pause", "--note", "mid-analysis"], catch_exceptions=False)
    assert result.exit_code == 0, result.output

    latest = tmp_path / ".gsigmad" / "context" / "latest.json"
    assert latest.is_file()
    payload = json.loads(latest.read_text(encoding="utf-8"))
    assert payload["note"] == "mid-analysis"
    assert payload["recommended_command"]
