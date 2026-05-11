"""Tests for recovery helper logic."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from gsigmad.cli import app
from gsigmad.governance.closure_chain import load_chain_state, save_chain_state
from gsigmad.governance.recovery import diagnose_recovery_state, repair_recovery_state
from gsigmad.hub.ledger import append_w5, verify_ledger_chain
from gsigmad.scaffold.templates import exp_template
from typer.testing import CliRunner

runner = CliRunner()


def _init_project(path: Path) -> None:
    result = runner.invoke(app, ["init", str(path)])
    assert result.exit_code == 0, result.output


def _write_exp(path: Path, exp_id: str) -> None:
    exp_path = path / ".gsigmad" / "experiments" / f"{exp_id}.yaml"
    exp_path.parent.mkdir(parents=True, exist_ok=True)
    exp_path.write_text(
        yaml.safe_dump(exp_template(exp_id, "EXPLORATORY"), sort_keys=False),
        encoding="utf-8",
    )


def _base_chain(exp_id: str) -> dict:
    return {
        "exp_id": exp_id,
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


def _corrupt_ledger(path: Path) -> None:
    append_w5(
        path,
        who={"actor": "tester"},
        what={"command": "register"},
        where={"project_root": str(path), "exp_id": "EXP-1.1"},
        why={"action": "pre_register"},
    )
    append_w5(
        path,
        who={"actor": "tester"},
        what={"command": "run"},
        where={"project_root": str(path), "exp_id": "EXP-1.1"},
        why={"action": "execute"},
    )
    ledger_file = path / ".gsigmad" / "ledger" / "governance.jsonl"
    entries = [json.loads(line) for line in ledger_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    entries[0]["why"]["action"] = "tampered"
    ledger_file.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")
    assert verify_ledger_chain(path)["pass"] is False


def test_diagnose_recovery_state_classifies_chain_ledger_and_queue_issues(tmp_path: Path) -> None:
    """diagnosis should classify the major recovery issue families."""
    _init_project(tmp_path)
    _write_exp(tmp_path, "EXP-1.1")
    _corrupt_ledger(tmp_path)

    agent_root = tmp_path / ".agent"
    agent_root.mkdir(parents=True, exist_ok=True)
    (agent_root / "kg_queue.jsonl").write_text(
        json.dumps(
            {
                "queued_at": "2026-04-19T20:00:00Z",
                "operation": "insert",
                "collection": "experiments",
                "document": {"_key": "valid-1"},
            }
        )
        + "\n"
        + '{"broken":\n',
        encoding="utf-8",
    )

    dangling = _base_chain("EXP-1.1")
    dangling["exp_id"] = "EXP-9.9"
    dangling["current_stage"] = "RESULTS"
    dangling["results_id"] = "RESULTS-EXP-1.1-1"
    dangling["history"] = [
        {"timestamp": "2026-04-19T20:00:00Z", "stage": "EXP", "artifact_id": "EXP-1.1", "metadata": {}},
        {"timestamp": "2026-04-19T20:01:00Z", "stage": "RESULTS", "artifact_id": "RESULTS-EXP-1.1-1", "metadata": {}},
        {"timestamp": "2026-04-19T20:02:00Z", "stage": "PROMPT", "artifact_id": "PROMPT-1", "metadata": {}},
    ]
    orphan = _base_chain("EXP-404")
    orphan["current_stage"] = "EXP"
    orphan["history"] = [{"timestamp": "2026-04-19T20:00:00Z", "stage": "EXP", "artifact_id": "EXP-404", "metadata": {}}]
    save_chain_state(
        tmp_path,
        {
            "schema_version": 1,
            "chains": {"EXP-1.1": dangling, "EXP-404": orphan},
            "updated_at": "2026-04-19T20:00:00Z",
        },
    )

    payload = diagnose_recovery_state(tmp_path)
    codes = {issue["code"] for issue in payload["issues"]}

    assert "DANGLING_REFERENCE" in codes
    assert "BACKWARD_TRANSITION" in codes
    assert "ORPHANED_CHAIN" in codes
    assert "BROKEN_LEDGER_CHAIN" in codes
    assert "QUEUE_CORRUPTION" in codes


def test_diagnose_recovery_state_does_not_flag_in_progress_chain_as_corruption(tmp_path: Path) -> None:
    """A normal in-progress chain should not be treated as a stuck closure."""
    _init_project(tmp_path)
    _write_exp(tmp_path, "EXP-1.1")
    chain = _base_chain("EXP-1.1")
    chain["current_stage"] = "EXP"
    chain["history"] = [{"timestamp": "2026-04-19T20:00:00Z", "stage": "EXP", "artifact_id": "EXP-1.1", "metadata": {}}]
    save_chain_state(
        tmp_path,
        {
            "schema_version": 1,
            "chains": {"EXP-1.1": chain},
            "updated_at": "2026-04-19T20:00:00Z",
        },
    )

    payload = diagnose_recovery_state(tmp_path)
    codes = {issue["code"] for issue in payload["issues"]}
    assert "STUCK_CLOSURE" not in codes
    assert "BACKWARD_TRANSITION" not in codes


def test_repair_queue_preserves_valid_entries_and_quarantines_malformed_lines(tmp_path: Path) -> None:
    """Queue repair should keep valid lines active and preserve malformed lines for review."""
    _init_project(tmp_path)
    agent_root = tmp_path / ".agent"
    agent_root.mkdir(parents=True, exist_ok=True)
    queue_path = agent_root / "kg_queue.jsonl"
    queue_path.write_text(
        json.dumps(
            {
                "queued_at": "2026-04-19T20:00:00Z",
                "operation": "insert",
                "collection": "experiments",
                "document": {"_key": "valid-1"},
            }
        )
        + "\n"
        + '{"broken":\n',
        encoding="utf-8",
    )

    result = repair_recovery_state(
        tmp_path,
        target="queue",
        apply=True,
        attestation="operator approved queue cleanup",
    )

    assert result["applied"] is True
    repaired_lines = [line for line in queue_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(repaired_lines) == 1
    assert json.loads(repaired_lines[0])["document"]["_key"] == "valid-1"

    quarantine_path = agent_root / "kg_queue_quarantine.jsonl"
    quarantine_entries = [json.loads(line) for line in quarantine_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert quarantine_entries
    assert quarantine_entries[0]["raw_line"] == '{"broken":'


def test_repair_closure_state_adds_recovery_metadata_without_deleting_history(tmp_path: Path) -> None:
    """Closure repair should preserve existing history while appending recovery metadata."""
    _init_project(tmp_path)
    _write_exp(tmp_path, "EXP-1.1")

    chain = _base_chain("EXP-1.1")
    chain["current_stage"] = "RESULTS"
    chain["results_id"] = "RESULTS-EXP-1.1-1"
    chain["history"] = [
        {"timestamp": "2026-04-19T20:00:00Z", "stage": "EXP", "artifact_id": "EXP-1.1", "metadata": {}},
        {"timestamp": "2026-04-19T20:01:00Z", "stage": "RESULTS", "artifact_id": "RESULTS-EXP-1.1-1", "metadata": {}},
    ]
    save_chain_state(
        tmp_path,
        {
            "schema_version": 1,
            "chains": {"EXP-1.1": chain},
            "updated_at": "2026-04-19T20:00:00Z",
        },
    )

    original_history = list(chain["history"])
    result = repair_recovery_state(
        tmp_path,
        target="closure",
        apply=True,
        attestation="operator approved closure recovery",
    )

    assert result["applied"] is True
    repaired_state = load_chain_state(tmp_path, create=False)
    repaired_chain = repaired_state["chains"]["EXP-1.1"]
    assert repaired_chain["history"] == original_history
    assert repaired_chain["recovery_events"]
    assert repaired_chain["recovery_events"][0]["marker"] == "CHAIN_BREAK"
