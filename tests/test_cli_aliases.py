"""Tests for gsigmad command aliases."""
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from gsigmad.cli import app

runner = CliRunner()


def _init_project(path: Path) -> None:
    result = runner.invoke(app, ["init", str(path)])
    assert result.exit_code == 0, result.output


def test_short_aliases(tmp_path: Path, monkeypatch):
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["register", "--type", "exploratory"], catch_exceptions=False)

    with patch("gsigmad.commands.audit._load_audit_gate", return_value=lambda claims, verify_citations=True: {"pass": True, "failures": [], "warnings": []}):
        audit_result = runner.invoke(app, ["a"], catch_exceptions=False)
    status_result = runner.invoke(app, ["s"], catch_exceptions=False)

    assert audit_result.exit_code == 0, audit_result.output
    assert status_result.exit_code == 0, status_result.output
