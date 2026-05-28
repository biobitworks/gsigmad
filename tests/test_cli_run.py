"""Tests for gsigmad run command (CLI-03)."""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml
from typer.testing import CliRunner

from gsigmad.cli import app
from gsigmad.governance.receipts import load_stage_receipt

runner = CliRunner()
RATIFIED_PROMOTION_AUTHORITY = "phase20-local-text-classifier-v1"


def _init_project(path: Path) -> None:
    """Helper: initialize a gsigmad project at path."""
    result = runner.invoke(app, ["init", str(path)])
    assert result.exit_code == 0, f"init failed: {result.output}"


def _create_exp(path: Path, exp_id: str, classification: str, **extra) -> Path:
    """Helper: create an EXP YAML file directly."""
    exps_dir = path / ".gsigmad" / "experiments"
    exps_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "exp_id": exp_id,
        "classification": classification,
        "hypothesis": {
            "h0": "No effect",
            "h1": "Effect exists",
            "test": "ttest_ind",
            "alpha": 0.05,
            "mesi": 0.4,
        },
        "power_analysis": {
            "tier": "formula",
            "test_type": "ttest_ind",
            "required_n": 100,
            "effect_size_mesi": 0.4,
            "alpha": 0.05,
            "achieved_power": 0.80,
        },
        "gates": {},
        "claims": [],
    }
    record.update(extra)
    exp_path = exps_dir / f"{exp_id}.yaml"
    exp_path.write_text(yaml.safe_dump(record, default_flow_style=False, sort_keys=False))
    return exp_path


def _mock_gate_pass(*args, **kwargs):
    """Mock gate function that always passes."""
    return {"pass": True, "error": None}


def _mock_gate_fail(*args, **kwargs):
    """Mock gate function that always fails."""
    return {"pass": False, "error": "Test gate failure"}


def _mock_decision_tree_pass(*args, **kwargs):
    """Mock decision_tree validate that returns valid."""
    return {"valid": True, "tree": {}}


def _mock_decision_tree_fail(*args, **kwargs):
    """Mock decision_tree validate that returns invalid."""
    return {"valid": False, "errors": [{"msg": "Invalid tree"}]}


def _mock_data_contract_pass(*args, **kwargs):
    """Mock data_contract that returns valid (uses 'valid' not 'pass')."""
    return {"valid": True, "violations": [], "halt_message": None}


def _mock_data_contract_fail(*args, **kwargs):
    """Mock data_contract that returns invalid."""
    return {"valid": False, "violations": ["Missing field"], "halt_message": "DATA CONTRACT VIOLATION"}


def _load_exp_record(path: Path, exp_id: str) -> dict:
    exp_path = path / ".gsigmad" / "experiments" / f"{exp_id}.yaml"
    return yaml.safe_load(exp_path.read_text(encoding="utf-8"))


def _latest_results_event(path: Path, exp_id: str) -> dict:
    chain_path = path / ".gsigmad" / "closure_chain.json"
    chain_state = json.loads(chain_path.read_text(encoding="utf-8"))
    history = chain_state["chains"][exp_id]["history"]
    results_events = [event for event in history if event["stage"] == "RESULTS"]
    assert results_events, f"No RESULTS events found for {exp_id}"
    return results_events[-1]


def _results_events(path: Path, exp_id: str) -> list[dict]:
    chain_path = path / ".gsigmad" / "closure_chain.json"
    chain_state = json.loads(chain_path.read_text(encoding="utf-8"))
    history = chain_state["chains"][exp_id]["history"]
    return [event for event in history if event["stage"] == "RESULTS"]


def test_run_loads_exp(tmp_path: Path, monkeypatch):
    """gsigmad run EXP-1.1 loads .gsigmad/experiments/EXP-1.1.yaml and executes gates."""
    _init_project(tmp_path)
    _create_exp(tmp_path, "EXP-1.1", "EXPLORATORY",
                data_contract={"interface": "test", "fields": []})
    monkeypatch.chdir(tmp_path)

    def _loader(module_path, fn_name):
        if fn_name == "validate_data_contract":
            return _mock_data_contract_pass
        return _mock_gate_pass

    with patch("gsigmad.commands.run._load_gate_fn", side_effect=_loader):
        result = runner.invoke(app, ["run", "EXP-1.1"], catch_exceptions=False)
    assert result.exit_code == 0, f"stdout: {result.output}"


