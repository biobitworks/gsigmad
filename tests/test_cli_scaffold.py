"""Contract tests for the Phase 20 scaffold CLI (EXEC-01)."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from gsigmad.cli import app
from gsigmad.governance.receipts import load_stage_receipt

runner = CliRunner()

RATIFIED_PROMOTION_AUTHORITY = "phase20-local-text-classifier-v1"


def _init_project(path: Path) -> None:
    result = runner.invoke(app, ["init", str(path)], catch_exceptions=False)
    assert result.exit_code == 0, result.output


def _enable_anchor_opt_in(project_root: Path) -> None:
    config_path = project_root / ".gsigmad" / "config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["anchor_schema_version"] = 1
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def _write_anchor_file(project_root: Path, *, valid: bool = True) -> Path:
    anchors_path = project_root / "contracts" / "anchors" / "scaffold-anchors.yaml"
    anchors_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_name": "gsigmad-anchor-pack",
        "schema_version": 1,
        "anchors": [
            {
                "anchor_type": "dataset",
                "anchor_id": "dataset-main",
                "title": "Dataset anchor",
                "dataset_name": "clinical_signals",
                "field_name": "patient_id" if valid else ["patient_id"],
                "source_path": "data/clinical.csv",
            }
        ],
    }
    anchors_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return anchors_path


def _exp_record(project_root: Path, exp_id: str) -> dict:
    exp_path = project_root / ".gsigmad" / "experiments" / f"{exp_id}.yaml"
    return yaml.safe_load(exp_path.read_text(encoding="utf-8"))


def _journal_payload(project_root: Path) -> dict | list:
    journal_path = (
        project_root
        / ".gsigmad"
        / "journal"
        / f"{datetime.now(timezone.utc).date().isoformat()}.yaml"
    )
    return yaml.safe_load(journal_path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("exp_type", ["exploratory", "confirmatory", "replication"])
def test_scaffold_creates_planned_experiment_and_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exp_type: str):
    """Scaffold creates a planned EXP record plus script/results/manifest placeholder artifacts."""
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "--json",
            "scaffold",
            "--type",
            exp_type,
            "--title",
            "Signal check",
            "--hypothesis",
            "The unpublished claim text should stay out of summaries.",
            "--promotion-authority",
            RATIFIED_PROMOTION_AUTHORITY,
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output

    payload = json.loads(result.output)
    exp_id = payload["exp_id"]
    exp_path = tmp_path / ".gsigmad" / "experiments" / f"{exp_id}.yaml"
    script_path = tmp_path / "scripts" / f"{exp_id}_analysis.py"
    results_dir = tmp_path / "results" / exp_id
    manifest_path = tmp_path / ".gsigmad" / "manifests" / exp_id / "MANIFEST.placeholder.yaml"

    assert exp_path.is_file()
    assert script_path.is_file()
    assert results_dir.is_dir()
    assert manifest_path.is_file()

    record = _exp_record(tmp_path, exp_id)
    assert record["status"] == "planned"
    assert record["record_schema_version"] == 3
    assert record["task_id"].startswith("TASK-")
    assert record["prompt_id"].startswith("PROMPT-")
    assert record["scaffold_state"] == "ready"
    assert record["promotion_authority"] == RATIFIED_PROMOTION_AUTHORITY
    assert payload["receipts"]

    receipt = load_stage_receipt(tmp_path, payload["receipts"][0])
    assert receipt.stage.value == "scaffold/materialize"
    assert receipt.run_id == f"RUN-SCAFFOLD-{exp_id}"
    assert receipt.outputs[1].kind.value == "manifest"


def test_scaffold_rejects_or_marks_unratified_unknown_promotion_authority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Unknown promotion authorities must not be persisted as ratified EXP-level approval."""
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "--json",
            "scaffold",
            "--type",
            "confirmatory",
            "--promotion-authority",
            "some-other-authority",
        ],
        catch_exceptions=False,
    )

    if result.exit_code != 0:
        assert "promotion-authority" in result.output
        return

    payload = json.loads(result.output)
    record = _exp_record(tmp_path, payload["exp_id"])
    assert record.get("promotion_authority") != "some-other-authority"
    assert record.get("promotion_authority") in {None, "", "UNRATIFIED"}


