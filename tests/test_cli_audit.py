"""Tests for gsigmad audit command (CLI-04)."""
import json
from pathlib import Path
from unittest.mock import patch

import yaml
from typer.testing import CliRunner

from gsigmad.cli import app
from gsigmad.governance.artifact_integrity import write_run_manifest
from gsigmad.governance.receipts import write_stage_receipt

runner = CliRunner()


def _init_project(path: Path) -> None:
    """Helper: initialize a gsigmad project at path."""
    result = runner.invoke(app, ["init", str(path)])
    assert result.exit_code == 0, f"init failed: {result.output}"


def _create_exp(
    path: Path,
    exp_id: str,
    classification: str,
    claims: list | None = None,
    **extra,
) -> Path:
    """Helper: create an EXP YAML file with optional claims."""
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
        "claims": claims if claims is not None else [],
    }
    record.update(extra)
    exp_path = exps_dir / f"{exp_id}.yaml"
    exp_path.write_text(yaml.safe_dump(record, default_flow_style=False, sort_keys=False))
    return exp_path


def _mock_audit_pass(claims, verify_citations=True):
    """Mock audit_claims_gate that returns all pass."""
    return {"pass": True, "failures": [], "warnings": []}


def _mock_audit_fail(claims, verify_citations=True):
    """Mock audit_claims_gate that returns failures."""
    return {
        "pass": False,
        "failures": [
            {
                "claim_index": 0,
                "text": "test claim",
                "error": "MISSING_EFFECT_SIZE",
            }
        ],
        "warnings": [],
    }


def _load_exp(path: Path, exp_id: str) -> dict:
    exp_path = path / ".gsigmad" / "experiments" / f"{exp_id}.yaml"
    return yaml.safe_load(exp_path.read_text(encoding="utf-8"))


def _prepare_integrity_inputs(path: Path, exp_id: str) -> None:
    script_path = path / "scripts" / f"{exp_id}_analysis.py"
    data_path = path / "data" / "inputs.csv"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text("print('analysis')\n", encoding="utf-8")
    data_path.write_text("sample,data\n1,2\n", encoding="utf-8")


def _write_results_chain(
    path: Path,
    exp_id: str,
    *,
    required: bool,
    results_id: str | None = None,
    manifest_relpath: str | None = None,
    artifact_integrity_status: str | None = None,
    receipt_run_id: str | None = None,
    receipt_relpaths: list[str] | None = None,
) -> None:
    results_id = results_id or f"RESULTS-{exp_id}-1"
    metadata = {}
    if required:
        metadata["artifact_integrity_required"] = True
        if artifact_integrity_status is not None:
            metadata["artifact_integrity_status"] = artifact_integrity_status
        if manifest_relpath is not None:
            metadata["manifest_relpath"] = manifest_relpath
        if receipt_run_id is not None:
            metadata["receipt_run_id"] = receipt_run_id
        if receipt_relpaths is not None:
            metadata["receipt_relpaths"] = receipt_relpaths

    payload = {
        "schema_version": 1,
        "chains": {
            exp_id: {
                "exp_id": exp_id,
                "task_id": None,
                "prompt_id": None,
                "results_id": results_id,
                "rt_id": None,
                "rem_id": None,
                "lab_notebook_entry": None,
                "current_stage": "RESULTS",
                "terminal_state": "COMPLETED",
                "history": [
                    {
                        "timestamp": "2026-04-10T00:00:00+00:00",
                        "stage": "RESULTS",
                        "artifact_id": results_id,
                        "metadata": metadata,
                    }
                ],
            }
        },
        "updated_at": "2026-04-10T00:00:00+00:00",
    }
    chain_path = path / ".gsigmad" / "closure_chain.json"
    chain_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _prepare_required_manifest(
    path: Path,
    exp_id: str = "EXP-1.1",
    *,
    claims: list | None = None,
) -> tuple[dict, dict]:
    _init_project(path)
    _create_exp(
        path,
        exp_id,
        "EXPLORATORY",
        claims=claims,
        data_file="data/inputs.csv",
    )
    _prepare_integrity_inputs(path, exp_id)
    exp_record = _load_exp(path, exp_id)
    manifest = write_run_manifest(path, exp_record=exp_record, results_id=f"RESULTS-{exp_id}-1")
    _write_results_chain(
        path,
        exp_id,
        required=True,
        manifest_relpath=manifest["manifest_relpath"],
        artifact_integrity_status="verified",
    )
    return exp_record, manifest


