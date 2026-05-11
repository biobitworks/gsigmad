"""Coordinate version registry for gsigmad projects."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gsigmad import __version__

COORDINATION_FILENAME = "coordination.json"
TRACK_TYPES = ("EXP", "PROMPT", "RT", "REM", "TASK")
COORDINATE_KEYS = ("version", "milestone", "phase", "wave")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def coordination_path(project_root: Path | str) -> Path:
    """Return the path to the project coordination registry."""
    root = Path(project_root)
    return root / ".gsigmad" / COORDINATION_FILENAME


def package_coordinate_seed() -> tuple[int, int]:
    """Derive default version/milestone slots from the installed package version."""
    parts = str(__version__).split(".")
    raw_major = _safe_int(parts[0]) if parts else 1
    raw_minor = _safe_int(parts[1]) if len(parts) > 1 else 1
    return _normalize_slot(raw_major), _normalize_slot(raw_minor)


def default_coordination_state(
    *,
    version_slot: int | None = None,
    milestone_slot: int | None = None,
) -> dict[str, Any]:
    """Return the default coordination registry state."""
    seed_version, seed_milestone = package_coordinate_seed()
    version_value = _normalize_slot(version_slot or seed_version)
    milestone_value = _normalize_slot(milestone_slot or seed_milestone)
    return {
        "schema_version": 1,
        "coordinate": {
            "version": version_value,
            "milestone": milestone_value,
            "phase": 1,
            "wave": 1,
        },
        "track_counters": {track: 0 for track in TRACK_TYPES},
        "rerun_counters": {},
        "updated_at": _utc_now(),
    }


def load_coordination_state(
    project_root: Path | str,
    *,
    create: bool = False,
) -> dict[str, Any]:
    """Load the persisted coordination state, optionally creating it."""
    root = Path(project_root)
    path = coordination_path(root)
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Coordination registry must be a JSON object")
        normalized = _normalize_state(data)
        if normalized != data:
            save_coordination_state(root, normalized)
        return normalized

    if not (root / ".gsigmad").is_dir():
        if not create:
            raise FileNotFoundError("No .gsigmad directory found for project")
        (root / ".gsigmad").mkdir(parents=True, exist_ok=True)

    state = default_coordination_state()
    state = sync_coordination_state(root, state)
    if create:
        save_coordination_state(root, state)
    return state


def save_coordination_state(project_root: Path | str, state: dict[str, Any]) -> Path:
    """Persist normalized coordination state and return the file path."""
    root = Path(project_root)
    path = coordination_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = _normalize_state(state)
    normalized["updated_at"] = _utc_now()
    path.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def bootstrap_coordination_state(project_root: Path | str) -> Path:
    """Create the coordination registry if it does not exist and return its path."""
    root = Path(project_root)
    path = coordination_path(root)
    if path.exists():
        load_coordination_state(root, create=False)
        return path

    state = sync_coordination_state(root, default_coordination_state())
    return save_coordination_state(root, state)


def resolve_coordinate(project_root: Path | str | None = None) -> str | None:
    """Return the project's current coordinate string, or None if not initialized."""
    root = Path(project_root or Path.cwd())
    if not (root / ".gsigmad").is_dir():
        return None
    state = load_coordination_state(root, create=False)
    coordinate = state["coordinate"]
    return format_coordinate(coordinate)


def format_coordinate(coordinate: dict[str, Any]) -> str:
    """Format a coordinate dict as `vX.Y.Z.W`."""
    validate_coordinate(coordinate)
    return (
        f"v{coordinate['version']}."
        f"{coordinate['milestone']}."
        f"{coordinate['phase']}."
        f"{coordinate['wave']}"
    )


def validate_coordinate(coordinate: dict[str, Any]) -> None:
    """Validate slot bounds for a coordinate dict."""
    for key in COORDINATE_KEYS:
        value = coordinate.get(key)
        _normalize_slot(value)


def advance_coordinate(
    project_root: Path | str,
    *,
    level: str,
) -> str:
    """Advance the stored coordinate at the requested level and persist it."""
    if level not in {"wave", "phase", "milestone", "version"}:
        raise ValueError(f"Unsupported coordinate level: {level}")

    root = Path(project_root)
    state = load_coordination_state(root, create=True)
    coordinate = state["coordinate"]

    if level == "wave":
        coordinate["wave"] = _increment_slot(coordinate["wave"])
    elif level == "phase":
        coordinate["phase"] = _increment_slot(coordinate["phase"])
        coordinate["wave"] = 1
    elif level == "milestone":
        coordinate["milestone"] = _increment_slot(coordinate["milestone"])
        coordinate["phase"] = 1
        coordinate["wave"] = 1
    else:
        coordinate["version"] = _increment_slot(coordinate["version"])
        coordinate["milestone"] = 1
        coordinate["phase"] = 1
        coordinate["wave"] = 1

    save_coordination_state(root, state)
    return format_coordinate(coordinate)


def sync_coordination_state(
    project_root: Path | str,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Reconcile counters with project-local artifacts."""
    root = Path(project_root)
    normalized = _normalize_state(state or default_coordination_state())

    exp_counter = _highest_experiment_sequence(root, normalized["coordinate"]["milestone"])
    if exp_counter > normalized["track_counters"]["EXP"]:
        normalized["track_counters"]["EXP"] = exp_counter

    return normalized


def _normalize_state(state: dict[str, Any]) -> dict[str, Any]:
    normalized = default_coordination_state()
    if isinstance(state, dict):
        coordinate = state.get("coordinate", {})
        if isinstance(coordinate, dict):
            for key in COORDINATE_KEYS:
                normalized["coordinate"][key] = _normalize_slot(
                    coordinate.get(key, normalized["coordinate"][key])
                )

        track_counters = state.get("track_counters", {})
        if isinstance(track_counters, dict):
            for track in TRACK_TYPES:
                value = track_counters.get(track, 0)
                normalized["track_counters"][track] = max(0, _safe_int(value))

        rerun_counters = state.get("rerun_counters", {})
        if isinstance(rerun_counters, dict):
            normalized["rerun_counters"] = {
                str(key): max(0, _safe_int(value))
                for key, value in rerun_counters.items()
            }

        if state.get("schema_version"):
            normalized["schema_version"] = state["schema_version"]
        if state.get("updated_at"):
            normalized["updated_at"] = str(state["updated_at"])

    validate_coordinate(normalized["coordinate"])
    return normalized


def _highest_experiment_sequence(project_root: Path, milestone: int) -> int:
    experiments_dir = project_root / ".gsigmad" / "experiments"
    if not experiments_dir.is_dir():
        return 0

    prefix = f"EXP-{milestone}."
    highest = 0
    for path in experiments_dir.glob("EXP-*.yaml"):
        name = path.stem
        if not name.startswith(prefix):
            continue
        remainder = name[len(prefix):]
        seq_part = remainder.split(".", 1)[0]
        highest = max(highest, _safe_int(seq_part))
    return highest


def _normalize_slot(value: Any) -> int:
    slot = _safe_int(value)
    if not 1 <= slot <= 9:
        raise ValueError(f"Coordinate slots must be between 1 and 9; got {value!r}")
    return slot


def _increment_slot(value: Any) -> int:
    slot = _normalize_slot(value)
    if slot >= 9:
        raise ValueError(f"Coordinate slot overflow: {slot}")
    return slot + 1


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
