"""Contract tests for Phase 22 artifact integrity helpers."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from gsigmad.cli import app
from gsigmad.governance.artifact_integrity import (
    build_frozen_governance_payload,
    compare_run_manifests,
    collect_immutable_inputs,
    verify_run_manifest,
    write_run_manifest,
)
from gsigmad.hub.ledger import hash_payload

runner = CliRunner()


def _init_project(path: Path) -> None:
    result = runner.invoke(app, ["init", str(path)], catch_exceptions=False)
    assert result.exit_code == 0, result.output


def _scaffold_experiment(project_root: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, dict]:
    monkeypatch.chdir(project_root)
    result = runner.invoke(
        app,
        ["--json", "scaffold", "--type", "exploratory"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output

    exp_id = yaml.safe_load(result.output)["exp_id"]
    exp_path = project_root / ".gsigmad" / "experiments" / f"{exp_id}.yaml"
    record = yaml.safe_load(exp_path.read_text(encoding="utf-8"))
    return exp_id, record


def _write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_frozen_governance_payload_excludes_mutable_fields() -> None:
    exp_record = {
        "exp_id": "EXP-22.1",
        "classification": "CONFIRMATORY",
        "status": "completed",
        "created_at": "2026-04-09T00:00:00+00:00",
        "last_run_id": "RESULTS-EXP-22.1-7",
        "promotion_authority": "phase20-local-text-classifier-v1",
        "decision_tree": "configs/decision-tree.yaml",
        "data_file": "data/inputs.csv",
        "anchor_schema_name": "gsigmad-anchor-pack",
        "anchor_schema_version": 1,
        "anchors_file": "contracts/anchors.yaml",
        "gates": {"g0": {"status": "pass"}},
        "notebook_entry_id": "NOTE-EXP-22.1-1",
        "journal_rows": ["JRN-1"],
        "closure_metadata": {"results": "RESULTS-EXP-22.1-7"},
        "hypothesis": {
            "h0": "No effect",
            "h1": "Effect exists",
            "test": "welch_t",
            "alpha": 0.01,
            "mesi": 0.2,
        },
        "replication_artifacts": [
            {"path": "scripts/EXP-22.1_analysis.py", "type": "script", "description": "main"},
            {"path": "pipelines/run.nf", "type": "pipeline", "description": "workflow"},
            {"path": "config/run.yaml", "type": "config", "description": "config"},
            {"path": "data/reference.csv", "type": "data", "description": "dataset"},
            {"path": "env/requirements.txt", "type": "environment", "description": "env"},
            {"path": "notebooks/report.ipynb", "type": "notebook", "description": "mutable"},
        ],
    }

    payload = build_frozen_governance_payload(exp_record)

    assert payload == {
        "exp_id": "EXP-22.1",
        "classification": "CONFIRMATORY",
        "hypothesis": {
            "h0": "No effect",
            "h1": "Effect exists",
            "test": "welch_t",
            "alpha": 0.01,
            "mesi": 0.2,
        },
        "promotion_authority": "phase20-local-text-classifier-v1",
        "decision_tree": "configs/decision-tree.yaml",
        "data_file": "data/inputs.csv",
        "anchor_schema_name": "gsigmad-anchor-pack",
        "anchor_schema_version": 1,
        "anchors_file": "contracts/anchors.yaml",
        "replication_artifacts": [
            {"path": "scripts/EXP-22.1_analysis.py", "type": "script", "description": "main"},
            {"path": "pipelines/run.nf", "type": "pipeline", "description": "workflow"},
            {"path": "config/run.yaml", "type": "config", "description": "config"},
            {"path": "data/reference.csv", "type": "data", "description": "dataset"},
            {"path": "env/requirements.txt", "type": "environment", "description": "env"},
        ],
    }
    assert "status" not in payload
    assert "gates" not in payload
    assert "last_run_id" not in payload
    assert "created_at" not in payload
    assert "notebook_entry_id" not in payload
    assert "journal_rows" not in payload
    assert "closure_metadata" not in payload


def test_collect_immutable_inputs_uses_declared_files_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _init_project(tmp_path)
    exp_id, exp_record = _scaffold_experiment(tmp_path, monkeypatch)

    analysis_path = tmp_path / "scripts" / f"{exp_id}_analysis.py"
    data_path = tmp_path / "data" / "inputs.csv"
    decision_tree_path = tmp_path / "configs" / "decision-tree.yaml"
    anchors_path = tmp_path / "contracts" / "anchors.yaml"
    pipeline_path = tmp_path / "pipelines" / "run.nf"
    config_path = tmp_path / "config" / "runtime.yaml"
    env_path = tmp_path / "env" / "requirements.txt"
    result_path = tmp_path / "results" / exp_id / "output.csv"
    notebook_path = tmp_path / "notebooks" / "report.ipynb"

    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text("sample,data\n1,2\n", encoding="utf-8")
    decision_tree_path.parent.mkdir(parents=True, exist_ok=True)
    decision_tree_path.write_text("steps: []\n", encoding="utf-8")
    anchors_path.parent.mkdir(parents=True, exist_ok=True)
    anchors_path.write_text("schema_name: gsigmad-anchor-pack\nschema_version: 1\nanchors: []\n", encoding="utf-8")
    pipeline_path.parent.mkdir(parents=True, exist_ok=True)
    pipeline_path.write_text("process main {}\n", encoding="utf-8")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("mode: frozen\n", encoding="utf-8")
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("pydantic==2.12.4\n", encoding="utf-8")
    result_path.write_text("result,value\nok,1\n", encoding="utf-8")
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    notebook_path.write_text("mutable notebook\n", encoding="utf-8")

    exp_record.update(
        {
            "data_file": "data/inputs.csv",
            "decision_tree": "configs/decision-tree.yaml",
            "anchors_file": "contracts/anchors.yaml",
            "replication_artifacts": [
                {"path": "pipelines/run.nf", "type": "pipeline"},
                {"path": "config/runtime.yaml", "type": "config"},
                {"path": "env/requirements.txt", "type": "environment"},
                {"path": f"results/{exp_id}/output.csv", "type": "data"},
                {"path": "notebooks/report.ipynb", "type": "notebook"},
            ],
        }
    )

    inputs = collect_immutable_inputs(tmp_path, exp_record)
    relpaths = {entry["path"] for entry in inputs}

    assert relpaths == {
        analysis_path.relative_to(tmp_path).as_posix(),
        "data/inputs.csv",
        "configs/decision-tree.yaml",
        "contracts/anchors.yaml",
        "pipelines/run.nf",
        "config/runtime.yaml",
        "env/requirements.txt",
    }
    assert f"results/{exp_id}/output.csv" not in relpaths
    assert "notebooks/report.ipynb" not in relpaths
    assert all(entry["sha256"] for entry in inputs)


def test_write_run_manifest_creates_write_once_results_named_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _init_project(tmp_path)
    exp_id, exp_record = _scaffold_experiment(tmp_path, monkeypatch)

    results_id = f"RESULTS-{exp_id}-1"
    manifest = write_run_manifest(tmp_path, exp_record=exp_record, results_id=results_id)
    manifest_path = tmp_path / manifest["manifest_relpath"]

    assert manifest_path == (
        tmp_path / ".gsigmad" / "manifests" / exp_id / f"{results_id}.manifest.yaml"
    )
    assert manifest_path.is_file()

    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert payload["exp_id"] == exp_id
    assert payload["results_id"] == results_id
    assert payload["frozen_governance"] == build_frozen_governance_payload(exp_record)

    with pytest.raises(FileExistsError):
        write_run_manifest(tmp_path, exp_record=exp_record, results_id=results_id)


def test_write_run_manifest_returns_manifest_relpath_and_frozen_governance_sha256(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _init_project(tmp_path)
    exp_id, exp_record = _scaffold_experiment(tmp_path, monkeypatch)

    manifest = write_run_manifest(
        tmp_path,
        exp_record=exp_record,
        results_id=f"RESULTS-{exp_id}-1",
    )

    expected_payload = build_frozen_governance_payload(exp_record)
    assert manifest["manifest_relpath"] == (
        Path(".gsigmad") / "manifests" / exp_id / f"RESULTS-{exp_id}-1.manifest.yaml"
    ).as_posix()
    assert manifest["frozen_governance_sha256"] == hash_payload(expected_payload)


def test_verify_run_manifest_detects_missing_and_mismatched_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _init_project(tmp_path)
    exp_id, exp_record = _scaffold_experiment(tmp_path, monkeypatch)

    missing_path = tmp_path / ".gsigmad" / "manifests" / exp_id / f"RESULTS-{exp_id}-1.manifest.yaml"
    missing_status = verify_run_manifest(tmp_path, exp_record=exp_record, manifest_path=missing_path)
    assert missing_status["status"] == "missing"

    placeholder_path = tmp_path / ".gsigmad" / "manifests" / exp_id / "MANIFEST.placeholder.yaml"
    unavailable_status = verify_run_manifest(
        tmp_path,
        exp_record=exp_record,
        manifest_path=placeholder_path,
    )
    assert unavailable_status["status"] == "unavailable"

    data_path = tmp_path / "data" / "inputs.csv"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text("sample,data\n1,2\n", encoding="utf-8")
    exp_record["data_file"] = "data/inputs.csv"

    manifest = write_run_manifest(
        tmp_path,
        exp_record=exp_record,
        results_id=f"RESULTS-{exp_id}-1",
    )
    manifest_path = tmp_path / manifest["manifest_relpath"]
    verified = verify_run_manifest(tmp_path, exp_record=exp_record, manifest_path=manifest_path)
    assert verified["status"] == "verified"

    data_path.write_text("sample,data\n1,999\n", encoding="utf-8")
    mismatch = verify_run_manifest(tmp_path, exp_record=exp_record, manifest_path=manifest_path)
    assert mismatch["status"] == "mismatch"


def test_compare_run_manifests_reports_frozen_governance_and_input_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _init_project(tmp_path)
    exp_id, exp_record = _scaffold_experiment(tmp_path, monkeypatch)

    data_path = tmp_path / "data" / "inputs.csv"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text("sample,data\n1,2\n", encoding="utf-8")
    exp_record["data_file"] = "data/inputs.csv"

    baseline = write_run_manifest(
        tmp_path,
        exp_record=exp_record,
        results_id=f"RESULTS-{exp_id}-1",
    )

    exp_record["hypothesis"]["h1"] = "Effect exists with stronger response"
    data_path.write_text("sample,data\n1,3\n", encoding="utf-8")
    replay = write_run_manifest(
        tmp_path,
        exp_record=exp_record,
        results_id=f"RESULTS-{exp_id}-2",
    )

    comparison = compare_run_manifests(
        tmp_path,
        baseline_manifest_path=tmp_path / baseline["manifest_relpath"],
        candidate_manifest_path=tmp_path / replay["manifest_relpath"],
    )

    assert comparison["pass"] is False
    reason_codes = {reason["code"] for reason in comparison["reasons"]}
    assert "FROZEN_GOVERNANCE_DRIFT" in reason_codes
    assert "IMMUTABLE_INPUT_DRIFT" in reason_codes
