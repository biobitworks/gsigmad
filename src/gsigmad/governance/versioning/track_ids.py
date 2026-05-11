"""Parallel track identifier allocation for gsigmad projects."""
from __future__ import annotations

import json
from pathlib import Path

from gsigmad.governance.versioning.coordinate import (
    TRACK_TYPES,
    coordination_path,
    load_coordination_state,
    save_coordination_state,
    sync_coordination_state,
)


def allocate_track_id(track_type: str, project_root: Path | str) -> str:
    """Allocate and persist the next ID for a supported track type."""
    normalized_track = str(track_type).upper()
    if normalized_track not in TRACK_TYPES:
        raise ValueError(f"Unsupported track type: {track_type}")

    root = Path(project_root)
    state = sync_coordination_state(root, load_coordination_state(root, create=True))
    counters = state["track_counters"]
    counters[normalized_track] = int(counters.get(normalized_track, 0)) + 1
    save_coordination_state(root, state)

    milestone = state["coordinate"]["milestone"]
    seq = counters[normalized_track]
    return f"{normalized_track}-{milestone}.{seq}"


def next_rerun_version(base_exp_id: str, project_root: Path | str) -> str:
    """Allocate the next rerun version for a base EXP and mirror legacy state."""
    root = Path(project_root)
    state = load_coordination_state(root, create=True)
    legacy = _load_legacy_rerun_counters(root)
    if legacy:
        for key, value in legacy.items():
            state["rerun_counters"][key] = max(
                int(state["rerun_counters"].get(key, 0)),
                int(value),
            )

    current = int(state["rerun_counters"].get(base_exp_id, 0)) + 1
    state["rerun_counters"][base_exp_id] = current
    save_coordination_state(root, state)
    _write_legacy_rerun_counters(root, state["rerun_counters"])
    return f"{base_exp_id}.{current}"


def _load_legacy_rerun_counters(project_root: Path) -> dict[str, int]:
    path = project_root / ".agent" / "exp_versions.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    return {str(key): int(value) for key, value in data.items()}


def _write_legacy_rerun_counters(project_root: Path, counters: dict[str, int]) -> None:
    agent_dir = project_root / ".agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    path = agent_dir / "exp_versions.json"
    path.write_text(json.dumps(counters, indent=2, sort_keys=True) + "\n", encoding="utf-8")
