"""Tests for REP-01 replication artifacts field and validation."""
from __future__ import annotations

from pathlib import Path

from gsigmad.scaffold.templates import (
    REPLICATION_ARTIFACT_TYPES,
    ROCRATE_TYPE_MAP,
    exp_template,
    validate_replication_artifacts,
)
from gsigmad.governance.closure_chain import summarize_chain


# -- exp_template includes replication_artifacts --


def test_exp_template_includes_replication_artifacts():
    record = exp_template("EXP-1", "EXPLORATORY")
    assert "replication_artifacts" in record
    assert record["replication_artifacts"] == []


# -- Type enum --


def test_artifact_type_enum_values():
    assert REPLICATION_ARTIFACT_TYPES == frozenset(
        {"notebook", "script", "pipeline", "config", "data", "environment"}
    )


# -- Valid artifact entry --


def test_valid_artifact_entry():
    artifacts = [
        {"path": "scripts/run.py", "type": "script", "description": "Main runner"},
    ]
    result = validate_replication_artifacts(artifacts, "CONFIRMATORY")
    assert result["valid"] is True
    assert result["errors"] == []
    assert result["skipped"] is False


# -- CONFIRMATORY requires description (D-16) --


def test_confirmatory_requires_description():
    artifacts = [{"path": "scripts/run.py", "type": "script"}]
    result = validate_replication_artifacts(artifacts, "CONFIRMATORY")
    assert result["valid"] is False
    assert any("description" in e for e in result["errors"])


# -- EXPLORATORY allows missing description (D-16) --


def test_exploratory_allows_missing_description():
    artifacts = [{"path": "scripts/run.py", "type": "script"}]
    result = validate_replication_artifacts(artifacts, "EXPLORATORY")
    assert result["valid"] is True


# -- Invalid type rejected --


def test_invalid_type_rejected():
    artifacts = [{"path": "foo.txt", "type": "unknown", "description": "bad type"}]
    result = validate_replication_artifacts(artifacts, "EXPLORATORY")
    assert result["valid"] is False
    assert any("type" in e for e in result["errors"])


# -- Missing path checks (D-17) --


def test_missing_path_confirmatory_fails(tmp_path: Path):
    artifacts = [
        {
            "path": "nonexistent/file.py",
            "type": "script",
            "description": "Does not exist",
        }
    ]
    result = validate_replication_artifacts(artifacts, "CONFIRMATORY", project_root=tmp_path)
    assert result["valid"] is False
    assert any("does not exist" in e for e in result["errors"])


def test_missing_path_exploratory_warns(tmp_path: Path):
    artifacts = [{"path": "nonexistent/file.py", "type": "script"}]
    result = validate_replication_artifacts(artifacts, "EXPLORATORY", project_root=tmp_path)
    assert result["valid"] is True
    assert any("does not exist" in w for w in result["warnings"])


# -- Pre-v1.7 backward compatibility (D-19) --


def test_pre_v17_record_skipped():
    result = validate_replication_artifacts(None, "CONFIRMATORY")
    assert result["skipped"] is True
    assert result["valid"] is True
    assert result["errors"] == []


# -- RO-Crate type mapping (D-18) --


def test_rocrate_type_mapping():
    assert ROCRATE_TYPE_MAP["script"] == ["File", "SoftwareSourceCode"]
    assert ROCRATE_TYPE_MAP["notebook"] == ["File", "SoftwareSourceCode"]


def test_rocrate_pipeline_mapping():
    assert "ComputationalWorkflow" in ROCRATE_TYPE_MAP["pipeline"]


# -- Closure chain summarize_chain includes replication_artifacts_status --


def test_summarize_chain_replication_status_skip():
    """Pre-v1.7 chain (no replication_artifacts key) -> SKIP."""
    chain = {
        "exp_id": "EXP-1",
        "task_id": None,
        "prompt_id": None,
        "results_id": None,
        "rt_id": None,
        "rem_id": None,
        "lab_notebook_entry": None,
        "current_stage": None,
        "terminal_state": None,
        "history": [],
    }
    summary = summarize_chain(chain)
    assert summary["replication_artifacts_status"] == "SKIP"


def test_summarize_chain_replication_status_declared():
    """Chain with replication_artifacts list -> DECLARED."""
    chain = {
        "exp_id": "EXP-1",
        "task_id": None,
        "prompt_id": None,
        "results_id": None,
        "rt_id": None,
        "rem_id": None,
        "lab_notebook_entry": None,
        "current_stage": None,
        "terminal_state": None,
        "history": [],
        "replication_artifacts": [{"path": "x.py", "type": "script"}],
    }
    summary = summarize_chain(chain)
    assert summary["replication_artifacts_status"] == "DECLARED"


def test_summarize_chain_replication_status_empty():
    """Chain with empty replication_artifacts -> EMPTY."""
    chain = {
        "exp_id": "EXP-1",
        "task_id": None,
        "prompt_id": None,
        "results_id": None,
        "rt_id": None,
        "rem_id": None,
        "lab_notebook_entry": None,
        "current_stage": None,
        "terminal_state": None,
        "history": [],
        "replication_artifacts": [],
    }
    summary = summarize_chain(chain)
    assert summary["replication_artifacts_status"] == "EMPTY"