def test_run_dry_run(tmp_path: Path, monkeypatch):
    """gsigmad run --dry-run EXP-1.1 lists gates without executing, exit code 0."""
    _init_project(tmp_path)
    _create_exp(tmp_path, "EXP-1.1", "CONFIRMATORY")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["run", "--dry-run", "EXP-1.1"], catch_exceptions=False)
    assert result.exit_code == 0, f"stdout: {result.output}"
    # Should mention gates that would execute
    assert "power_analysis" in result.output.lower() or "gate" in result.output.lower()


def test_confirmatory_dry_run_blocks_missing_alpha_mesi_before_execution(tmp_path: Path, monkeypatch):
    """Malformed confirmatory preregistration blocks dry-run without preflight/gates."""
    _init_project(tmp_path)
    exp_path = _create_exp(tmp_path, "EXP-1.1", "CONFIRMATORY")
    record = yaml.safe_load(exp_path.read_text(encoding="utf-8"))
    del record["hypothesis"]["alpha"]
    del record["hypothesis"]["mesi"]
    exp_path.write_text(yaml.safe_dump(record, default_flow_style=False, sort_keys=False), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with patch(
        "gsigmad.commands.run.run_execution_preflight",
        side_effect=AssertionError("dry-run preregistration block must not execute preflight"),
    ), patch("gsigmad.commands.run._load_gate_fn", side_effect=AssertionError("dry run must not execute gates")):
        result = runner.invoke(app, ["--json", "run", "--dry-run", "EXP-1.1"], catch_exceptions=False)

    assert result.exit_code == 1, result.output
    data = json.loads(result.output)
    assert data["error"] == "Experiment preregistration is incomplete"
    assert data["failures"] == [
        "CONFIRMATORY_PREREGISTRATION_MISSING: hypothesis.alpha",
        "CONFIRMATORY_PREREGISTRATION_MISSING: hypothesis.mesi",
    ]
    assert not (tmp_path / ".gsigmad" / "closure_chain.json").exists()


def test_run_gate_failure(tmp_path: Path, monkeypatch):
    """When a gate returns pass=False, run exits code 1."""
    _init_project(tmp_path)
    _create_exp(tmp_path, "EXP-1.1", "EXPLORATORY",
                data_contract={"interface": "test", "fields": [
                    {"name": "x", "type": "float", "required": True}
                ]})
    monkeypatch.chdir(tmp_path)

    def _loader(module_path, fn_name):
        if fn_name == "validate_data_contract":
            return _mock_data_contract_fail
        return _mock_gate_pass

    with patch("gsigmad.commands.run._load_gate_fn", side_effect=_loader):
        result = runner.invoke(app, ["run", "EXP-1.1"], catch_exceptions=False)
    assert result.exit_code == 1, f"expected exit 1, got {result.exit_code}. stdout: {result.output}"


def test_run_all_gates_pass(tmp_path: Path, monkeypatch):
    """When all gates pass, run exits code 0."""
    _init_project(tmp_path)
    _create_exp(tmp_path, "EXP-1.1", "EXPLORATORY",
                data_contract={"interface": "test", "fields": []})
    monkeypatch.chdir(tmp_path)

    def _loader(module_path, fn_name):
        if fn_name == "validate_data_contract":
            return _mock_data_contract_pass
        return _mock_gate_pass

    with patch("gsigmad.commands.run._load_gate_fn", side_effect=_loader):
        result = runner.invoke(app, ["run", "EXP-1.1"], catch_exceptions=False)
    assert result.exit_code == 0, f"stdout: {result.output}"


def test_run_confirmatory_chain(tmp_path: Path, monkeypatch):
    """CONFIRMATORY experiment triggers all 5 gates."""
    _init_project(tmp_path)
    _create_exp(tmp_path, "EXP-1.1", "CONFIRMATORY")
    monkeypatch.chdir(tmp_path)

    gate_calls = []

    def tracking_loader(module_path, fn_name):
        gate_calls.append(fn_name)
        if fn_name == "validate_decision_tree":
            return _mock_decision_tree_pass
        if fn_name == "validate_data_contract":
            return _mock_data_contract_pass
        return _mock_gate_pass

    with patch("gsigmad.commands.run._load_gate_fn", side_effect=tracking_loader):
        result = runner.invoke(app, ["run", "EXP-1.1"], catch_exceptions=False)

    assert result.exit_code == 0, f"stdout: {result.output}"
    assert len(gate_calls) == 7, f"Expected 7 gates, got {len(gate_calls)}: {gate_calls}"


def test_run_exploratory_chain(tmp_path: Path, monkeypatch):
    """EXPLORATORY experiment triggers only data_contract gate."""
    _init_project(tmp_path)
    _create_exp(tmp_path, "EXP-1.1", "EXPLORATORY",
                data_contract={"interface": "test", "fields": []})
    monkeypatch.chdir(tmp_path)

    gate_calls = []

    def tracking_loader(module_path, fn_name):
        gate_calls.append(fn_name)
        if fn_name == "validate_data_contract":
            return _mock_data_contract_pass
        return _mock_gate_pass

    with patch("gsigmad.commands.run._load_gate_fn", side_effect=tracking_loader):
        result = runner.invoke(app, ["run", "EXP-1.1"], catch_exceptions=False)

    assert result.exit_code == 0, f"stdout: {result.output}"
    assert len(gate_calls) == 2, f"Expected 2 gates, got {len(gate_calls)}: {gate_calls}"
    assert "check_null_model_gate" in gate_calls
    assert "validate_data_contract" in gate_calls


def test_run_missing_exp(tmp_path: Path, monkeypatch):
    """run EXP-999.1 (nonexistent) exits code 1 with error."""
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["run", "EXP-999.1"], catch_exceptions=False)
    assert result.exit_code == 1, f"stdout: {result.output}"