def test_audit_validates_claims(tmp_path: Path, monkeypatch):
    """gsigmad audit EXP-1.1 extracts claims from EXP YAML and runs audit_claims_gate."""
    _init_project(tmp_path)
    _create_exp(tmp_path, "EXP-1.1", "CONFIRMATORY", claims=[
        {"text": "Treatment improved outcome. Cohen's d = 0.5 (95% CI: [0.2, 0.8]). p < 0.01."}
    ])
    monkeypatch.chdir(tmp_path)

    with patch("gsigmad.commands.audit._load_audit_gate", return_value=_mock_audit_pass):
        result = runner.invoke(app, ["audit", "EXP-1.1"], catch_exceptions=False)
    assert result.exit_code == 0, f"stdout: {result.output}"


def test_audit_skip_citations(tmp_path: Path, monkeypatch):
    """gsigmad audit --skip-citations EXP-1.1 passes verify_citations=False."""
    _init_project(tmp_path)
    _create_exp(tmp_path, "EXP-1.1", "CONFIRMATORY", claims=[
        {"text": "Some claim text."}
    ])
    monkeypatch.chdir(tmp_path)

    captured_kwargs = {}

    def tracking_audit(claims, verify_citations=True):
        captured_kwargs["verify_citations"] = verify_citations
        return {"pass": True, "failures": [], "warnings": []}

    with patch("gsigmad.commands.audit._load_audit_gate", return_value=tracking_audit):
        result = runner.invoke(
            app, ["audit", "--skip-citations", "EXP-1.1"], catch_exceptions=False,
        )
    assert result.exit_code == 0, f"stdout: {result.output}"
    assert captured_kwargs.get("verify_citations") is False, (
        f"Expected verify_citations=False, got {captured_kwargs}"
    )


def test_audit_all_experiments(tmp_path: Path, monkeypatch):
    """gsigmad audit (no EXP ID) scans all experiments in .gsigmad/experiments/."""
    _init_project(tmp_path)
    _create_exp(tmp_path, "EXP-1.1", "EXPLORATORY", claims=[
        {"text": "Claim 1."}
    ])
    _create_exp(tmp_path, "EXP-1.2", "CONFIRMATORY", claims=[
        {"text": "Claim 2."}
    ])
    monkeypatch.chdir(tmp_path)

    call_count = {"n": 0}

    def counting_audit(claims, verify_citations=True):
        call_count["n"] += 1
        return {"pass": True, "failures": [], "warnings": []}

    with patch("gsigmad.commands.audit._load_audit_gate", return_value=counting_audit):
        result = runner.invoke(app, ["audit"], catch_exceptions=False)
    assert result.exit_code == 0, f"stdout: {result.output}"
    assert call_count["n"] == 2, f"Expected 2 audit calls, got {call_count['n']}"


def test_audit_no_claims(tmp_path: Path, monkeypatch):
    """EXP with empty claims list returns pass with info message."""
    _init_project(tmp_path)
    _create_exp(tmp_path, "EXP-1.1", "EXPLORATORY", claims=[])
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["audit", "EXP-1.1"], catch_exceptions=False)
    assert result.exit_code == 0, f"stdout: {result.output}"
    assert "no claims" in result.output.lower() or "0 claims" in result.output.lower()


def test_audit_failures_exit_1(tmp_path: Path, monkeypatch):
    """audit exits 1 when claims fail validation."""
    _init_project(tmp_path)
    _create_exp(tmp_path, "EXP-1.1", "CONFIRMATORY", claims=[
        {"text": "p < 0.05 but no effect size reported."}
    ])
    monkeypatch.chdir(tmp_path)

    with patch("gsigmad.commands.audit._load_audit_gate", return_value=_mock_audit_fail):
        result = runner.invoke(app, ["audit", "EXP-1.1"], catch_exceptions=False)
    assert result.exit_code == 1, f"expected exit 1, got {result.exit_code}. stdout: {result.output}"


def test_audit_json_output(tmp_path: Path, monkeypatch):
    """--json produces valid JSON with pass, failures, warnings."""
    _init_project(tmp_path)
    _create_exp(tmp_path, "EXP-1.1", "EXPLORATORY", claims=[
        {"text": "Some claim."}
    ])
    monkeypatch.chdir(tmp_path)

    with patch("gsigmad.commands.audit._load_audit_gate", return_value=_mock_audit_pass):
        result = runner.invoke(app, ["--json", "audit", "EXP-1.1"], catch_exceptions=False)
    assert result.exit_code == 0, f"stdout: {result.output}"
    data = json.loads(result.output)
    assert "experiments" in data
    assert isinstance(data["experiments"], list)
    exp_result = data["experiments"][0]
    assert "pass" in exp_result
    assert "failures" in exp_result
    assert "integrity" in exp_result