def test_scaffold_records_task_prompt_exp_and_low_sensitivity_journal_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Scaffold records closure events and governed summaries without echoing sensitive text."""
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    secret_hypothesis = "Patient secret token 12345 and raw claim body should never be copied."

    result = runner.invoke(
        app,
        [
            "--json",
            "scaffold",
            "--type",
            "exploratory",
            "--hypothesis",
            secret_hypothesis,
            "--promotion-authority",
            RATIFIED_PROMOTION_AUTHORITY,
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output

    payload = json.loads(result.output)
    exp_id = payload["exp_id"]
    chain_state = json.loads((tmp_path / ".gsigmad" / "closure_chain.json").read_text(encoding="utf-8"))
    history = chain_state["chains"][exp_id]["history"]
    journal_path = (
        tmp_path
        / ".gsigmad"
        / "journal"
        / f"{datetime.now(timezone.utc).date().isoformat()}.yaml"
    )
    assert [entry["stage"] for entry in history[:3]] == ["TASK", "PROMPT", "EXP"]

    notebook_text = (tmp_path / ".gsigmad" / "LAB_NOTEBOOK.md").read_text(encoding="utf-8")
    journal_payload = _journal_payload(tmp_path)
    journal_text = yaml.safe_dump(journal_payload, sort_keys=False)

    assert exp_id in notebook_text
    assert exp_id in journal_text
    assert journal_path.is_file()
    assert ".gsigmad/journal/" in journal_path.as_posix()
    assert secret_hypothesis not in notebook_text
    assert secret_hypothesis not in journal_text
    assert "raw claim body" not in notebook_text
    assert "raw claim body" not in journal_text


def test_scaffold_allocates_fresh_ids_and_only_uses_skipped_for_local_collisions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Repeated scaffold runs allocate new EXP IDs instead of behaving like idempotent retries."""
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    first = runner.invoke(app, ["--json", "scaffold", "--type", "exploratory"], catch_exceptions=False)
    second = runner.invoke(app, ["--json", "scaffold", "--type", "exploratory"], catch_exceptions=False)
    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output

    first_payload = json.loads(first.output)
    second_payload = json.loads(second.output)
    assert first_payload["exp_id"] != second_payload["exp_id"]
    assert second_payload["skipped"] == []

def test_scaffold_reports_incomplete_state_without_rollback_on_mandatory_append_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Mandatory post-EXP write failures persist an incomplete scaffold contract instead of rolling back."""
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    from gsigmad.commands import scaffold as scaffold_cmd

    monkeypatch.setattr(
        scaffold_cmd,
        "append_lab_notebook_entry",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("notebook append failed")),
    )

    result = runner.invoke(
        app,
        [
            "--json",
            "scaffold",
            "--type",
            "confirmatory",
            "--promotion-authority",
            RATIFIED_PROMOTION_AUTHORITY,
        ],
        catch_exceptions=False,
    )
    assert result.exit_code != 0
    assert "incomplete" in result.output.lower()

    payload = json.loads(result.output)
    exp_id = payload["exp_id"]
    record = _exp_record(tmp_path, exp_id)
    chain_state = json.loads((tmp_path / ".gsigmad" / "closure_chain.json").read_text(encoding="utf-8"))

    assert record["scaffold_state"] == "incomplete"
    assert record["scaffold_missing"]
    assert record["scaffold_warnings"] == []
    assert payload["created"]
    assert payload["missing"]
    assert exp_id in chain_state["chains"]

def test_scaffold_surfaces_w5_append_failures_as_warnings_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Best-effort W5 append failures warn without converting scaffold success into failure."""
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    from gsigmad.commands import scaffold as scaffold_cmd

    monkeypatch.setattr(
        scaffold_cmd,
        "best_effort_append_command_w5",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("w5 unavailable")),
    )

    result = runner.invoke(
        app,
        [
            "--json",
            "scaffold",
            "--type",
            "exploratory",
            "--promotion-authority",
            RATIFIED_PROMOTION_AUTHORITY,
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "W5_APPEND_FAILED" in payload["warnings"]


def test_scaffold_persists_anchor_pointer_for_opted_in_projects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Opted-in scaffold runs persist validated anchor pointer metadata only."""
    _init_project(tmp_path)
    _enable_anchor_opt_in(tmp_path)
    anchors_path = _write_anchor_file(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "--json",
            "scaffold",
            "--type",
            "exploratory",
            "--anchors-file",
            str(anchors_path.relative_to(tmp_path)),
            "--promotion-authority",
            RATIFIED_PROMOTION_AUTHORITY,
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output

    payload = json.loads(result.output)
    record = _exp_record(tmp_path, payload["exp_id"])
    assert record["anchor_schema_version"] == 1
    assert record["anchors_file"] == "contracts/anchors/scaffold-anchors.yaml"
    assert "anchors" not in record


def test_scaffold_rejects_malformed_anchor_file_for_opted_in_projects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Malformed opted-in anchor payloads fail before scaffold persistence."""
    _init_project(tmp_path)
    _enable_anchor_opt_in(tmp_path)
    anchors_path = _write_anchor_file(tmp_path, valid=False)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "--json",
            "scaffold",
            "--type",
            "exploratory",
            "--anchors-file",
            str(anchors_path.relative_to(tmp_path)),
            "--promotion-authority",
            RATIFIED_PROMOTION_AUTHORITY,
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 1
    assert "anchor" in result.output.lower()
    assert not list((tmp_path / ".gsigmad" / "experiments").glob("EXP-*.yaml"))