def test_run_json_output(tmp_path: Path, monkeypatch):
    """--json produces valid JSON with list of gate results."""
    _init_project(tmp_path)
    _create_exp(tmp_path, "EXP-1.1", "EXPLORATORY",
                data_contract={"interface": "test", "fields": []})
    monkeypatch.chdir(tmp_path)

    def _loader(module_path, fn_name):
        if fn_name == "validate_data_contract":
            return _mock_data_contract_pass
        return _mock_gate_pass

    with patch("gsigmad.commands.run._load_gate_fn", side_effect=_loader):
        result = runner.invoke(app, ["--json", "run", "EXP-1.1"], catch_exceptions=False)
    assert result.exit_code == 0, f"stdout: {result.output}"
    data = json.loads(result.output)
    assert "gates" in data
    assert isinstance(data["gates"], list)


def test_run_json_output_includes_canonical_receipts(tmp_path: Path, monkeypatch):
    """Successful runs emit preflight/execute/validate/summarize receipts."""
    _init_project(tmp_path)
    _create_exp(tmp_path, "EXP-1.1", "EXPLORATORY", data_contract={"interface": "test", "fields": []})
    monkeypatch.chdir(tmp_path)

    def _loader(module_path, fn_name):
        if fn_name == "validate_data_contract":
            return _mock_data_contract_pass
        return _mock_gate_pass

    with patch("gsigmad.commands.run._load_gate_fn", side_effect=_loader):
        result = runner.invoke(app, ["--json", "run", "EXP-1.1"], catch_exceptions=False)

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    receipts = data["receipts"]
    assert receipts["run_id"] == "RUN-EXP-1.1-1"
    assert len(receipts["paths"]) == 4

    loaded = [load_stage_receipt(tmp_path, relpath).stage.value for relpath in receipts["paths"]]
    assert loaded == ["preflight", "execute", "validate", "summarize"]


def test_run_records_closure_results(tmp_path: Path, monkeypatch):
    """Successful run records closure RESULTS state for the experiment."""
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    register_result = runner.invoke(app, ["register", "--type", "exploratory"], catch_exceptions=False)
    assert register_result.exit_code == 0, register_result.output

    def _loader(module_path, fn_name):
        if fn_name == "validate_data_contract":
            return _mock_data_contract_pass
        return _mock_gate_pass

    with patch("gsigmad.commands.run._load_gate_fn", side_effect=_loader):
        result = runner.invoke(app, ["run", "EXP-1.1"], catch_exceptions=False)

    assert result.exit_code == 0, result.output
    chain_file = tmp_path / ".gsigmad" / "closure_chain.json"
    assert chain_file.is_file()
    assert "RESULTS-EXP-1.1-1" in chain_file.read_text(encoding="utf-8")