def test_audit_not_initialized(tmp_path: Path, monkeypatch):
    """audit in non-gsigmad project exits 1."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["audit", "EXP-1.1"], catch_exceptions=False)
    assert result.exit_code == 1


def test_audit_missing_exp(tmp_path: Path, monkeypatch):
    """audit EXP-999.1 exits 1 with error message."""
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["audit", "EXP-999.1"], catch_exceptions=False)
    assert result.exit_code == 1


def test_audit_integrity_verifies_real_manifest(tmp_path: Path, monkeypatch) -> None:
    _, manifest = _prepare_required_manifest(
        tmp_path,
        claims=[{"text": "Claim 1."}],
    )
    monkeypatch.chdir(tmp_path)

    with patch("gsigmad.commands.audit._load_audit_gate", return_value=_mock_audit_pass):
        result = runner.invoke(app, ["--json", "audit", "EXP-1.1"], catch_exceptions=False)

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    integrity = payload["experiments"][0]["integrity"]
    assert integrity["pass"] is True
    assert integrity["status"] == "verified"
    assert integrity["manifest_path"] == manifest["manifest_relpath"]


def test_audit_json_includes_receipt_visibility_when_available(tmp_path: Path, monkeypatch) -> None:
    _init_project(tmp_path)
    _create_exp(tmp_path, "EXP-1.1", "EXPLORATORY", claims=[])
    _prepare_integrity_inputs(tmp_path, "EXP-1.1")
    exp_record = _load_exp(tmp_path, "EXP-1.1")
    manifest = write_run_manifest(tmp_path, exp_record=exp_record, results_id="RESULTS-EXP-1.1-1")
    receipt = write_stage_receipt(
        tmp_path,
        {
            "run_id": "RUN-EXP-1.1-1",
            "stage": "summarize",
            "phase": "26",
            "wave": "2",
            "lane": "sidecar-parallel",
            "required_inputs": [manifest["manifest_relpath"]],
            "immutable_inputs_hash": "sha256:abc123",
            "outputs": [{"path": manifest["manifest_relpath"], "kind": "manifest"}],
            "status": "pass",
            "blocked_class": None,
            "resume_point": "interpret/escalate",
            "retry_policy": "bounded-local",
            "escalation_trigger": None,
            "upstream_receipts": [],
        },
    )
    _write_results_chain(
        tmp_path,
        "EXP-1.1",
        required=True,
        manifest_relpath=manifest["manifest_relpath"],
        artifact_integrity_status="verified",
        receipt_run_id="RUN-EXP-1.1-1",
        receipt_relpaths=[receipt["receipt_relpath"]],
    )
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["--json", "audit", "EXP-1.1"], catch_exceptions=False)
    assert result.exit_code == 0, result.output

    data = json.loads(result.output)
    receipts = data["experiments"][0]["receipts"]
    assert receipts["available"] is True
    assert receipts["run_id"] == "RUN-EXP-1.1-1"
    assert receipts["stages"] == ["summarize"]


def test_audit_integrity_fails_when_required_manifest_is_missing(tmp_path: Path, monkeypatch) -> None:
    _init_project(tmp_path)
    _create_exp(
        tmp_path,
        "EXP-1.1",
        "EXPLORATORY",
        claims=[{"text": "Claim 1."}],
        data_file="data/inputs.csv",
    )
    _prepare_integrity_inputs(tmp_path, "EXP-1.1")
    _write_results_chain(
        tmp_path,
        "EXP-1.1",
        required=True,
        manifest_relpath=".gsigmad/manifests/EXP-1.1/RESULTS-EXP-1.1-1.manifest.yaml",
        artifact_integrity_status="verified",
    )
    monkeypatch.chdir(tmp_path)

    with patch("gsigmad.commands.audit._load_audit_gate", return_value=_mock_audit_pass):
        result = runner.invoke(app, ["--json", "audit", "EXP-1.1"], catch_exceptions=False)

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    integrity = payload["experiments"][0]["integrity"]
    assert integrity["pass"] is False
    assert integrity["status"] == "missing"


def test_audit_integrity_fails_on_corrupt_manifest_payload(tmp_path: Path, monkeypatch) -> None:
    _init_project(tmp_path)
    _create_exp(
        tmp_path,
        "EXP-1.1",
        "EXPLORATORY",
        claims=[{"text": "Claim 1."}],
        data_file="data/inputs.csv",
    )
    _prepare_integrity_inputs(tmp_path, "EXP-1.1")
    manifest_path = tmp_path / ".gsigmad" / "manifests" / "EXP-1.1" / "RESULTS-EXP-1.1-1.manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("schema_version: [\n", encoding="utf-8")
    _write_results_chain(
        tmp_path,
        "EXP-1.1",
        required=True,
        manifest_relpath=manifest_path.relative_to(tmp_path).as_posix(),
        artifact_integrity_status="verified",
    )
    monkeypatch.chdir(tmp_path)

    with patch("gsigmad.commands.audit._load_audit_gate", return_value=_mock_audit_pass):
        result = runner.invoke(app, ["--json", "audit", "EXP-1.1"], catch_exceptions=False)

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    integrity = payload["experiments"][0]["integrity"]
    assert integrity["pass"] is False
    assert integrity["status"] == "corrupt"


def test_audit_integrity_fails_when_manifest_references_missing_input(tmp_path: Path, monkeypatch) -> None:
    _, manifest = _prepare_required_manifest(
        tmp_path,
        claims=[{"text": "Claim 1."}],
    )
    (tmp_path / "data" / "inputs.csv").unlink()
    monkeypatch.chdir(tmp_path)

    with patch("gsigmad.commands.audit._load_audit_gate", return_value=_mock_audit_pass):
        result = runner.invoke(app, ["--json", "audit", "EXP-1.1"], catch_exceptions=False)

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    integrity = payload["experiments"][0]["integrity"]
    assert integrity["pass"] is False
    assert integrity["status"] == "mismatch"
    assert integrity["errors"][0]["code"] == "INPUT_MISSING"
    assert integrity["manifest_path"] == manifest["manifest_relpath"]


def test_audit_integrity_fails_on_sha_mismatch(tmp_path: Path, monkeypatch) -> None:
    _prepare_required_manifest(
        tmp_path,
        claims=[{"text": "Claim 1."}],
    )
    (tmp_path / "data" / "inputs.csv").write_text("sample,data\n1,999\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with patch("gsigmad.commands.audit._load_audit_gate", return_value=_mock_audit_pass):
        result = runner.invoke(app, ["--json", "audit", "EXP-1.1"], catch_exceptions=False)

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    integrity = payload["experiments"][0]["integrity"]
    assert integrity["pass"] is False
    assert integrity["status"] == "mismatch"
    assert integrity["errors"][0]["code"] == "SHA_MISMATCH"


def test_audit_integrity_verifies_required_manifest_even_when_no_claims_exist(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _, manifest = _prepare_required_manifest(tmp_path, claims=[])
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["--json", "audit", "EXP-1.1"], catch_exceptions=False)

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    exp_result = payload["experiments"][0]
    assert exp_result["note"] == "No claims to audit."
    assert exp_result["integrity"]["pass"] is True
    assert exp_result["integrity"]["status"] == "verified"
    assert exp_result["integrity"]["manifest_path"] == manifest["manifest_relpath"]


def test_audit_integrity_skips_placeholder_only_legacy_record(tmp_path: Path, monkeypatch) -> None:
    _init_project(tmp_path)
    _create_exp(tmp_path, "EXP-1.1", "EXPLORATORY", claims=[])
    placeholder = tmp_path / ".gsigmad" / "manifests" / "EXP-1.1" / "MANIFEST.placeholder.yaml"
    placeholder.parent.mkdir(parents=True, exist_ok=True)
    placeholder.write_text("placeholder: true\n", encoding="utf-8")
    _write_results_chain(tmp_path, "EXP-1.1", required=False)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["--json", "audit", "EXP-1.1"], catch_exceptions=False)

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    integrity = payload["experiments"][0]["integrity"]
    assert integrity["pass"] is True
    assert integrity["status"] == "unavailable"
    assert integrity["advisory"] is True
    assert integrity["manifest_path"] == placeholder.relative_to(tmp_path).as_posix()


def test_audit_ledger_mode_passes(tmp_path: Path, monkeypatch):
    """audit --ledger verifies the W5 chain and exits 0 when intact."""
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    runner.invoke(app, ["register", "--type", "exploratory"], catch_exceptions=False)
    result = runner.invoke(app, ["audit", "--ledger"], catch_exceptions=False)

    assert result.exit_code == 0, result.output
    assert "ledger ok" in result.output.lower() or "verified" in result.output.lower()


def test_audit_ledger_mode_detects_tampering(tmp_path: Path, monkeypatch):
    """audit --ledger exits 1 when a ledger line is modified post hoc."""
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    runner.invoke(app, ["register", "--type", "exploratory"], catch_exceptions=False)

    ledger_file = tmp_path / ".gsigmad" / "ledger" / "governance.jsonl"
    tampered = ledger_file.read_text(encoding="utf-8").replace("pre_register_experiment", "tampered_action")
    ledger_file.write_text(tampered, encoding="utf-8")

    result = runner.invoke(app, ["audit", "--ledger"], catch_exceptions=False)
    assert result.exit_code == 1, result.output
    assert "ledger failed" in result.output.lower() or "hash_mismatch" in result.output.lower()


# -- Plan 02: --fdr-consistency and --traits CLI flags --


def _create_exp_with_fdr(path: Path, exp_id: str, fdr_chain: dict) -> Path:
    """Helper: create a CONFIRMATORY EXP YAML with fdr_chain."""
    exps_dir = path / ".gsigmad" / "experiments"
    exps_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "exp_id": exp_id,
        "classification": "CONFIRMATORY",
        "hypothesis": {
            "h0": "No effect",
            "h1": "Effect exists",
            "test": "ttest_ind",
            "alpha": 0.05,
            "mesi": 0.4,
        },
        "fdr_chain": fdr_chain,
        "claims": [],
    }
    exp_path = exps_dir / f"{exp_id}.yaml"
    exp_path.write_text(yaml.safe_dump(record, default_flow_style=False, sort_keys=False))
    return exp_path


def test_fdr_consistency_cli_flag(tmp_path: Path, monkeypatch):
    """gsigmad audit --fdr-consistency --json returns JSON with fdr_consistency key."""
    _init_project(tmp_path)
    chain = {
        "levels": [
            {"name": "PSM", "threshold": 0.01},
            {"name": "peptide", "threshold": 0.01},
        ],
        "method": "fdr_bh",
        "tool": "Percolator",
        "tool_version": "3.06.1",
    }
    _create_exp_with_fdr(tmp_path, "EXP-1.1", chain)
    _create_exp_with_fdr(tmp_path, "EXP-1.2", chain)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["--json", "audit", "--fdr-consistency"], catch_exceptions=False)
    assert result.exit_code == 0, f"stdout: {result.output}"
    data = json.loads(result.output)
    assert "fdr_consistency" in data
    assert data["fdr_consistency"]["consistent"] is True


def test_fdr_consistency_cli_inconsistent(tmp_path: Path, monkeypatch):
    """gsigmad audit --fdr-consistency exits 1 with inconsistency details."""
    _init_project(tmp_path)
    chain_a = {
        "levels": [
            {"name": "PSM", "threshold": 0.01},
            {"name": "peptide", "threshold": 0.01},
        ],
        "method": "fdr_bh",
        "tool": "Percolator",
        "tool_version": "3.06.1",
    }
    chain_b = {
        "levels": [
            {"name": "PSM", "threshold": 0.01},
            {"name": "peptide", "threshold": 0.05},
        ],
        "method": "fdr_bh",
        "tool": "Percolator",
        "tool_version": "3.06.1",
    }
    _create_exp_with_fdr(tmp_path, "EXP-1.1", chain_a)
    _create_exp_with_fdr(tmp_path, "EXP-1.2", chain_b)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["--json", "audit", "--fdr-consistency"], catch_exceptions=False)
    assert result.exit_code == 1, f"stdout: {result.output}"
    data = json.loads(result.output)
    assert data["fdr_consistency"]["consistent"] is False
    assert len(data["fdr_consistency"]["inconsistencies"]) >= 1


def test_traits_cli_flag(tmp_path: Path, monkeypatch):
    """gsigmad audit --traits --json returns JSON with traits_coverage key."""
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["--json", "audit", "--traits"], catch_exceptions=False)
    assert result.exit_code == 0, f"stdout: {result.output}"
    data = json.loads(result.output)
    assert "traits_coverage" in data
    assert "covered" in data["traits_coverage"]
    assert "uncovered" in data["traits_coverage"]
