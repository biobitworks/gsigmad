"""
Tests for governance.compiler.drift_scanner — scheduled cross-project CANON drift detection.

Decision refs: D-07 (drift detection as scheduled check), D-08 (DRIFT-{timestamp}.json report),
               D-09 (24-hour trigger using mtime vs. last_drift_scan.txt).

All tests use tmp_path for filesystem isolation — no writes to the real .agent/ directory.
"""
import json
import time
import pytest
from pathlib import Path

from gsigmad.governance.compiler.drift_scanner import scan_all_projects


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_canon(path: Path, status: str = "ACTIVE", version: str = "1.0.0") -> None:
    """Write a minimal CANON.md with the standard header block format."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# CANON\n\n"
        f"> **Status**: {status}\n"
        f"> **Version**: {version}\n"
    )


def _make_entry(tmp_path: Path, name: str, has_canon: bool = True) -> dict:
    """Build a project_registry entry pointing into tmp_path."""
    return {
        "name": name,
        "canon_path": str(tmp_path / name / "CANON.md"),
        "has_canon": has_canon,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_empty_registry(tmp_path):
    """scan_all_projects with empty registry returns pass=True, projects_scanned=0."""
    result = scan_all_projects(str(tmp_path), [])

    assert result["pass"] is True
    assert result["projects_scanned"] == 0
    assert result["drift_detected"] is False
    assert result["drift_events"] == []
    assert result["report_path"] is None

    # No report files should be created
    drift_reports_dir = tmp_path / ".agent" / "drift_reports"
    if drift_reports_dir.exists():
        assert list(drift_reports_dir.iterdir()) == []


def test_all_no_canon(tmp_path):
    """All entries have has_canon=False — all skipped, no drift events."""
    registry = [
        _make_entry(tmp_path, "conductor", has_canon=False),
        _make_entry(tmp_path, "antigence", has_canon=False),
        _make_entry(tmp_path, "seedgraph", has_canon=False),
    ]

    result = scan_all_projects(str(tmp_path), registry)

    assert result["projects_scanned"] == 0
    assert result["drift_detected"] is False
    assert result["drift_events"] == []
    assert result["pass"] is True


def test_bootstrap_no_drift(tmp_path):
    """First scan with valid CANON.md creates snapshot, no drift event emitted."""
    canon_path = tmp_path / "test-project" / "CANON.md"
    _write_canon(canon_path, status="ACTIVE", version="1.0.0")

    registry = [_make_entry(tmp_path, "test-project")]
    result = scan_all_projects(str(tmp_path), registry)

    # No drift on first run (bootstrap)
    assert result["drift_events"] == []
    assert result["drift_detected"] is False
    assert result["pass"] is True
    assert result["projects_scanned"] == 1

    # Snapshot file must be created
    snap_path = tmp_path / ".agent" / "drift_snapshots" / "test-project_canon_state.json"
    assert snap_path.exists()
    state = json.loads(snap_path.read_text())
    assert state["status"] == "ACTIVE"
    assert state["version"] == "1.0.0"


def test_drift_detected(tmp_path):
    """Change CANON.md status between scans — drift_events has one entry, pass=False."""
    canon_path = tmp_path / "test-project" / "CANON.md"
    _write_canon(canon_path, status="ACTIVE", version="1.0.0")

    registry = [_make_entry(tmp_path, "test-project")]

    # Bootstrap scan — no drift
    scan_all_projects(str(tmp_path), registry)

    # Force mtime to be in the future relative to last_drift_scan.txt
    # by sleeping briefly and rewriting CANON with changed content
    time.sleep(0.05)
    _write_canon(canon_path, status="DEPRECATED", version="1.0.0")

    # Second scan — should detect drift
    result = scan_all_projects(str(tmp_path), registry)

    assert result["drift_detected"] is True
    assert result["pass"] is False
    assert len(result["drift_events"]) >= 1

    event = result["drift_events"][0]
    assert event["project"] == "test-project"
    assert event["invariant_changed"] == "status"
    assert event["old_classification"] == "ACTIVE"
    assert event["new_classification"] == "DEPRECATED"

    # Report file must exist
    assert result["report_path"] is not None
    assert Path(result["report_path"]).exists()


def test_false_positive_prevention(tmp_path):
    """mtime advanced but content unchanged — no drift event emitted (Pitfall 3)."""
    canon_path = tmp_path / "test-project" / "CANON.md"
    _write_canon(canon_path, status="ACTIVE", version="1.0.0")

    registry = [_make_entry(tmp_path, "test-project")]

    # Bootstrap scan
    scan_all_projects(str(tmp_path), registry)

    # Read content, sleep, write back same bytes (updates mtime without changing content)
    time.sleep(0.05)
    original_content = canon_path.read_text()
    canon_path.write_text(original_content)  # same content, new mtime

    # Second scan — mtime > last_scan, but content == snapshot → no drift
    result = scan_all_projects(str(tmp_path), registry)

    assert result["drift_events"] == []
    assert result["drift_detected"] is False
    assert result["pass"] is True


def test_missing_canon_file_skipped(tmp_path):
    """has_canon=True but CANON.md file absent — treated as no_canon, no error raised."""
    registry = [
        {
            "name": "missing-project",
            "canon_path": str(tmp_path / "missing-project" / "CANON.md"),
            "has_canon": True,
        }
    ]
    # File intentionally NOT created

    # Must not raise FileNotFoundError
    result = scan_all_projects(str(tmp_path), registry)

    assert result["projects_scanned"] == 0
    assert result["drift_events"] == []
    assert result["pass"] is True


def test_last_scan_updated(tmp_path):
    """last_drift_scan.txt is written after every scan."""
    registry = []
    scan_all_projects(str(tmp_path), registry)

    last_scan_path = tmp_path / ".agent" / "last_drift_scan.txt"
    assert last_scan_path.exists()
    ts = last_scan_path.read_text().strip()
    assert len(ts) > 0  # non-empty ISO timestamp


def test_report_path_none_when_no_drift(tmp_path):
    """report_path is None when no drift events occur."""
    canon_path = tmp_path / "test-project" / "CANON.md"
    _write_canon(canon_path)

    registry = [_make_entry(tmp_path, "test-project")]

    # Bootstrap (no drift)
    result = scan_all_projects(str(tmp_path), registry)
    assert result["report_path"] is None


def test_report_path_set_when_drift(tmp_path):
    """report_path is non-None and file exists when drift is detected."""
    canon_path = tmp_path / "test-project" / "CANON.md"
    _write_canon(canon_path, status="ACTIVE")

    registry = [_make_entry(tmp_path, "test-project")]

    # Bootstrap
    scan_all_projects(str(tmp_path), registry)

    # Modify and re-scan
    time.sleep(0.05)
    _write_canon(canon_path, status="ARCHIVED")

    result = scan_all_projects(str(tmp_path), registry)

    assert result["report_path"] is not None
    report_file = Path(result["report_path"])
    assert report_file.exists()

    # Verify report content is valid JSON with expected schema
    report = json.loads(report_file.read_text())
    assert "scan_timestamp" in report
    assert "drift_events" in report
    assert len(report["drift_events"]) >= 1
