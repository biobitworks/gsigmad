"""Local-first operational monitoring for native and routed projects."""
from __future__ import annotations

import json
import re
import shlex
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gsigmad.governance.adapters.runtime import (
    ProjectResolution,
    build_compatibility_report,
    discover_registry_root,
    inspect_payload,
    resolve_project_target,
)
from gsigmad.governance.compiler.drift_scanner import scan_all_projects
from gsigmad.governance.degradation import compute_degradation_state, write_degradation_state
from gsigmad.governance.kg.queue_ops import inspect_queue_state
from gsigmad.governance.kg.writer import _get_db

_CANON_STATUS_RE = re.compile(r"^>?\s*\*\*Status\*\*:\s*(.+)$", re.MULTILINE)
_CANON_VERSION_RE = re.compile(r"^>?\s*\*\*Version\*\*:\s*(.+)$", re.MULTILINE)


@dataclass
class MonitoringPaths:
    """Filesystem locations used by operational monitoring."""

    root: Path
    latest_file: Path
    baseline_file: Path
    install_state_file: Path
    open_alert_file: Path
    history_dir: Path
    alerts_dir: Path
    launchd_dir: Path
    cron_dir: Path


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_timestamp(ts: datetime | None = None) -> str:
    return (ts or _utc_now()).isoformat().replace("+00:00", "Z")


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "project"


def _monitoring_root(resolution: ProjectResolution) -> Path:
    surfaces = resolution.surfaces
    if resolution.source == "native_gsigmad":
        return resolution.project_root / ".gsigmad" / "monitoring"
    if surfaces.get("gsigmad_dir"):
        return Path(str(surfaces["gsigmad_dir"])) / "monitoring"
    if surfaces.get("legacy_state_dir"):
        return Path(str(surfaces["legacy_state_dir"])) / "gsigmad-monitoring"
    return resolution.project_root / ".agent" / "gsigmad-monitoring"


def monitoring_paths(target_path: Path | str | None = None) -> tuple[ProjectResolution, MonitoringPaths]:
    """Resolve a target path and derive monitoring artifact locations."""
    target = Path(target_path or Path.cwd()).resolve()
    registry_root = discover_registry_root(Path.cwd())
    resolution = resolve_project_target(target, registry_root=registry_root)
    root = _monitoring_root(resolution)
    paths = MonitoringPaths(
        root=root,
        latest_file=root / "latest.json",
        baseline_file=root / "baseline.json",
        install_state_file=root / "install-state.json",
        open_alert_file=root / "open-alert.json",
        history_dir=root / "history",
        alerts_dir=root / "alerts",
        launchd_dir=root / "launchd",
        cron_dir=root / "cron",
    )
    return resolution, paths


def _ensure_monitoring_dirs(paths: MonitoringPaths) -> None:
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.history_dir.mkdir(parents=True, exist_ok=True)
    paths.alerts_dir.mkdir(parents=True, exist_ok=True)
    paths.launchd_dir.mkdir(parents=True, exist_ok=True)
    paths.cron_dir.mkdir(parents=True, exist_ok=True)


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _canon_state(resolution: ProjectResolution) -> dict[str, Any]:
    canon_path = None
    if resolution.surfaces.get("canon_path"):
        canon_path = Path(str(resolution.surfaces["canon_path"]))
    else:
        candidate = resolution.project_root / "CANON.md"
        if candidate.exists():
            canon_path = candidate
    if canon_path is None or not canon_path.exists():
        return {"present": False, "path": str(canon_path) if canon_path else None, "status": "UNKNOWN", "version": "UNKNOWN"}

    text = canon_path.read_text(encoding="utf-8")
    status_match = _CANON_STATUS_RE.search(text)
    version_match = _CANON_VERSION_RE.search(text)
    return {
        "present": True,
        "path": str(canon_path),
        "status": status_match.group(1).strip() if status_match else "UNKNOWN",
        "version": version_match.group(1).strip() if version_match else "UNKNOWN",
    }


def _drift_state(resolution: ProjectResolution) -> dict[str, Any]:
    canon = _canon_state(resolution)
    registry = [
        {
            "name": resolution.project_name,
            "canon_path": canon["path"] or str(resolution.project_root / "CANON.md"),
            "has_canon": canon["present"],
        }
    ]
    result = scan_all_projects(str(resolution.project_root), registry)
    return {
        "pass": result["pass"],
        "drift_detected": result["drift_detected"],
        "projects_scanned": result["projects_scanned"],
        "report_path": result["report_path"],
        "event_count": len(result["drift_events"]),
        "events": result["drift_events"],
    }


