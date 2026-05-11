"""Tests for gsigmad status command (CLI-05)."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from typer.testing import CliRunner

from gsigmad.cli import app
from gsigmad.governance.closure_chain import record_chain_event

runner = CliRunner()
# Patch targets at the source module level (lazy imports in status.py
# import from these modules, so we mock at the origin)
_PATCH_EXP = "gsigmad.governance.compiler.session_status.get_exp_status_summary"
_PATCH_DRIFT = "gsigmad.governance.compiler.drift_check.check_drift"


def _init_project(path: Path) -> None:
    """Helper: initialize a gsigmad project at path."""
    result = runner.invoke(app, ["init", str(path)])
    assert result.exit_code == 0, f"init failed: {result.output}"


_MOCK_EXPS = {
    "pass": True,
    "exps": [
        {
            "exp_id": "EXP-1.1",
            "classification": "CONFIRMATORY",
            "status": "planned",
            "project": "test-project",
            "last_run_id": "\u2014",
        }
    ],
    "source": "local_fallback",
    "warning": "KG_UNAVAILABLE: using local file scan fallback",
}

_MOCK_EXPS_EMPTY = {
    "pass": True,
    "exps": [],
    "source": "local_fallback",
    "warning": "KG_UNAVAILABLE: using local file scan fallback",
}

_MOCK_DRIFT_NOT_TRIGGERED = {
    "pass": True,
    "triggered": False,
    "counter": 2,
}

_MOCK_DRIFT_TRIGGERED = {
    "pass": True,
    "triggered": True,
    "science_pct": 80.0,
    "breakdown": {"SCIENCE": 4, "INFRASTRUCTURE": 1},
}


def test_status_shows_experiments(tmp_path: Path, monkeypatch):
    """status in initialized project with experiments shows experiment table."""
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    with (
        patch(_PATCH_EXP, return_value=_MOCK_EXPS),
        patch(_PATCH_DRIFT, return_value=_MOCK_DRIFT_NOT_TRIGGERED),
    ):
        result = runner.invoke(app, ["status"], catch_exceptions=False)

    assert result.exit_code == 0, f"stdout: {result.output}"
    assert "EXP-1.1" in result.output
    assert "CONFIRMATORY" in result.output


def test_status_empty_project(tmp_path: Path, monkeypatch):
    """status in initialized project with no experiments shows 'No experiments' message."""
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    with (
        patch(_PATCH_EXP, return_value=_MOCK_EXPS_EMPTY),
        patch(_PATCH_DRIFT, return_value=_MOCK_DRIFT_NOT_TRIGGERED),
    ):
        result = runner.invoke(app, ["status"], catch_exceptions=False)

    assert result.exit_code == 0, f"stdout: {result.output}"
    output_lower = result.output.lower()
    assert "no active experiments" in output_lower or "no experiments" in output_lower


def test_status_shows_drift(tmp_path: Path, monkeypatch):
    """status includes drift score section."""
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    with (
        patch(_PATCH_EXP, return_value=_MOCK_EXPS),
        patch(_PATCH_DRIFT, return_value=_MOCK_DRIFT_TRIGGERED),
    ):
        result = runner.invoke(app, ["status"], catch_exceptions=False)

    assert result.exit_code == 0, f"stdout: {result.output}"
    assert "80" in result.output or "drift" in result.output.lower()


def test_status_json_output(tmp_path: Path, monkeypatch):
    """--json produces valid JSON with experiments and drift keys."""
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    with (
        patch(_PATCH_EXP, return_value=_MOCK_EXPS),
        patch(_PATCH_DRIFT, return_value=_MOCK_DRIFT_NOT_TRIGGERED),
    ):
        result = runner.invoke(app, ["--json", "status"], catch_exceptions=False)

    assert result.exit_code == 0, f"stdout: {result.output}"
    data = json.loads(result.output)
    assert "experiments" in data
    assert "drift" in data
    assert "closure" in data


def test_status_rich_output_shows_degraded_banner_when_runtime_below_full_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rich status output should carry the shared degraded banner when the runtime is below full service."""
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    degraded_state = {
        "tier": "KG_DEGRADED",
        "unavailable_services": ["kg"],
        "detected_at": "2026-04-19T20:00:00Z",
    }

    with (
        patch("gsigmad.cli.compute_degradation_state", return_value=degraded_state),
        patch("gsigmad.cli.write_degradation_state"),
        patch(_PATCH_EXP, return_value=_MOCK_EXPS),
        patch(_PATCH_DRIFT, return_value=_MOCK_DRIFT_NOT_TRIGGERED),
    ):
        result = runner.invoke(app, ["status"], catch_exceptions=False)

    assert result.exit_code == 0, result.output
    assert "[DEGRADED]" in result.output
    assert "KG_DEGRADED" in result.output
    assert "EXP-1.1" in result.output


