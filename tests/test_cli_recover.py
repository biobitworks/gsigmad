"""Tests for recover subcommands."""
from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from gsigmad.cli import app
from gsigmad.governance.closure_chain import save_chain_state
from gsigmad.hub.ledger import append_w5, verify_ledger_chain
from gsigmad.scaffold.templates import exp_template

runner = CliRunner()


def _init_project(path: Path) -> None:
    result = runner.invoke(app, ["init", str(path)])
    assert result.exit_code == 0, result.output


def _write_exp(path: Path, exp_id: str, *, classification: str = "EXPLORATORY") -> None:
    exp_path = path / ".gsigmad" / "experiments" / f"{exp_id}.yaml"
    exp_path.parent.mkdir(parents=True, exist_ok=True)
    exp_path.write_text(
        yaml.safe_dump(exp_template(exp_id, classification), sort_keys=False),
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


def _write_queue_with_corruption(path: Path) -> None:
    agent_root = path / ".agent"
    agent_root.mkdir(parents=True, exist_ok=True)
    (agent_root / "kg_queue.jsonl").write_text(
        json.dumps(
            {
                "queued_at": "2026-04-19T20:00:00Z",
                "operation": "insert",
                "collection": "experiments",
                "document": {"_key": "valid-1"},
                "attempts": 0,
            }
        )
        + "\n"
        + '{"broken":\n',
        encoding="utf-8",
    )


def test_recover_diagnose_reports_corruption_without_side_effects(tmp_path: Path, monkeypatch) -> None:
    """recover diagnose should report corruption while leaving files untouched."""
    _init_project(tmp_path)
    _write_exp(tmp_path, "EXP-1.1")
    _corrupt_ledger(tmp_path)
    _write_queue_with_corruption(tmp_path)

    orphan = _base_chain("EXP-404")
    orphan["current_stage"] = "EXP"
    orphan["history"] = [{"timestamp": "2026-04-19T20:00:00Z", "stage": "EXP", "artifact_id": "EXP-404", "metadata": {}}]
    save_chain_state(
        tmp_path,
        {
            "schema_version": 1,
            "chains": {"EXP-404": orphan},
            "updated_at": "2026-04-19T20:00:00Z",
        },
    )

    monkeypatch.chdir(tmp_path.parent)
    ledger_file = tmp_path / ".gsigmad" / "ledger" / "governance.jsonl"
    queue_file = tmp_path / ".agent" / "kg_queue.jsonl"
    chain_file = tmp_path / ".gsigmad" / "closure_chain.json"
    before = {
        "ledger": ledger_file.read_bytes(),
        "queue": queue_file.read_bytes(),
        "chain": chain_file.read_bytes(),
    }

    result = runner.invoke(app, ["recover", "diagnose", str(tmp_path)], catch_exceptions=False)

    assert result.exit_code == 0, result.output
    output = result.output.lower()
    assert "recovery diagnose" in output
    assert "ledger" in output
    assert "queue" in output
    assert "closure" in output
    assert ledger_file.read_bytes() == before["ledger"]
    assert queue_file.read_bytes() == before["queue"]
    assert chain_file.read_bytes() == before["chain"]


def test_recover_diagnose_json_includes_issue_summary_and_suggested_actions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """recover diagnose JSON should expose a machine-readable issue list and summary."""
    _init_project(tmp_path)
    _write_exp(tmp_path, "EXP-1.1")
    _corrupt_ledger(tmp_path)
    monkeypatch.chdir(tmp_path.parent)

    result = runner.invoke(app, ["--json", "recover", "diagnose", str(tmp_path)], catch_exceptions=False)

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["summary"]["healthy"] is False
    assert payload["summary"]["issue_count"] >= 1
    assert payload["issues"]
    assert all("suggested_action" in issue for issue in payload["issues"])


def test_recover_repair_requires_attestation_for_apply(tmp_path: Path, monkeypatch) -> None:
    """apply-mode repair should fail without explicit operator attestation."""
    _init_project(tmp_path)
    _corrupt_ledger(tmp_path)
    monkeypatch.chdir(tmp_path.parent)

    result = runner.invoke(
        app,
        ["recover", "repair", str(tmp_path), "--target", "ledger", "--apply"],
        catch_exceptions=False,
    )

    assert result.exit_code == 1
    assert "attestation" in result.output.lower()


def test_recover_repair_backs_up_corrupt_ledger_and_records_chain_break(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """ledger repair should preserve the corrupt ledger and seed a CHAIN_BREAK recovery record."""
    _init_project(tmp_path)
    _corrupt_ledger(tmp_path)
    monkeypatch.chdir(tmp_path.parent)

    result = runner.invoke(
        app,
        [
            "--json",
            "recover",
            "repair",
            str(tmp_path),
            "--target",
            "ledger",
            "--apply",
            "--attestation",
            "operator approved ledger recovery",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["applied"] is True
    assert payload["backups"]
    backup_path = Path(payload["backups"][0]["backup_path"])
    assert backup_path.exists()

    ledger_file = tmp_path / ".gsigmad" / "ledger" / "governance.jsonl"
    ledger_text = ledger_file.read_text(encoding="utf-8")
    assert "CHAIN_BREAK" in ledger_text
    assert "operator approved ledger recovery" in ledger_text
    assert verify_ledger_chain(tmp_path)["pass"] is True


def test_recover_repair_reports_w5_audit_metadata(tmp_path: Path, monkeypatch) -> None:
    """repair JSON should include audit metadata for applied recovery work."""
    _init_project(tmp_path)
    _write_queue_with_corruption(tmp_path)
    monkeypatch.chdir(tmp_path.parent)

    result = runner.invoke(
        app,
        [
            "--json",
            "recover",
            "repair",
            str(tmp_path),
            "--target",
            "queue",
            "--apply",
            "--attestation",
            "operator approved queue cleanup",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["audit"]
    assert any(audit["target"] == "queue" for audit in payload["audit"])
    queue_audit = next(audit for audit in payload["audit"] if audit["target"] == "queue")
    assert queue_audit["entry"]["metadata"]["attestation"] == "operator approved queue cleanup"


def test_recover_review_json_groups_terminal_queue_work_without_mutation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """recover review should expose dead-letter and non-retryable queue work read-only."""
    _init_project(tmp_path)
    agent_root = tmp_path / ".agent"
    agent_root.mkdir(parents=True, exist_ok=True)
    (agent_root / "kg_queue_failed.jsonl").write_text(
        json.dumps(
            {
                "queued_at": "2026-04-19T20:00:00Z",
                "operation": "replace",
                "collection": "experiments",
                "document": {"_key": "failed-1"},
                "old_rev": "_rev-1",
                "attempts": 1,
                "failure_class": "permanent",
                "next_retry_after": None,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    queue_bytes = (agent_root / "kg_queue_failed.jsonl").read_bytes()
    monkeypatch.chdir(tmp_path.parent)

    result = runner.invoke(app, ["--json", "recover", "review", str(tmp_path)], catch_exceptions=False)

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["summary"]["dead_letter"] == 1
    assert payload["summary"]["non_retryable"] == 1
    assert payload["entries"]["dead_letter"][0]["entry_id"] == "failed-1"
    assert (agent_root / "kg_queue_failed.jsonl").read_bytes() == queue_bytes
