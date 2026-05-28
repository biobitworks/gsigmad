"""
Scheduled cross-project CANON drift detection — D-07/D-08/D-09.

Scans all registered projects for CANON classification changes since the last
scheduled check. Implements a three-step pipeline:

  1. mtime shortcut — skip files unchanged since last_drift_scan.txt (D-09)
  2. Content comparison — parse CANON header and compare to stored snapshot
     (avoids false positives from git operations that update mtime, Pitfall 3)
  3. Snapshot update — write updated state after change is recorded

Produces machine-readable drift reports at:
  .agent/drift_reports/DRIFT-{timestamp}.json

Only writes a report when classification changes are actually detected.
Updates .agent/last_drift_scan.txt after every successful scan regardless of
whether drift was found — enabling the 24-hour cron trigger pattern (D-09).

Projects with has_canon=False or missing CANON.md are silently skipped (D-07,
Pitfall 4, Pitfall 6 — the 24-hour trigger applies only to CANON-bearing projects).

Reference decisions: D-07 (scheduled scan), D-08 (DRIFT JSON schema),
                     D-09 (24-hour mtime trigger).
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path


# Regex patterns to extract CANON header block fields.
# Matches both "**Status**: VALUE" (bold) and "> **Status**: VALUE" (blockquote + bold).
_CANON_STATUS_RE = re.compile(r"^>?\s*\*\*Status\*\*:\s*(.+)$", re.MULTILINE)
_CANON_VERSION_RE = re.compile(r"^>?\s*\*\*Version\*\*:\s*(.+)$", re.MULTILINE)


def _parse_canon_header(canon_text: str) -> dict:
    """
    Extract the minimal classification state from a CANON.md header block.

    Parses ``**Status**`` and ``**Version**`` fields using regex. Returns
    ``{"status": "UNKNOWN", "version": "UNKNOWN"}`` for any absent field.

    Args:
        canon_text: Full text content of a CANON.md file.

    Returns:
        dict with keys ``status`` and ``version`` (both str).
    """
    status_match = _CANON_STATUS_RE.search(canon_text)
    version_match = _CANON_VERSION_RE.search(canon_text)

    return {
        "status": status_match.group(1).strip() if status_match else "UNKNOWN",
        "version": version_match.group(1).strip() if version_match else "UNKNOWN",
    }


def scan_all_projects(gsd_root: str, project_registry: list) -> dict:
    """
    Scan all registered projects for CANON classification changes.

    Implements the three-step pipeline: mtime shortcut → content comparison →
    snapshot update. Writes a DRIFT JSON report only when actual classification
    changes are detected. Always updates last_drift_scan.txt on completion.

    Args:
        gsd_root:
            Path to the governance workspace root (contains the .agent/
            subdirectory where scan state is stored).
        project_registry:
            List of project entry dicts. Each dict must contain:
              - ``name`` (str): Unique project identifier.
              - ``canon_path`` (str): Absolute path to the project's CANON.md.
              - ``has_canon`` (bool): False for projects without CANON.md.
            Projects with ``has_canon=False`` or a missing CANON.md file are
            silently skipped without generating drift events (Pitfall 4).

    Returns:
        dict with keys:

        - ``pass`` (bool): False if any drift was detected.
        - ``scan_timestamp`` (str): ISO 8601 UTC timestamp of this scan.
        - ``projects_scanned`` (int): Number of projects whose CANON.md was parsed.
        - ``drift_detected`` (bool): True if any drift events were emitted.
        - ``drift_events`` (list): List of drift event dicts (empty when no drift).
        - ``report_path`` (str | None): Path to the written DRIFT JSON report,
          or None when no drift was detected.
    """
    # 1. Resolve paths and ensure required directories exist.
    root = Path(gsd_root)
    agent_dir = root / ".agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "drift_reports").mkdir(exist_ok=True)
    (agent_dir / "drift_snapshots").mkdir(exist_ok=True)

    # 2. Read last scan timestamp (for mtime shortcut).
    last_scan_path = agent_dir / "last_drift_scan.txt"
    last_scan_dt = None
    if last_scan_path.exists():
        raw_ts = last_scan_path.read_text().strip()
        if raw_ts:
            try:
                last_scan_dt = datetime.fromisoformat(raw_ts)
            except ValueError:
                last_scan_dt = None

    # 3. Record the scan start timestamp (ISO 8601 UTC).
    scan_timestamp = datetime.now(timezone.utc).isoformat()

    # 4. Scan each project.
    drift_events = []
    projects_scanned = 0

    for entry in project_registry:
        # Skip projects explicitly marked as having no CANON.md.
        if not entry.get("has_canon", True):
            continue

        canon_path = Path(entry["canon_path"])

        # Skip projects where the CANON.md file does not exist on disk (Pitfall 4).
        if not canon_path.exists():
            continue

        projects_scanned += 1

        # --- Step 1: mtime shortcut ---
        # If the file hasn't been modified since the last scan, skip it.
        mtime_dt = datetime.fromtimestamp(canon_path.stat().st_mtime, tz=timezone.utc)
        if last_scan_dt is not None and mtime_dt <= last_scan_dt:
            continue

        # --- Step 2: Parse current header state ---
        current_state = _parse_canon_header(canon_path.read_text(encoding="utf-8"))

        snap_path = (
            agent_dir / "drift_snapshots" / f"{entry['name']}_canon_state.json"
        )

        # Bootstrap: no prior snapshot exists → create one, no drift event.
        if not snap_path.exists():
            snap_path.write_text(json.dumps(current_state, indent=2))
            continue

        # --- Step 3: Content comparison (Pitfall 3 false positive prevention) ---
        prior_state = json.loads(snap_path.read_text())
        if current_state == prior_state:
            # mtime changed (e.g., git operation) but content is identical.
            continue

        # Drift detected: emit one event per changed field.
        for key in current_state:
            if current_state[key] != prior_state.get(key):
                drift_events.append(
                    {
                        "project": entry["name"],
                        "invariant_changed": key,
                        "old_classification": prior_state.get(key, "UNKNOWN"),
                        "new_classification": current_state[key],
                        "detected_timestamp": scan_timestamp,
                    }
                )

        # Update the snapshot to reflect the new state.
        snap_path.write_text(json.dumps(current_state, indent=2))

    # 5. Write DRIFT report only when drift events exist (D-08).
    report_path = None
    if drift_events:
        # Sanitize the timestamp for use as a filename component.
        safe_ts = scan_timestamp.replace(":", "-").replace(".", "-")
        report_file = agent_dir / "drift_reports" / f"DRIFT-{safe_ts}.json"
        report_file.write_text(
            json.dumps(
                {"scan_timestamp": scan_timestamp, "drift_events": drift_events},
                indent=2,
            )
        )
        report_path = str(report_file)

    # 6. Always update last_drift_scan.txt (enables 24-hour cron trigger, D-09).
    last_scan_path.write_text(scan_timestamp)

    return {
        "pass": len(drift_events) == 0,
        "scan_timestamp": scan_timestamp,
        "projects_scanned": projects_scanned,
        "drift_detected": len(drift_events) > 0,
        "drift_events": drift_events,
        "report_path": report_path,
    }