def test_status_json_includes_degradation_state_when_kg_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Status JSON should include the structured degradation object from the shared runtime state."""
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    degraded_state = {
        "tier": "KG_DEGRADED",
        "unavailable_services": ["kg"],
        "detected_at": "2026-04-19T20:00:00Z",
    }

    with (
        patch("gsigmad.cli.compute_degradation_state", return_value=degraded_state),
        patch("gsigmad.cli.write_degradation_state"),
        patch(_PATCH_EXP, return_value=_MOCK_EXPS),
        patch(_PATCH_DRIFT, return_value=_MOCK_DRIFT_NOT_TRIGGERED),
    ):
        result = runner.invoke(app, ["--json", "status"], catch_exceptions=False)

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["degradation"]["tier"] == "KG_DEGRADED"
    assert payload["degradation"]["unavailable_services"] == ["kg"]


def test_status_not_initialized(tmp_path: Path, monkeypatch):
    """status in non-gsigmad project exits 1."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 1


def test_status_no_arango(tmp_path: Path, monkeypatch):
    """status works without ArangoDB (falls back to local scan)."""
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    # Use actual get_exp_status_summary but mock check_drift to avoid .agent/ side effects
    with patch(_PATCH_DRIFT, return_value=_MOCK_DRIFT_NOT_TRIGGERED):
        result = runner.invoke(app, ["status"], catch_exceptions=False)

    assert result.exit_code == 0, f"stdout: {result.output}"


def test_status_drift_error_handled(tmp_path: Path, monkeypatch):
    """status handles drift check errors gracefully (e.g., no .agent/ directory)."""
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    with (
        patch(_PATCH_EXP, return_value=_MOCK_EXPS_EMPTY),
        patch(_PATCH_DRIFT, side_effect=Exception("No .agent/ directory")),
    ):
        result = runner.invoke(app, ["status"], catch_exceptions=False)

    assert result.exit_code == 0, f"stdout: {result.output}"
    output_lower = result.output.lower()
    assert "not yet tracked" in output_lower or "drift" in output_lower


def test_offline_lifecycle_smoke(tmp_path: Path, monkeypatch):
    """Offline init -> register -> run -> audit -> status works without external services."""
    monkeypatch.chdir(tmp_path)

    init_result = runner.invoke(app, ["init", str(tmp_path)], catch_exceptions=False)
    assert init_result.exit_code == 0, init_result.output

    register_result = runner.invoke(app, ["register", "--type", "exploratory"], catch_exceptions=False)
    assert register_result.exit_code == 0, register_result.output

    def _gate_loader(module_path, fn_name):
        if fn_name == "validate_data_contract":
            return lambda *args, **kwargs: {"valid": True, "halt_message": None}
        return lambda *args, **kwargs: {"pass": True, "error": None}

    with patch("gsigmad.commands.run._load_gate_fn", side_effect=_gate_loader):
        run_result = runner.invoke(app, ["run", "EXP-1.1"], catch_exceptions=False)
    assert run_result.exit_code == 0, run_result.output

    with patch("gsigmad.commands.audit._load_audit_gate", return_value=lambda claims, verify_citations=True: {"pass": True, "failures": [], "warnings": []}), patch(_PATCH_DRIFT, return_value=_MOCK_DRIFT_NOT_TRIGGERED):
        audit_result = runner.invoke(app, ["audit"], catch_exceptions=False)
        status_result = runner.invoke(app, ["status"], catch_exceptions=False)

    assert audit_result.exit_code == 0, audit_result.output
    assert status_result.exit_code == 0, status_result.output
    assert "EXP-1.1" in status_result.output
    ledger_file = tmp_path / ".gsigmad" / "ledger" / "governance.jsonl"
    assert ledger_file.is_file()
    assert len([line for line in ledger_file.read_text(encoding="utf-8").splitlines() if line.strip()]) >= 5


