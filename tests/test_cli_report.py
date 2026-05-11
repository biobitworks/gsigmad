"""Tests for gsigmad report subcommands."""
import json
from pathlib import Path

from typer.testing import CliRunner

from gsigmad.cli import app

runner = CliRunner()


def _init_project(path: Path) -> None:
    result = runner.invoke(app, ["init", str(path)])
    assert result.exit_code == 0, result.output


def _register(path: Path, monkeypatch) -> None:
    monkeypatch.chdir(path)
    result = runner.invoke(app, ["register", "--type", "exploratory"], catch_exceptions=False)
    assert result.exit_code == 0, result.output


def test_report_lock_creates_registered_report_record(tmp_path: Path, monkeypatch):
    _init_project(tmp_path)
    _register(tmp_path, monkeypatch)
    result = runner.invoke(app, ["report", "lock", "EXP-1.1"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    lock_file = tmp_path / ".agent" / "registered_reports.json"
    assert lock_file.is_file()


def test_report_amend_from_json_file(tmp_path: Path, monkeypatch):
    _init_project(tmp_path)
    _register(tmp_path, monkeypatch)
    runner.invoke(app, ["report", "lock", "EXP-1.1"], catch_exceptions=False)

    payload = {
        "justification": "Need to update the effect-size threshold before continuing.",
        "pi_countersignature": "PI-SIGNATURE",
        "changed_fields": ["hypothesis.alpha"],
        "original_values": {"hypothesis.alpha": 0.05},
        "new_values": {"hypothesis.alpha": 0.01},
    }
    payload_path = tmp_path / "amendment.json"
    payload_path.write_text(json.dumps(payload), encoding="utf-8")

    result = runner.invoke(
        app,
        ["report", "amend", "EXP-1.1", "--json-file", str(payload_path)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".agent" / "amendments" / "EXP-1.1-1.json").is_file()