def _kg_state() -> dict[str, Any]:
    try:
        db = _get_db()
        # A lightweight metadata call is enough to prove connectivity/auth.
        db.collections()
        return {"available": True, "error": None}
    except Exception as exc:  # pragma: no cover - exercised through tests with monkeypatches
        return {"available": False, "error": str(exc)}


def _queue_state(resolution: ProjectResolution) -> dict[str, Any]:
    snapshot = inspect_queue_state(resolution.project_root)
    counts = snapshot["counts"]
    return {
        "pending_count": counts["pending"],
        "failed_count": counts["failed"],
        "expired_count": counts["expired"],
        "quarantine_count": counts["quarantine"],
        "retry_scheduled_count": counts["retry_scheduled"],
        "dead_letter_count": counts["dead_letter"],
    }


def _signature(scan: dict[str, Any]) -> dict[str, Any]:
    return {
        "runtime_mode": scan["routing"]["runtime_mode"],
        "resolution_source": scan["routing"]["source"],
        "unsupported_commands": scan["compatibility"]["unsupported_commands"],
        "canon_status": scan["canon"]["status"],
        "canon_version": scan["canon"]["version"],
        "kg_available": scan["kg"]["available"],
        "queue_pending": scan["queue"]["pending_count"],
        "queue_failed": scan["queue"]["failed_count"],
        "queue_expired": scan["queue"]["expired_count"],
        "queue_quarantine": scan["queue"]["quarantine_count"],
        "queue_retry_scheduled": scan["queue"]["retry_scheduled_count"],
        "queue_dead_letter": scan["queue"]["dead_letter_count"],
        "drift_detected": scan["drift"]["drift_detected"],
        "degradation_tier": scan["degradation"]["tier"],
        "degradation_services": scan["degradation"]["unavailable_services"],
    }


def _diff_signature(previous: dict[str, Any] | None, current: dict[str, Any]) -> list[dict[str, Any]]:
    if not previous:
        return []
    changes: list[dict[str, Any]] = []
    for key, current_value in current.items():
        old_value = previous.get(key)
        if old_value != current_value:
            changes.append({"field": key, "old": old_value, "new": current_value})
    return changes


def _change_categories(changes: list[dict[str, Any]]) -> list[str]:
    categories: set[str] = set()
    for item in changes:
        field = item["field"]
        if field.startswith("canon_"):
            categories.add("canon")
        elif field in {"runtime_mode", "resolution_source"}:
            categories.add("routing")
        elif field == "unsupported_commands":
            categories.add("compatibility")
        elif field == "kg_available":
            categories.add("kg")
        elif field.startswith("queue_"):
            categories.add("queue")
        elif field == "drift_detected":
            categories.add("drift")
        elif field.startswith("degradation_"):
            categories.add("degradation")
        else:
            categories.add("other")
    return sorted(categories)