def test_register_succeeds_when_ledger_append_warns(tmp_path: Path, monkeypatch):
    """Command success is preserved when the ledger append path raises internally."""
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    with patch("gsigmad.hub.ledger.append_w5", side_effect=RuntimeError("boom")):
        result = runner.invoke(app, ["register", "--type", "exploratory"], catch_exceptions=False)

    assert result.exit_code == 0, result.output


def test_status_reports_open_closure_chain(tmp_path: Path, monkeypatch):
    """status surfaces closure state after register/run in JSON mode."""
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    register_result = runner.invoke(app, ["register", "--type", "exploratory"], catch_exceptions=False)
    assert register_result.exit_code == 0, register_result.output

    def _gate_loader2(module_path, fn_name):
        if fn_name == "validate_data_contract":
            return lambda *args, **kwargs: {"valid": True, "halt_message": None}
        return lambda *args, **kwargs: {"pass": True, "error": None}

    with patch("gsigmad.commands.run._load_gate_fn", side_effect=_gate_loader2), patch(_PATCH_DRIFT, return_value=_MOCK_DRIFT_NOT_TRIGGERED):
        run_result = runner.invoke(app, ["run", "EXP-1.1"], catch_exceptions=False)
        status_result = runner.invoke(app, ["--json", "status"], catch_exceptions=False)

    assert run_result.exit_code == 0, run_result.output
    assert status_result.exit_code == 0, status_result.output
    payload = json.loads(status_result.output)
    assert payload["closure"]
    assert payload["closure"][0]["exp_id"] == "EXP-1.1"


def _create_scaffolded_exp(path: Path, exp_id: str, *, scaffold_state: str) -> None:
    exp_path = path / ".gsigmad" / "experiments" / f"{exp_id}.yaml"
    exp_record = {
        "exp_id": exp_id,
        "classification": "EXPLORATORY",
        "status": "planned",
        "scaffold_state": scaffold_state,
        "task_id": "TASK-20.1",
        "prompt_id": "PROMPT-20.1",
        "claims": [],
    }
    exp_path.write_text(yaml.safe_dump(exp_record, default_flow_style=False, sort_keys=False), encoding="utf-8")
    record_chain_event(path, exp_id=exp_id, stage="TASK", artifact_id="TASK-20.1")
    record_chain_event(path, exp_id=exp_id, stage="PROMPT", artifact_id="PROMPT-20.1")
    record_chain_event(path, exp_id=exp_id, stage="EXP", artifact_id=exp_id)


def test_status_shows_scaffolded_planned_experiment(tmp_path: Path, monkeypatch):
    """Status should surface scaffolded planned EXPs through the existing loader and closure summary."""
    _init_project(tmp_path)
    _create_scaffolded_exp(tmp_path, "EXP-20.1", scaffold_state="ready")
    monkeypatch.chdir(tmp_path)

    with patch(_PATCH_DRIFT, return_value=_MOCK_DRIFT_NOT_TRIGGERED):
        result = runner.invoke(app, ["--json", "status"], catch_exceptions=False)

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    experiments = payload["experiments"]["exps"]
    closure = payload["closure"]
    assert any(item["exp_id"] == "EXP-20.1" and item["status"] == "planned" for item in experiments)
    assert any(item["exp_id"] == "EXP-20.1" and item["scaffold_state"] == "ready" for item in experiments)
    assert any(item["exp_id"] == "EXP-20.1" and item["current_stage"] == "EXP" for item in closure)


def test_status_marks_incomplete_scaffold_experiment(tmp_path: Path, monkeypatch):
    """Status should expose EXP-backed scaffold_state markers without introducing a separate registry."""
    _init_project(tmp_path)
    _create_scaffolded_exp(tmp_path, "EXP-20.1", scaffold_state="incomplete")
    monkeypatch.chdir(tmp_path)

    with patch(_PATCH_DRIFT, return_value=_MOCK_DRIFT_NOT_TRIGGERED):
        result = runner.invoke(app, ["status"], catch_exceptions=False)

    assert result.exit_code == 0, result.output
    assert "EXP-20.1" in result.output
    assert "incomplete" in result.output.lower()
