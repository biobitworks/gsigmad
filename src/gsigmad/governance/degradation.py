"""Shared runtime degradation state for local-first command execution."""
from __future__ import annotations

import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FULL_SERVICE = "FULL_SERVICE"
KG_DEGRADED = "KG_DEGRADED"
MONITOR_DEGRADED = "MONITOR_DEGRADED"
CORE_ONLY = "CORE_ONLY"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _degradation_path(project_root: Path | str) -> Path:
    return Path(project_root).resolve() / ".gsigmad" / "degradation.json"


def _probe_kg_available() -> bool:
    try:
        from gsigmad.governance.kg.writer import _ARANGO_HOST, ARANGO_AVAILABLE

        if not ARANGO_AVAILABLE:
            return False
        host = _ARANGO_HOST
        if host.startswith("http://"):
            host = host[len("http://") :]
        elif host.startswith("https://"):
            host = host[len("https://") :]
        if "/" in host:
            host = host.split("/", 1)[0]
        hostname, _, port_text = host.partition(":")
        port = int(port_text or "8531")
        with socket.create_connection((hostname, port), timeout=0.2):
            return True
    except Exception:
        return False


def _probe_monitoring_available(project_root: Path | str) -> bool:
    root = Path(project_root).resolve()
    gsigmad_dir = root / ".gsigmad"
    if not gsigmad_dir.is_dir():
        return False
    return os.access(gsigmad_dir, os.W_OK)


def compute_degradation_state(
    project_root: Path | str,
    *,
    kg_available: bool | None = None,
    monitoring_available: bool | None = None,
) -> dict[str, Any]:
    """Compute the current runtime degradation tier for a project."""
    root = Path(project_root).resolve()
    kg_ok = _probe_kg_available() if kg_available is None else bool(kg_available)
    monitoring_ok = _probe_monitoring_available(root) if monitoring_available is None else bool(monitoring_available)

    unavailable_services: list[str] = []
    if not kg_ok:
        unavailable_services.append("kg")
    if not monitoring_ok:
        unavailable_services.append("monitoring")

    if kg_ok and monitoring_ok:
        tier = FULL_SERVICE
    elif (not kg_ok) and monitoring_ok:
        tier = KG_DEGRADED
    elif kg_ok and (not monitoring_ok):
        tier = MONITOR_DEGRADED
    else:
        tier = CORE_ONLY

    return {
        "tier": tier,
        "unavailable_services": unavailable_services,
        "detected_at": _utc_now(),
    }


def write_degradation_state(project_root: Path | str, state: dict[str, Any]) -> Path:
    """Persist the current degradation state for downstream commands and monitoring."""
    path = _degradation_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_degradation_state(project_root: Path | str) -> dict[str, Any] | None:
    """Load the persisted degradation state if one exists."""
    path = _degradation_path(project_root)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def emit_degraded_banner(state: dict[str, Any], *, json_output: bool) -> None:
    """Emit a shared rich banner when operating below full service."""
    if json_output or state.get("tier") == FULL_SERVICE:
        return

    import rich

    unavailable = ", ".join(state.get("unavailable_services", [])) or "unknown"
    rich.print(f"[yellow][DEGRADED][/yellow] {state['tier']} — unavailable: {unavailable}")
