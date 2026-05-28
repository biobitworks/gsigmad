"""Tests for monitoring helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from gsigmad.governance import monitoring as monitoring_mod


def _native_project(tmp_path: Path) -> Path:
    project = tmp_path / "native"
    (project / ".gsigmad").mkdir(parents=True)
    (project / "CANON.md").write_text(
        "> **Status**: ACTIVE\n> **Version**: 1.0.0\n",
        encoding="utf-8",
    )
    return project


def _stub_now_factory():
    moments = iter(
        [
            datetime(2026, 4, 5, 16, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 4, 5, 16, 1, 0, tzinfo=timezone.utc),
            datetime(2026, 4, 5, 16, 2, 0, tzinfo=timezone.utc),
            datetime(2026, 4, 5, 16, 3, 0, tzinfo=timezone.utc),
            datetime(2026, 4, 5, 16, 4, 0, tzinfo=timezone.utc),
            datetime(2026, 4, 5, 16, 5, 0, tzinfo=timezone.utc),
        ]
    )
    return lambda: next(moments)


def _drift_ok(_resolution):
    return {
        "pass": True,
        "drift_detected": False,
        "projects_scanned": 1,
        "report_path": None,
        "event_count": 0,
        "events": [],
    }


def test_monitor_baseline_and_alert_dedup(tmp_path: Path, monkeypatch) -> None:
    project = _native_project(tmp_path)
    monkeypatch.setattr(monitoring_mod, "_utc_now", _stub_now_factory())
    monkeypatch.setattr(monitoring_mod, "_drift_state", _drift_ok)

    monkeypatch.setattr(monitoring_mod, "_kg_state", lambda: {"available": True, "error": None})
    first = monitoring_mod.collect_monitoring_scan(project, write_artifacts=True)
    assert first["summary"]["change_count"] == 0

    baseline = monitoring_mod.set_monitoring_baseline(project)
    assert baseline["pass"] is True

    monkeypatch.setattr(monitoring_mod, "_kg_state", lambda: {"available": False, "error": "offline"})
    second = monitoring_mod.collect_monitoring_scan(project, write_artifacts=True)
    assert second["summary"]["has_alert"] is True

    third = monitoring_mod.collect_monitoring_scan(project, write_artifacts=True)
    assert third["summary"]["has_alert"] is True

    alert_dir = project / ".gsigmad" / "monitoring" / "alerts"
    assert len(list(alert_dir.glob("ALERT-*.json"))) == 1


def test_monitor_history_and_summary(tmp_path: Path, monkeypatch) -> None:
    project = _native_project(tmp_path)
    monkeypatch.setattr(monitoring_mod, "_utc_now", _stub_now_factory())
    monkeypatch.setattr(monitoring_mod, "_drift_state", _drift_ok)
    monkeypatch.setattr(monitoring_mod, "_kg_state", lambda: {"available": True, "error": None})

    monitoring_mod.collect_monitoring_scan(project, write_artifacts=True)
    monitoring_mod.collect_monitoring_scan(project, write_artifacts=True)

    history = monitoring_mod.monitoring_history(project, limit=5)
    assert history["count"] == 2

    summary = monitoring_mod.monitoring_summary(project, limit=5)
    assert summary["history"]["count"] == 2
    assert summary["history"]["last_successful_scan"] is not None
    assert summary["current"]["project_name"] == "native"


def test_monitor_canon_changes_are_categorized(tmp_path: Path, monkeypatch) -> None:
    project = _native_project(tmp_path)
    monkeypatch.setattr(monitoring_mod, "_utc_now", _stub_now_factory())
    monkeypatch.setattr(monitoring_mod, "_drift_state", _drift_ok)
    monkeypatch.setattr(monitoring_mod, "_kg_state", lambda: {"available": True, "error": None})

    monitoring_mod.collect_monitoring_scan(project, write_artifacts=True)
    monitoring_mod.set_monitoring_baseline(project)

    (project / "CANON.md").write_text(
        "> **Status**: ACTIVE\n> **Version**: 1.2.0b1\n",
        encoding="utf-8",
    )
    changed = monitoring_mod.collect_monitoring_scan(project, write_artifacts=True)

    assert changed["summary"]["change_categories"] == ["canon"]

    open_alert = project / ".gsigmad" / "monitoring" / "open-alert.json"
    assert open_alert.exists()
    payload = monitoring_mod._load_json(open_alert)
    assert payload is not None
    assert payload["change_categories"] == ["canon"]


def test_monitor_queue_state_includes_quarantine_and_retry_health(tmp_path: Path, monkeypatch) -> None:
    """Monitoring queue state should expose quarantine and retry/dead-letter detail."""
    project = _native_project(tmp_path)
    monkeypatch.setattr(monitoring_mod, "_utc_now", _stub_now_factory())
    monkeypatch.setattr(monitoring_mod, "_drift_state", _drift_ok)
    monkeypatch.setattr(monitoring_mod, "_kg_state", lambda: {"available": True, "error": None})

    agent_root = project / ".agent"
    agent_root.mkdir(parents=True, exist_ok=True)
    (agent_root / "kg_queue.jsonl").write_text(
        "\n".join(
            [
                '{"queued_at":"2026-04-09T10:00:00Z","operation":"insert","collection":"experiments","document":{"_key":"pending-1"},"old_rev":null,"attempts":0,"failure_class":null,"next_retry_after":null}',
                '{"queued_at":"2026-04-09T10:01:00Z","operation":"insert","collection":"experiments","document":{"_key":"pending-2"},"old_rev":null,"attempts":2,"failure_class":"transient","next_retry_after":"2026-04-09T10:05:00Z"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (agent_root / "kg_queue_failed.jsonl").write_text(
        '{"queued_at":"2026-04-09T09:50:00Z","operation":"replace","collection":"experiments","document":{"_key":"failed-1"},"old_rev":"_rev-1","attempts":1,"failure_class":"permanent","next_retry_after":null}\n',
        encoding="utf-8",
    )
    (agent_root / "kg_queue_expired.jsonl").write_text(
        '{"queued_at":"2026-04-01T09:50:00Z","operation":"insert","collection":"experiments","document":{"_key":"expired-1"},"old_rev":null,"attempts":4,"failure_class":"transient","next_retry_after":null}\n',
        encoding="utf-8",
    )
    (agent_root / "kg_queue_quarantine.jsonl").write_text(
        '{"source_path":".agent/kg_queue.jsonl","raw_line":"{\\"broken\\":","error":"Expecting value","quarantined_at":"2026-04-09T10:02:00Z"}\n',
        encoding="utf-8",
    )

    scan = monitoring_mod.collect_monitoring_scan(project, write_artifacts=False)

    assert scan["queue"]["pending_count"] == 2
    assert scan["queue"]["failed_count"] == 1
    assert scan["queue"]["expired_count"] == 1
    assert scan["queue"]["quarantine_count"] == 1
    assert scan["queue"]["retry_scheduled_count"] == 1
    assert scan["queue"]["dead_letter_count"] == 1
    assert scan["summary"]["pass"] is False


def test_monitor_scan_persists_degradation_state(tmp_path: Path, monkeypatch) -> None:
    """Monitoring scans should persist the shared degradation state artifact."""
    project = _native_project(tmp_path)
    monkeypatch.setattr(monitoring_mod, "_utc_now", _stub_now_factory())
    monkeypatch.setattr(monitoring_mod, "_drift_state", _drift_ok)
    monkeypatch.setattr(monitoring_mod, "_kg_state", lambda: {"available": False, "error": "offline"})

    scan = monitoring_mod.collect_monitoring_scan(project, write_artifacts=True)

    degradation_file = project / ".gsigmad" / "degradation.json"
    assert degradation_file.exists()
    payload = monitoring_mod._load_json(degradation_file)
    assert payload is not None
    assert payload["tier"] == "KG_DEGRADED"
    assert payload["unavailable_services"] == ["kg"]
    assert payload["detected_at"]
    assert scan["degradation"]["tier"] == "KG_DEGRADED"


def test_monitor_summary_reports_degradation_object(tmp_path: Path, monkeypatch) -> None:
    """Monitoring summary should expose the same structured degradation object as the latest scan."""
    project = _native_project(tmp_path)
    monkeypatch.setattr(monitoring_mod, "_utc_now", _stub_now_factory())
    monkeypatch.setattr(monitoring_mod, "_drift_state", _drift_ok)
    monkeypatch.setattr(monitoring_mod, "_kg_state", lambda: {"available": False, "error": "offline"})

    monitoring_mod.collect_monitoring_scan(project, write_artifacts=True)
    summary = monitoring_mod.monitoring_summary(project, limit=5)

    assert summary["current"]["degradation"]["tier"] == "KG_DEGRADED"
    assert summary["current"]["degradation"]["unavailable_services"] == ["kg"]