def test_run_writes_write_once_manifest_and_records_integrity_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _init_project(tmp_path)
    _create_exp(
        tmp_path,
        "EXP-1.1",
        "EXPLORATORY",
        data_contract={"interface": "test", "fields": []},
    )
    monkeypatch.chdir(tmp_path)

    def _loader(module_path, fn_name):
        if fn_name == "validate_data_contract":
            return _mock_data_contract_pass
        return _mock_gate_pass

    with patch("gsigmad.commands.run._load_gate_fn", side_effect=_loader):
        result = runner.invoke(app, ["run", "EXP-1.1"], catch_exceptions=False)

    assert result.exit_code == 0, result.output

    manifest_path = (
        tmp_path
        / ".gsigmad"
        / "manifests"
        / "EXP-1.1"
        / "RESULTS-EXP-1.1-1.manifest.yaml"
    )
    assert manifest_path.is_file()

    results_event = _latest_results_event(tmp_path, "EXP-1.1")
    assert results_event["artifact_id"] == "RESULTS-EXP-1.1-1"
    assert results_event["metadata"]["artifact_integrity_required"] is True
    assert results_event["metadata"]["artifact_integrity_status"] == "verified"

    exp_record = _load_exp_record(tmp_path, "EXP-1.1")
    assert exp_record["status"] == "completed"
    assert exp_record["last_run_id"] == "RESULTS-EXP-1.1-1"


def test_run_blocks_when_manifest_closeout_fails_after_passed_gates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _init_project(tmp_path)
    _create_exp(
        tmp_path,
        "EXP-1.1",
        "EXPLORATORY",
        data_contract={"interface": "test", "fields": []},
    )
    monkeypatch.chdir(tmp_path)

    def _loader(module_path, fn_name):
        if fn_name == "validate_data_contract":
            return _mock_data_contract_pass
        return _mock_gate_pass

    with (
        patch("gsigmad.commands.run._load_gate_fn", side_effect=_loader),
        patch(
            "gsigmad.commands.run.write_run_manifest",
            side_effect=RuntimeError("MANIFEST_WRITE_FAILED"),
        ),
    ):
        result = runner.invoke(app, ["run", "EXP-1.1"], catch_exceptions=False)

    assert result.exit_code == 1, result.output

    exp_record = _load_exp_record(tmp_path, "EXP-1.1")
    assert exp_record["status"] == "blocked"
    assert exp_record["last_run_id"] == "RESULTS-EXP-1.1-1"

    results_event = _latest_results_event(tmp_path, "EXP-1.1")
    assert results_event["artifact_id"] == "RESULTS-EXP-1.1-1"
    assert results_event["metadata"]["artifact_integrity_required"] is True
    assert results_event["metadata"]["artifact_integrity_status"] == "blocked"
    assert results_event["metadata"]["artifact_integrity_error"] == "MANIFEST_WRITE_FAILED"

    chain_state = json.loads((tmp_path / ".gsigmad" / "closure_chain.json").read_text(encoding="utf-8"))
    assert chain_state["chains"]["EXP-1.1"]["terminal_state"] == "BLOCKED"


def test_run_replay_requires_prior_verified_results_baseline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _init_project(tmp_path)
    _create_exp(
        tmp_path,
        "EXP-1.1",
        "EXPLORATORY",
        data_contract={"interface": "test", "fields": []},
    )
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["--json", "run", "--replay", "EXP-1.1"], catch_exceptions=False)

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["error"] == "Replay requires a prior verified RESULTS baseline"


def test_run_replay_records_new_results_event_without_regressing_prior_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _init_project(tmp_path)
    _create_exp(
        tmp_path,
        "EXP-1.1",
        "EXPLORATORY",
        data_contract={"interface": "test", "fields": []},
    )
    monkeypatch.chdir(tmp_path)

    def _loader(module_path, fn_name):
        if fn_name == "validate_data_contract":
            return _mock_data_contract_pass
        return _mock_gate_pass

    with patch("gsigmad.commands.run._load_gate_fn", side_effect=_loader):
        first = runner.invoke(app, ["run", "EXP-1.1"], catch_exceptions=False)
        second = runner.invoke(app, ["--json", "run", "--replay", "EXP-1.1"], catch_exceptions=False)

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output

    replay_payload = json.loads(second.output)
    assert replay_payload["replay"]["replay"] is True
    assert replay_payload["replay"]["replay_source_results_id"] == "RESULTS-EXP-1.1-1"
    assert replay_payload["replay"]["governance_drift"] is False

    events = _results_events(tmp_path, "EXP-1.1")
    assert len(events) == 2
    assert events[0]["artifact_id"] == "RESULTS-EXP-1.1-1"
    assert events[1]["artifact_id"] == "RESULTS-EXP-1.1-2"
    assert events[1]["metadata"]["replay"] is True
    assert events[1]["metadata"]["replay_source_results_id"] == "RESULTS-EXP-1.1-1"

    exp_record = _load_exp_record(tmp_path, "EXP-1.1")
    assert exp_record["last_run_id"] == "RESULTS-EXP-1.1-2"


