"""Tests for Phase 06 closure-chain state."""
from pathlib import Path

from typer.testing import CliRunner

from gsigmad.cli import app
from gsigmad.governance.closure_chain import (
    ensure_chain_for_experiment,
    list_chain_summaries,
    load_chain_state,
    next_results_artifact_id,
    record_chain_event,
)

runner = CliRunner()


def _init_project(path: Path) -> None:
    result = runner.invoke(app, ["init", str(path)])
    assert result.exit_code == 0, result.output


def test_closure_chain_complete_path(tmp_path: Path) -> None:
    _init_project(tmp_path)
    record_chain_event(tmp_path, exp_id="EXP-1.1", stage="TASK", artifact_id="TASK-1.1")
    record_chain_event(tmp_path, exp_id="EXP-1.1", stage="PROMPT", artifact_id="PROMPT-1.1")
    record_chain_event(tmp_path, exp_id="EXP-1.1", stage="EXP", artifact_id="EXP-1.1")
    record_chain_event(tmp_path, exp_id="EXP-1.1", stage="RESULTS")
    record_chain_event(tmp_path, exp_id="EXP-1.1", stage="RT", artifact_id="RT-1.1")
    record_chain_event(
        tmp_path,
        exp_id="EXP-1.1",
        stage="LAB_NOTEBOOK",
        artifact_id="NOTE-EXP-1.1-1",
        terminal_state="COMPLETED",
    )

    summary = list_chain_summaries(tmp_path)[0]
    assert summary["complete"] is True
    assert summary["terminal_state"] == "COMPLETED"
    assert summary["missing"] == []


def test_closure_chain_rejects_out_of_order_results(tmp_path: Path) -> None:
    _init_project(tmp_path)

    try:
        record_chain_event(tmp_path, exp_id="EXP-1.1", stage="RESULTS")
    except ValueError as exc:
        assert "prerequisites" in str(exc)
    else:  # pragma: no cover - explicit failure path
        raise AssertionError("Expected out-of-order closure stage to fail")


def test_closure_chain_blocked_then_remediated(tmp_path: Path) -> None:
    _init_project(tmp_path)
    record_chain_event(tmp_path, exp_id="EXP-1.1", stage="TASK", artifact_id="TASK-1.1")
    record_chain_event(tmp_path, exp_id="EXP-1.1", stage="PROMPT", artifact_id="PROMPT-1.1")
    record_chain_event(tmp_path, exp_id="EXP-1.1", stage="EXP", artifact_id="EXP-1.1")
    record_chain_event(tmp_path, exp_id="EXP-1.1", stage="RESULTS")
    record_chain_event(
        tmp_path,
        exp_id="EXP-1.1",
        stage="RT",
        artifact_id="RT-1.1",
        terminal_state="BLOCKED",
    )
    record_chain_event(tmp_path, exp_id="EXP-1.1", stage="REM", artifact_id="REM-1.1")
    record_chain_event(
        tmp_path,
        exp_id="EXP-1.1",
        stage="LAB_NOTEBOOK",
        artifact_id="NOTE-EXP-1.1-1",
        terminal_state="COMPLETED",
    )

    summary = list_chain_summaries(tmp_path)[0]
    assert summary["terminal_state"] == "COMPLETED"
    assert summary["rem_id"] == "REM-1.1"


def test_ensure_chain_backfills_existing_exp_record(tmp_path: Path) -> None:
    _init_project(tmp_path)
    exp_record = {
        "exp_id": "EXP-1.1",
        "task_id": "TASK-1.1",
        "prompt_id": "PROMPT-1.1",
    }
    chain = ensure_chain_for_experiment(tmp_path, exp_record)
    assert chain["exp_id"] == "EXP-1.1"
    assert chain["current_stage"] == "EXP"


def test_next_results_artifact_id_matches_results_counter_without_mutation(tmp_path: Path) -> None:
    _init_project(tmp_path)
    record_chain_event(tmp_path, exp_id="EXP-1.1", stage="TASK", artifact_id="TASK-1.1")
    record_chain_event(tmp_path, exp_id="EXP-1.1", stage="PROMPT", artifact_id="PROMPT-1.1")
    record_chain_event(tmp_path, exp_id="EXP-1.1", stage="EXP", artifact_id="EXP-1.1")

    predicted = next_results_artifact_id(tmp_path, "EXP-1.1")
    assert predicted == "RESULTS-EXP-1.1-1"

    state_before = load_chain_state(tmp_path)
    chain_before = state_before["chains"]["EXP-1.1"]
    assert chain_before["results_id"] is None
    assert [event["stage"] for event in chain_before["history"]] == ["TASK", "PROMPT", "EXP"]

    assert next_results_artifact_id(tmp_path, "EXP-1.1") == predicted

    chain = record_chain_event(
        tmp_path,
        exp_id="EXP-1.1",
        stage="RESULTS",
        artifact_id=predicted,
    )
    assert chain["results_id"] == predicted
    assert next_results_artifact_id(tmp_path, "EXP-1.1") == "RESULTS-EXP-1.1-2"