def collect_monitoring_scan(target_path: Path | str | None = None, *, write_artifacts: bool = True) -> dict[str, Any]:
    """Collect one operational monitoring snapshot for a target project."""
    resolution, paths = monitoring_paths(target_path)
    if resolution.source == "unresolved":
        raise ValueError("Target is not routed safely for monitoring.")

    now = _utc_now()
    routing = inspect_payload(resolution)
    compatibility = build_compatibility_report(resolution)
    canon = _canon_state(resolution)
    drift = _drift_state(resolution)
    kg = _kg_state()
    queue = _queue_state(resolution)
    degradation = compute_degradation_state(
        resolution.project_root,
        kg_available=kg["available"],
        monitoring_available=True,
    )
    baseline = _load_json(paths.baseline_file)
    latest = _load_json(paths.latest_file)

    scan = {
        "generated_at": _iso_timestamp(now),
        "project_root": str(resolution.project_root),
        "project_name": resolution.project_name,
        "routing": {
            "runtime_mode": routing["runtime_mode"],
            "source": routing["source"],
            "namespace_prefix": routing["namespace_prefix"],
            "manifest_path": routing["manifest_path"],
        },
        "compatibility": {
            "supported_commands": compatibility["supported_commands"],
            "unsupported_commands": compatibility["unsupported_commands"],
        },
        "canon": canon,
        "drift": drift,
        "kg": kg,
        "queue": queue,
        "degradation": degradation,
        "baseline": {
            "present": baseline is not None,
            "generated_at": baseline.get("generated_at") if baseline else None,
            "source": "baseline" if baseline else ("latest" if latest else None),
        },
        "install_state": _load_json(paths.install_state_file),
    }
    signature = _signature(scan)
    reference_signature = baseline.get("signature") if baseline else (latest.get("signature") if latest else None)
    changes = _diff_signature(reference_signature, signature)
    categories = _change_categories(changes)
    scan["signature"] = signature
    scan["changes"] = changes
    scan["summary"] = {
        "pass": kg["available"]
        and queue["failed_count"] == 0
        and queue["expired_count"] == 0
        and queue["quarantine_count"] == 0,
        "change_count": len(changes),
        "change_categories": categories,
        "has_alert": False,
    }

    alert_payload: dict[str, Any] | None = None
    open_alert = _load_json(paths.open_alert_file)
    fingerprint = "|".join(f"{item['field']}={item['old']}->{item['new']}" for item in changes)
    if changes:
        scan["summary"]["pass"] = False
        if not open_alert or open_alert.get("fingerprint") != fingerprint:
            alert_payload = {
                "generated_at": scan["generated_at"],
                "project_root": scan["project_root"],
                "project_name": scan["project_name"],
                "severity": "warning",
                "fingerprint": fingerprint,
                "changes": changes,
                "change_categories": categories,
                "baseline_generated_at": baseline.get("generated_at") if baseline else None,
            }
            scan["summary"]["has_alert"] = True
        else:
            scan["summary"]["has_alert"] = True
    elif write_artifacts and paths.open_alert_file.exists():
        paths.open_alert_file.unlink()

    if write_artifacts:
        _ensure_monitoring_dirs(paths)
        write_degradation_state(resolution.project_root, degradation)
        stamp = now.strftime("%Y%m%dT%H%M%SZ")
        _write_json(paths.history_dir / f"SCAN-{stamp}.json", scan)
        _write_json(paths.latest_file, scan)
        if alert_payload is not None:
            alert_file = paths.alerts_dir / f"ALERT-{stamp}.json"
            _write_json(alert_file, alert_payload)
            _write_json(paths.open_alert_file, {**alert_payload, "path": str(alert_file)})

    return scan


def set_monitoring_baseline(target_path: Path | str | None = None) -> dict[str, Any]:
    """Acknowledge the current monitoring state as the new baseline."""
    resolution, paths = monitoring_paths(target_path)
    latest = _load_json(paths.latest_file)
    scan = latest or collect_monitoring_scan(target_path, write_artifacts=True)
    baseline = {
        "generated_at": _iso_timestamp(),
        "project_root": scan["project_root"],
        "project_name": scan["project_name"],
        "signature": scan["signature"],
    }
    _ensure_monitoring_dirs(paths)
    _write_json(paths.baseline_file, baseline)
    if paths.open_alert_file.exists():
        paths.open_alert_file.unlink()
    return {"pass": True, "baseline": baseline}