def test_run_replay_marks_governance_drift_when_manifest_or_gate_results_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _init_project(tmp_path)
    data_path = tmp_path / "data" / "inputs.csv"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text("sample,data\n1,2\n", encoding="utf-8")
    _create_exp(
        tmp_path,
        "EXP-1.1",
        "EXPLORATORY",
        data_contract={"interface": "test", "fields": []},
        data_file="data/inputs.csv",
    )
    monkeypatch.chdir(tmp_path)

    def _loader(module_path, fn_name):
        if fn_name == "validate_data_contract":
            return _mock_data_contract_pass
        return _mock_gate_pass

    with patch("gsigmad.commands.run._load_gate_fn", side_effect=_loader):
        first = runner.invoke(app, ["run", "EXP-1.1"], catch_exceptions=False)
        assert first.exit_code == 0, first.output
        data_path.write_text("sample,data\n1,999\n", encoding="utf-8")
        replay = runner.invoke(app, ["--json", "run", "--replay", "EXP-1.1"], catch_exceptions=False)

    assert replay.exit_code == 0, replay.output
    payload = json.loads(replay.output)
    assert payload["replay"]["status"] == "GOVERNANCE_DRIFT"
    assert payload["replay"]["governance_drift"] is True
    assert payload["replay"]["governance_drift_reasons"]

    results_event = _latest_results_event(tmp_path, "EXP-1.1")
    assert results_event["metadata"]["governance_drift"] is True
    assert results_event["metadata"]["governance_drift_reasons"]


def test_run_replay_writes_replay_identity_and_reverification_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _init_project(tmp_path)
    data_path = tmp_path / "data" / "inputs.csv"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text("sample,data\n1,2\n", encoding="utf-8")
    _create_exp(
        tmp_path,
        "EXP-1.1",
        "EXPLORATORY",
        data_contract={"interface": "test", "fields": []},
        data_file="data/inputs.csv",
    )
    monkeypatch.chdir(tmp_path)

    def _loader(module_path, fn_name):
        if fn_name == "validate_data_contract":
            return _mock_data_contract_pass
        return _mock_gate_pass

    with patch("gsigmad.commands.run._load_gate_fn", side_effect=_loader):
        first = runner.invoke(app, ["run", "EXP-1.1"], catch_exceptions=False)
        assert first.exit_code == 0, first.output
        replay = runner.invoke(app, ["--json", "run", "--replay", "EXP-1.1"], catch_exceptions=False)

    assert replay.exit_code == 0, replay.output
    payload = json.loads(replay.output)
    replay_payload = payload["replay"]
    assert replay_payload["replay_identity_path"]
    assert replay_payload["manifest_diff_path"]
    assert replay_payload["receipt_diff_path"]
    assert replay_payload["reverification_path"]
    assert replay_payload["reverification_status"] == "replay-ok"

    identity_path = tmp_path / replay_payload["replay_identity_path"]
    reverification_path = tmp_path / replay_payload["reverification_path"]
    assert identity_path.is_file()
    assert reverification_path.is_file()

    identity = yaml.safe_load(identity_path.read_text(encoding="utf-8"))
    assert identity["baseline_results_id"] == "RESULTS-EXP-1.1-1"
    assert identity["replay_results_id"] == "RESULTS-EXP-1.1-2"


