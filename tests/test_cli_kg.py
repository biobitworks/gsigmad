"""Tests for kg subcommands."""
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from gsigmad.cli import app

runner = CliRunner()


def test_kg_find_json(monkeypatch):
    """kg find emits JSON results via the routed helper."""
    monkeypatch.setattr(
        "gsigmad.commands.kg.routed_find_experiments",
        lambda **_: [{"exp_id": "shadow-seeds:EXP-001", "project": "shadow-seeds"}],
    )
    result = runner.invoke(app, ["--json", "kg", "find", "--path", "."])
    assert result.exit_code == 0
    assert '"count": 1' in result.stdout


def test_kg_validate_failure(monkeypatch):
    """kg validate exits non-zero when live validation fails."""
    monkeypatch.setattr(
        "gsigmad.commands.kg.validate_live_kg",
        lambda **_: {"pass": False, "context": {"project_name": "shadow-seeds", "runtime_mode": "legacy", "resolution_source": "runtime_manifest"}, "checks": {"write_inserted": False}, "errors": ["boom"]},
    )
    result = runner.invoke(app, ["kg", "validate", "."])
    assert result.exit_code == 1


def _write_jsonl(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(json.dumps(entry) for entry in entries)
    path.write_text(payload + ("\n" if payload else ""), encoding="utf-8")


def test_kg_queue_inspect_reports_pending_failed_expired_and_quarantine_counts(tmp_path: Path):
    """kg queue inspect should expose operator-visible queue state counts."""
    agent_root = tmp_path / ".agent"
    _write_jsonl(
        agent_root / "kg_queue.jsonl",
        [
            {
                "queued_at": "2026-04-09T10:00:00Z",
                "operation": "insert",
                "collection": "experiments",
                "document": {"_key": "pending-1"},
                "old_rev": None,
                "attempts": 1,
                "failure_class": "transient",
                "next_retry_after": "2026-04-09T10:05:00Z",
            },
            {
                "queued_at": "2026-04-09T10:01:00Z",
                "operation": "insert",
                "collection": "experiments",
                "document": {"_key": "pending-2"},
                "old_rev": None,
                "attempts": 0,
                "failure_class": None,
                "next_retry_after": None,
            },
        ],
    )
    _write_jsonl(
        agent_root / "kg_queue_failed.jsonl",
        [
            {
                "queued_at": "2026-04-09T09:50:00Z",
                "operation": "replace",
                "collection": "experiments",
                "document": {"_key": "failed-1"},
                "old_rev": "_rev-1",
                "attempts": 2,
                "failure_class": "permanent",
                "next_retry_after": None,
            }
        ],
    )
    _write_jsonl(
        agent_root / "kg_queue_expired.jsonl",
        [
            {
                "queued_at": "2026-04-01T09:50:00Z",
                "operation": "insert",
                "collection": "experiments",
                "document": {"_key": "expired-1"},
                "old_rev": None,
                "attempts": 4,
                "failure_class": "transient",
                "next_retry_after": None,
            }
        ],
    )
    _write_jsonl(
        agent_root / "kg_queue_quarantine.jsonl",
        [
            {
                "source_path": str(agent_root / "kg_queue.jsonl"),
                "raw_line": "{\"broken\":",
                "error": "Expecting value",
                "quarantined_at": "2026-04-09T10:02:00Z",
            }
        ],
    )

    result = runner.invoke(app, ["kg", "queue", "inspect", str(tmp_path)])

    assert result.exit_code == 0
    assert "pending" in result.stdout.lower()
    assert "failed" in result.stdout.lower()
    assert "expired" in result.stdout.lower()
    assert "quarantine" in result.stdout.lower()
    assert "2" in result.stdout
    assert "1" in result.stdout


def test_kg_queue_inspect_json_includes_retry_and_failure_details(tmp_path: Path):
    """JSON queue inspect should include per-entry retry and failure detail."""
    agent_root = tmp_path / ".agent"
    _write_jsonl(
        agent_root / "kg_queue.jsonl",
        [
            {
                "queued_at": "2026-04-09T10:00:00Z",
                "operation": "insert",
                "collection": "experiments",
                "document": {"_key": "pending-1"},
                "old_rev": None,
                "attempts": 1,
                "failure_class": "transient",
                "next_retry_after": "2026-04-09T10:05:00Z",
                "idempotency_key": "abc123",
            }
        ],
    )
    _write_jsonl(
        agent_root / "kg_queue_failed.jsonl",
        [
            {
                "queued_at": "2026-04-09T09:50:00Z",
                "operation": "replace",
                "collection": "experiments",
                "document": {"_key": "failed-1"},
                "old_rev": "_rev-1",
                "attempts": 2,
                "failure_class": "permanent",
                "next_retry_after": None,
                "idempotency_key": "deadbeef",
            }
        ],
    )

    result = runner.invoke(app, ["--json", "kg", "queue", "inspect", str(tmp_path)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["counts"]["pending"] == 1
    assert payload["counts"]["failed"] == 1
    assert payload["counts"]["expired"] == 0
    assert payload["counts"]["quarantine"] == 0
    assert payload["entries"]["pending"][0]["failure_class"] == "transient"
    assert payload["entries"]["pending"][0]["next_retry_after"] == "2026-04-09T10:05:00Z"
    assert payload["entries"]["failed"][0]["failure_class"] == "permanent"