def install_monitoring_schedule(
    target_path: Path | str | None = None,
    *,
    scheduler: str = "launchd",
    interval_minutes: int = 60,
) -> dict[str, Any]:
    """Create local-first scheduler artifacts for monitoring."""
    if scheduler not in {"launchd", "cron"}:
        raise ValueError("scheduler must be 'launchd' or 'cron'")
    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be > 0")

    resolution, paths = monitoring_paths(target_path)
    _ensure_monitoring_dirs(paths)
    label = f"dev.gsigmad.monitor.{_safe_slug(resolution.project_name)}"
    command = [sys.executable, "-m", "gsigmad", "--json", "monitor", "scan", str(resolution.project_root)]
    quoted_command = " ".join(shlex.quote(part) for part in command)

    state = _load_json(paths.install_state_file) or {"installs": {}}
    record = {
        "scheduler": scheduler,
        "interval_minutes": interval_minutes,
        "label": label,
        "command": command,
        "project_root": str(resolution.project_root),
        "generated_at": _iso_timestamp(),
    }

    if scheduler == "launchd":
        plist_path = paths.launchd_dir / f"{label}.plist"
        plist_content = "\n".join(
            [
                "<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
                "<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">",
                "<plist version=\"1.0\">",
                "<dict>",
                f"  <key>Label</key><string>{label}</string>",
                "  <key>ProgramArguments</key>",
                "  <array>",
                *[f"    <string>{part}</string>" for part in command],
                "  </array>",
                f"  <key>StartInterval</key><integer>{interval_minutes * 60}</integer>",
                "</dict>",
                "</plist>",
                "",
            ]
        )
        plist_path.write_text(plist_content, encoding="utf-8")
        record["artifact_path"] = str(plist_path)
    else:
        script_path = paths.cron_dir / f"{label}.sh"
        script_content = "\n".join(
            [
                "#!/bin/sh",
                f"cd {shlex.quote(str(resolution.project_root))} || exit 1",
                f"exec {quoted_command}",
                "",
            ]
        )
        script_path.write_text(script_content, encoding="utf-8")
        script_path.chmod(0o755)
        cron_path = paths.cron_dir / f"{label}.cron"
        cron_line = (
            f"* * * * * [ $(( $(date +\\%s) / 60 % {interval_minutes} )) -eq 0 ]"
            f" && {shlex.quote(str(script_path))}\n"
        )
        cron_path.write_text(cron_line, encoding="utf-8")
        record["artifact_path"] = str(cron_path)
        record["script_path"] = str(script_path)

    state["installs"][scheduler] = record
    _write_json(paths.install_state_file, state)
    return {"pass": True, "install": record}


def uninstall_monitoring_schedule(
    target_path: Path | str | None = None,
    *,
    scheduler: str | None = None,
) -> dict[str, Any]:
    """Remove generated scheduler artifacts."""
    resolution, paths = monitoring_paths(target_path)
    state = _load_json(paths.install_state_file) or {"installs": {}}
    installs = state.get("installs", {})
    schedulers = [scheduler] if scheduler else list(installs.keys())
    removed: list[str] = []

    for item in schedulers:
        if item not in installs:
            continue
        artifact_path = Path(installs[item]["artifact_path"])
        if artifact_path.exists():
            artifact_path.unlink()
        script_path = installs[item].get("script_path")
        if script_path:
            script = Path(script_path)
            if script.exists():
                script.unlink()
        installs.pop(item, None)
        removed.append(item)

    state["installs"] = installs
    _write_json(paths.install_state_file, state)
    return {
        "pass": True,
        "project_name": resolution.project_name,
        "removed": removed,
        "remaining": sorted(installs.keys()),
    }


def monitoring_history(target_path: Path | str | None = None, *, limit: int = 10) -> dict[str, Any]:
    """Return recent monitoring scans from local history."""
    _, paths = monitoring_paths(target_path)
    if limit <= 0:
        raise ValueError("limit must be > 0")
    entries = sorted(paths.history_dir.glob("SCAN-*.json"), reverse=True)[:limit]
    scans = [json.loads(path.read_text(encoding="utf-8")) for path in entries]
    return {"pass": True, "count": len(scans), "scans": scans}


def monitoring_summary(target_path: Path | str | None = None, *, limit: int = 10) -> dict[str, Any]:
    """Return a stable machine-readable summary for current monitoring health."""
    resolution, paths = monitoring_paths(target_path)
    latest = _load_json(paths.latest_file)
    history = monitoring_history(target_path, limit=limit)
    baseline = _load_json(paths.baseline_file)
    open_alert = _load_json(paths.open_alert_file)
    install_state = _load_json(paths.install_state_file)

    latest_scan = latest or collect_monitoring_scan(target_path, write_artifacts=False)
    recent_scans = history["scans"]
    change_count = sum(1 for item in recent_scans if item.get("changes"))
    last_success = next((item["generated_at"] for item in recent_scans if item.get("summary", {}).get("pass")), None)
    return {
        "pass": True,
        "project_name": resolution.project_name,
        "project_root": str(resolution.project_root),
        "current": latest_scan,
        "history": {
            "count": history["count"],
            "recent_change_count": change_count,
            "last_successful_scan": last_success,
            "scans": recent_scans,
        },
        "baseline": baseline,
        "open_alert": open_alert,
        "install_state": install_state,
    }