def test_run_not_initialized(tmp_path: Path, monkeypatch):
    """run in non-gsigmad project exits code 1."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["run", "EXP-1.1"], catch_exceptions=False)
    assert result.exit_code == 1


def test_fdr_gate_in_chain(tmp_path: Path, monkeypatch):
    """CONFIRMATORY EXP with valid fdr_chain passes the fdr_contract gate."""
    _init_project(tmp_path)
    _create_exp(
        tmp_path, "EXP-1.1", "CONFIRMATORY",
        fdr_chain={
            "levels": [{"name": "primary", "threshold": 0.05}],
            "method": "none",
            "tool": "custom",
            "tool_version": "1.0",
        },
    )
    monkeypatch.chdir(tmp_path)

    gate_calls = []

    def tracking_loader(module_path, fn_name):
        gate_calls.append(fn_name)
        if fn_name == "validate_decision_tree":
            return _mock_decision_tree_pass
        if fn_name == "validate_data_contract":
            return _mock_data_contract_pass
        if fn_name == "check_fdr_contract_gate":
            # Use the real gate function
            from gsigmad.governance.gates.fdr_contract import check_fdr_contract_gate
            return check_fdr_contract_gate
        return _mock_gate_pass

    with patch("gsigmad.commands.run._load_gate_fn", side_effect=tracking_loader):
        result = runner.invoke(app, ["--json", "run", "EXP-1.1"], catch_exceptions=False)

    assert result.exit_code == 0, f"stdout: {result.output}"
    data = json.loads(result.output)
    # Verify fdr_contract gate is in the results
    gate_names = [g["gate"] for g in data["gates"]]
    assert "fdr_contract" in gate_names
    fdr_result = next(g for g in data["gates"] if g["gate"] == "fdr_contract")
    assert fdr_result["pass"] is True


def test_null_model_gate_in_chain(tmp_path, monkeypatch):
    """CONFIRMATORY EXP with valid null_model passes the null_model gate."""
    _init_project(tmp_path)
    _create_exp(
        tmp_path, "EXP-1.1", "CONFIRMATORY",
        null_model={
            "strategy": "permutation",
            "n_permutations": 1000,
            "baseline_description": "Random shuffling of target labels",
            "exchangeability_assumption": "Target labels are exchangeable under null",
            "novel_space": False,
        },
    )
    monkeypatch.chdir(tmp_path)

    gate_calls = []

    def tracking_loader(module_path, fn_name):
        gate_calls.append(fn_name)
        if fn_name == "validate_decision_tree":
            return _mock_decision_tree_pass
        if fn_name == "validate_data_contract":
            return _mock_data_contract_pass
        if fn_name == "check_null_model_gate":
            from gsigmad.governance.gates.null_model import check_null_model_gate
            return check_null_model_gate
        return _mock_gate_pass

    with patch("gsigmad.commands.run._load_gate_fn", side_effect=tracking_loader):
        result = runner.invoke(app, ["--json", "run", "EXP-1.1"], catch_exceptions=False)

    assert result.exit_code == 0, f"stdout: {result.output}"
    data = json.loads(result.output)
    gate_names = [g["gate"] for g in data["gates"]]
    assert "null_model" in gate_names
    nm_result = next(g for g in data["gates"] if g["gate"] == "null_model")
    assert nm_result["pass"] is True


def test_confirmatory_preflight_blocks_on_claim_lint_failure(tmp_path: Path, monkeypatch):
    """Confirmatory runs must stop before gate execution when claim lint fails in preflight."""
    _init_project(tmp_path)
    _create_exp(
        tmp_path,
        "EXP-1.1",
        "CONFIRMATORY",
        claims=[{"text": "Primary outcome improved (p < 0.01)."}],
        scaffold_state="ready",
    )
    monkeypatch.chdir(tmp_path)

    with patch(
        "gsigmad.commands.run.run_execution_preflight",
        return_value={
            "passed": False,
            "failures": ["STAT_RIGOR_VIOLATION: missing effect size"],
            "warnings": [],
            "checks": [],
            "authority": None,
            "details": {"hypothesis_promotion": []},
        },
    ), patch("gsigmad.commands.run._load_gate_fn", side_effect=AssertionError("gate chain should not run")):
        result = runner.invoke(app, ["--json", "run", "EXP-1.1"], catch_exceptions=False)

    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["preflight"]["failures"] == ["STAT_RIGOR_VIOLATION: missing effect size"]
    assert data["preflight"]["passed"] is False
    exp_record = yaml.safe_load((tmp_path / ".gsigmad" / "experiments" / "EXP-1.1.yaml").read_text(encoding="utf-8"))
    assert exp_record.get("status") != "completed"
    assert "last_run_id" not in exp_record
    chain_file = tmp_path / ".gsigmad" / "closure_chain.json"
    if chain_file.exists():
        assert "RESULTS-EXP-1.1-1" not in chain_file.read_text(encoding="utf-8")


def test_confirmatory_promotion_violation_requires_exp_ratification(tmp_path: Path, monkeypatch):
    """Only the exact EXP-level promotion_authority ratifies a blocking promotion violation."""
    _init_project(tmp_path)
    _create_exp(
        tmp_path,
        "EXP-1.1",
        "CONFIRMATORY",
        claims=[{"text": "We hypothesize this treatment could improve response rates.", "evidence_class": "MEASURED"}],
        scaffold_state="ready",
        status="planned",
    )
    monkeypatch.chdir(tmp_path)

    def fake_preflight(exp_record: dict) -> dict:
        authority = exp_record.get("promotion_authority")
        if authority == RATIFIED_PROMOTION_AUTHORITY:
            return {
                "passed": False,
                "failures": [
                    "HYPOTHESIS_PROMOTION_VIOLATION: claim[0] declares MEASURED above detected HYPOTHESIS"
                ],
                "warnings": [],
                "checks": [],
                "authority": authority,
                "details": {
                    "hypothesis_promotion": [
                        {
                            "claim_index": 0,
                            "authority": authority,
                            "declared_tier": "MEASURED",
                            "detected_tier": "HYPOTHESIS",
                            "ratified": True,
                        }
                    ]
                },
            }
        return {
            "passed": True,
            "failures": [],
            "warnings": [
                "HYPOTHESIS_PROMOTION_UNRATIFIED: claim[0] declares MEASURED above detected HYPOTHESIS"
            ],
            "checks": [],
            "authority": authority,
            "details": {
                "hypothesis_promotion": [
                    {
                        "claim_index": 0,
                        "authority": authority,
                        "declared_tier": "MEASURED",
                        "detected_tier": "HYPOTHESIS",
                        "ratified": False,
                    }
                ]
            },
        }

    def _loader(module_path, fn_name):
        if fn_name == "validate_decision_tree":
            return _mock_decision_tree_pass
        if fn_name == "validate_data_contract":
            return _mock_data_contract_pass
        return _mock_gate_pass

    exp_path = tmp_path / ".gsigmad" / "experiments" / "EXP-1.1.yaml"
    with patch("gsigmad.commands.run.run_execution_preflight", side_effect=fake_preflight), patch(
        "gsigmad.commands.run._load_gate_fn", side_effect=_loader
    ):
        first = runner.invoke(app, ["--json", "run", "EXP-1.1"], catch_exceptions=False)
    assert first.exit_code == 0, first.output
    first_data = json.loads(first.output)
    assert first_data["preflight"]["warnings"] == [
        "HYPOTHESIS_PROMOTION_UNRATIFIED: claim[0] declares MEASURED above detected HYPOTHESIS"
    ]
    assert first_data["preflight"]["passed"] is True

    record = yaml.safe_load(exp_path.read_text(encoding="utf-8"))
    record["promotion_authority"] = RATIFIED_PROMOTION_AUTHORITY
    record["status"] = "planned"
    record.pop("last_run_id", None)
    exp_path.write_text(yaml.safe_dump(record, default_flow_style=False, sort_keys=False), encoding="utf-8")

    with patch("gsigmad.commands.run.run_execution_preflight", side_effect=fake_preflight), patch(
        "gsigmad.commands.run._load_gate_fn", side_effect=AssertionError("gate chain should not run")
    ):
        second = runner.invoke(app, ["--json", "run", "EXP-1.1"], catch_exceptions=False)
    assert second.exit_code == 1, second.output
    second_data = json.loads(second.output)
    assert second_data["preflight"]["failures"] == [
        "HYPOTHESIS_PROMOTION_VIOLATION: claim[0] declares MEASURED above detected HYPOTHESIS"
    ]
    assert second_data["preflight"]["authority"] == RATIFIED_PROMOTION_AUTHORITY


def test_exploratory_preflight_warns_and_continues(tmp_path: Path, monkeypatch):
    """Exploratory runs surface preflight advisories but still execute the minimal gate chain."""
    _init_project(tmp_path)
    _create_exp(
        tmp_path,
        "EXP-1.1",
        "EXPLORATORY",
        claims=[{"text": "We hypothesize this treatment could improve response rates."}],
        data_contract={"interface": "test", "fields": []},
        scaffold_state="ready",
    )
    monkeypatch.chdir(tmp_path)

    def _loader(module_path, fn_name):
        if fn_name == "validate_data_contract":
            return _mock_data_contract_pass
        return _mock_gate_pass

    with patch(
        "gsigmad.commands.run.run_execution_preflight",
        return_value={
            "passed": False,
            "failures": ["STAT_RIGOR_VIOLATION: missing effect size"],
            "warnings": [
                "HYPOTHESIS_PROMOTION_UNRATIFIED: claim[0] declares INFERRED above detected HYPOTHESIS"
            ],
            "checks": [],
            "authority": None,
            "details": {"hypothesis_promotion": []},
        },
    ), patch("gsigmad.commands.run._load_gate_fn", side_effect=_loader):
        result = runner.invoke(app, ["--json", "run", "EXP-1.1"], catch_exceptions=False)

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["preflight"]["failures"] == ["STAT_RIGOR_VIOLATION: missing effect size"]
    assert data["preflight"]["warnings"] == [
        "HYPOTHESIS_PROMOTION_UNRATIFIED: claim[0] declares INFERRED above detected HYPOTHESIS"
    ]
    assert data["passed"] is True
    gate_names = [gate["gate"] for gate in data["gates"]]
    assert gate_names == ["null_model", "data_contract"]


def test_run_refuses_incomplete_scaffold_experiment(tmp_path: Path, monkeypatch):
    """Run refuses scaffold_state=incomplete experiments before preflight or gate execution."""
    _init_project(tmp_path)
    _create_exp(
        tmp_path,
        "EXP-1.1",
        "CONFIRMATORY",
        scaffold_state="incomplete",
        scaffold_missing=["journal_row"],
        scaffold_warnings=["W5_APPEND_FAILED"],
        status="planned",
    )
    monkeypatch.chdir(tmp_path)

    with patch("gsigmad.commands.run.run_execution_preflight", side_effect=AssertionError("preflight should not run")):
        result = runner.invoke(app, ["--json", "run", "EXP-1.1"], catch_exceptions=False)

    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["error"] == "Experiment scaffold is not runnable"
    assert data["scaffold_state"] == "incomplete"
    assert data["scaffold_missing"] == ["journal_row"]
    assert data["scaffold_warnings"] == ["W5_APPEND_FAILED"]
    exp_record = yaml.safe_load((tmp_path / ".gsigmad" / "experiments" / "EXP-1.1.yaml").read_text(encoding="utf-8"))
    assert exp_record["status"] == "planned"
    assert "last_run_id" not in exp_record


def test_dry_run_lists_preflight_without_mutating_gate_chain(tmp_path: Path, monkeypatch):
    """Dry run reports preflight separately from GATE_CHAIN and does not execute gates."""
    _init_project(tmp_path)
    _create_exp(tmp_path, "EXP-1.1", "CONFIRMATORY", scaffold_state="ready")
    monkeypatch.chdir(tmp_path)

    with patch(
        "gsigmad.commands.run.run_execution_preflight",
        return_value={
            "passed": True,
            "warnings": [],
            "failures": [],
            "checks": [],
        },
    ), patch("gsigmad.commands.run._load_gate_fn", side_effect=AssertionError("dry run must not execute gates")):
        result = runner.invoke(app, ["--json", "run", "--dry-run", "EXP-1.1"], catch_exceptions=False)

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["preflight_checks"] == ["claim_lint", "hypothesis_promotion"]
    assert "gates" in data
    assert [gate["gate"] for gate in data["gates"]] == [
        "power_analysis",
        "decision_tree",
        "fdr_contract",
        "null_model",
        "temporal_integrity",
        "red_team",
        "data_contract",
    ]


def test_run_refuses_unknown_non_ready_scaffold_state(tmp_path: Path, monkeypatch):
    """Unknown persisted scaffold_state values are treated as non-runnable contract drift."""
    _init_project(tmp_path)
    _create_exp(
        tmp_path,
        "EXP-1.1",
        "EXPLORATORY",
        scaffold_state="drifted",
        scaffold_missing=["manifest_placeholder"],
        scaffold_warnings=["unexpected_state"],
        status="planned",
    )
    monkeypatch.chdir(tmp_path)

    with patch("gsigmad.commands.run.run_execution_preflight", side_effect=AssertionError("preflight should not run")):
        result = runner.invoke(app, ["--json", "run", "EXP-1.1"], catch_exceptions=False)

    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["error"] == "Experiment scaffold is not runnable"
    assert data["scaffold_state"] == "drifted"
    assert data["detail"] == "Non-ready scaffold_state values are blocked in Phase 20"
