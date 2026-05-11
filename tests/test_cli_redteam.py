"""Tests for gsigmad redteam command."""
from pathlib import Path

import yaml
from typer.testing import CliRunner

from gsigmad.cli import app

runner = CliRunner()


def _init_project(path: Path) -> None:
    result = runner.invoke(app, ["init", str(path)])
    assert result.exit_code == 0, result.output


def _write_exp(path: Path, exp_id: str, classification: str, **extra) -> None:
    payload = {"exp_id": exp_id, "classification": classification, "hypothesis": {"h0": "No effect"}}
    payload.update(extra)
    target = path / ".gsigmad" / "experiments" / f"{exp_id}.yaml"
    target.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_redteam_exploratory_passes(tmp_path: Path, monkeypatch):
    _init_project(tmp_path)
    _write_exp(tmp_path, "EXP-1.1", "EXPLORATORY")
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["redteam", "EXP-1.1"], catch_exceptions=False)
    assert result.exit_code == 0, result.output


def test_redteam_confirmatory_failures_exit_1(tmp_path: Path, monkeypatch):
    _init_project(tmp_path)
    _write_exp(tmp_path, "EXP-1.1", "CONFIRMATORY")
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["redteam", "EXP-1.1"], catch_exceptions=False)
    assert result.exit_code == 1, result.output


def test_redteam_json_output(tmp_path: Path, monkeypatch):
    _init_project(tmp_path)
    _write_exp(
        tmp_path,
        "EXP-1.1",
        "CONFIRMATORY",
        prompt_fields={
            "risk_tier": "P1",
            "red_team_status": "PASS",
            "remediation_constraints": ["document scope"],
            "execution_decision": "GO",
        },
    )
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["--json", "redteam", "EXP-1.1"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
