"""Structured pause/resume checkpoint helpers."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gsigmad.governance.closure_chain import list_chain_summaries
from gsigmad.governance.versioning import resolve_coordinate


def checkpoint_dir(project_root: Path | str) -> Path:
    """Return the directory containing structured checkpoints."""
    root = Path(project_root)
    return root / ".gsigmad" / "context" / "checkpoints"


def latest_checkpoint_path(project_root: Path | str) -> Path:
    """Return the pointer file for the latest checkpoint."""
    root = Path(project_root)
    return root / ".gsigmad" / "context" / "latest.json"


def write_checkpoint(
    project_root: Path | str,
    *,
    note: str = "",
    recommended_command: str | None = None,
) -> dict[str, Any]:
    """Write a structured checkpoint and return its payload."""
    root = Path(project_root)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    closures = list_chain_summaries(root)
    payload = {
        "timestamp": timestamp,
        "coordinate": resolve_coordinate(root),
        "open_chains": [item for item in closures if not item.get("complete")],
        "recommended_command": recommended_command or recommend_next_command(closures),
        "note": note,
    }

    target_dir = checkpoint_dir(root)
    target_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = target_dir / f"{timestamp}.json"
    checkpoint_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    latest_path = latest_checkpoint_path(root)
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    payload["path"] = str(checkpoint_path)
    return payload


def load_latest_checkpoint(project_root: Path | str) -> dict[str, Any] | None:
    """Load the latest structured checkpoint, if present."""
    path = latest_checkpoint_path(project_root)
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    payload.setdefault("path", str(path))
    return payload


def recommend_next_command(closures: list[dict[str, Any]]) -> str:
    """Return a deterministic next-step hint from closure summaries."""
    for closure in closures:
        exp_id = closure.get("exp_id", "")
        if closure.get("blocked") and not closure.get("rem_id"):
            return f"gsigmad report amend {exp_id} --json-file <payload>"
        missing = closure.get("missing", [])
        if "RESULTS" in missing:
            return f"gsigmad run {exp_id}"
        if "RT/REM" in missing:
            return f"gsigmad redteam {exp_id}"
        if "LAB_NOTEBOOK" in missing:
            return f"gsigmad report amend {exp_id} --json-file <payload>"
    return "gsigmad status"
