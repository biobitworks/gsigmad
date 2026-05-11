"""Closure-chain persistence and summaries for governed experiment workflows."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TERMINAL_STATES = {"COMPLETED", "ABANDONED", "BLOCKED", "FAILED"}
STAGE_ORDER = {
    "TASK": 0,
    "PROMPT": 1,
    "EXP": 2,
    "RESULTS": 3,
    "RT": 4,
    "REM": 4,
    "LAB_NOTEBOOK": 5,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def closure_chain_path(project_root: Path | str) -> Path:
    """Return the project-local closure-chain file path."""
    root = Path(project_root)
    return root / ".gsigmad" / "closure_chain.json"


def load_chain_state(project_root: Path | str, *, create: bool = False) -> dict[str, Any]:
    """Load closure-chain state from disk."""
    path = closure_chain_path(project_root)
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Closure-chain state must be a JSON object")
        data.setdefault("schema_version", 1)
        data.setdefault("chains", {})
        data.setdefault("updated_at", _utc_now())
        return data

    if not create:
        return {"schema_version": 1, "chains": {}, "updated_at": _utc_now()}

    state = {"schema_version": 1, "chains": {}, "updated_at": _utc_now()}
    save_chain_state(project_root, state)
    return state


def save_chain_state(project_root: Path | str, state: dict[str, Any]) -> Path:
    """Persist closure-chain state and return the written path."""
    path = closure_chain_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = _utc_now()
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def ensure_chain_for_experiment(project_root: Path | str, exp_record: dict[str, Any]) -> dict[str, Any]:
    """Backfill a minimal chain entry for an existing experiment record."""
    exp_id = exp_record.get("exp_id")
    if not exp_id:
        raise ValueError("EXP record must include exp_id for closure tracking")

    root = Path(project_root)
    state = load_chain_state(root, create=True)
    chains = state.setdefault("chains", {})
    if exp_id not in chains:
        chains[exp_id] = _new_chain(exp_id)
    chain = chains[exp_id]

    if exp_record.get("task_id") and not chain.get("task_id"):
        chain["task_id"] = exp_record["task_id"]
    if exp_record.get("prompt_id") and not chain.get("prompt_id"):
        chain["prompt_id"] = exp_record["prompt_id"]
    chain["exp_id"] = exp_id
    if not chain.get("current_stage"):
        chain["current_stage"] = _highest_present_stage(chain)

    save_chain_state(root, state)
    return chain


def record_chain_event(
    project_root: Path | str,
    *,
    exp_id: str,
    stage: str,
    artifact_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    terminal_state: str | None = None,
) -> dict[str, Any]:
    """Append a closure-chain event and return the updated chain."""
    normalized_stage = stage.upper()
    if normalized_stage not in STAGE_ORDER:
        raise ValueError(f"Unsupported closure stage: {stage}")
    if terminal_state is not None and terminal_state not in TERMINAL_STATES:
        raise ValueError(f"Unsupported terminal state: {terminal_state}")

    root = Path(project_root)
    state = load_chain_state(root, create=True)
    chains = state.setdefault("chains", {})
    chain = chains.setdefault(exp_id, _new_chain(exp_id))
    _validate_stage_transition(chain, normalized_stage)

    if normalized_stage == "TASK":
        chain["task_id"] = artifact_id or chain.get("task_id")
    elif normalized_stage == "PROMPT":
        chain["prompt_id"] = artifact_id or chain.get("prompt_id")
    elif normalized_stage == "EXP":
        chain["exp_id"] = artifact_id or exp_id
    elif normalized_stage == "RESULTS":
        chain["results_id"] = artifact_id or _next_generated_id(chain, "RESULTS", exp_id)
    elif normalized_stage == "RT":
        chain["rt_id"] = artifact_id or chain.get("rt_id")
    elif normalized_stage == "REM":
        chain["rem_id"] = artifact_id or chain.get("rem_id")
    elif normalized_stage == "LAB_NOTEBOOK":
        note_id = artifact_id or append_lab_notebook_entry(
            root,
            exp_id=exp_id,
            summary=(metadata or {}).get("summary", f"Closure update for {exp_id}"),
        )
        chain["lab_notebook_entry"] = note_id

    event = {
        "timestamp": _utc_now(),
        "stage": normalized_stage,
        "artifact_id": artifact_id,
        "metadata": metadata or {},
    }
    chain.setdefault("history", []).append(event)
    chain["current_stage"] = normalized_stage
    if terminal_state:
        chain["terminal_state"] = terminal_state
    elif normalized_stage == "LAB_NOTEBOOK":
        chain["terminal_state"] = "COMPLETED"

    save_chain_state(root, state)
    return chain


def summarize_chain(chain: dict[str, Any]) -> dict[str, Any]:
    """Summarize closure completeness for a single chain."""
    missing: list[str] = []
    if not chain.get("task_id"):
        missing.append("TASK")
    if not chain.get("prompt_id"):
        missing.append("PROMPT")
    if not chain.get("exp_id"):
        missing.append("EXP")
    if not chain.get("results_id"):
        missing.append("RESULTS")
    if not (chain.get("rt_id") or chain.get("rem_id")):
        missing.append("RT/REM")
    if not chain.get("lab_notebook_entry"):
        missing.append("LAB_NOTEBOOK")

    # Replication artifacts status (REP-01) -- informational only.
    # Actual validation happens via validate_replication_artifacts() at gate time.
    rep_arts = chain.get("replication_artifacts")
    if rep_arts is None:
        replication_artifacts_status = "SKIP"  # pre-v1.7 record
    elif isinstance(rep_arts, list) and len(rep_arts) > 0:
        replication_artifacts_status = "DECLARED"
    else:
        replication_artifacts_status = "EMPTY"

    terminal_state = chain.get("terminal_state")
    return {
        "exp_id": chain.get("exp_id", "UNKNOWN"),
        "task_id": chain.get("task_id"),
        "prompt_id": chain.get("prompt_id"),
        "results_id": chain.get("results_id"),
        "rt_id": chain.get("rt_id"),
        "rem_id": chain.get("rem_id"),
        "lab_notebook_entry": chain.get("lab_notebook_entry"),
        "current_stage": chain.get("current_stage"),
        "terminal_state": terminal_state,
        "missing": missing,
        "complete": not missing and terminal_state == "COMPLETED",
        "blocked": terminal_state == "BLOCKED",
        "history_count": len(chain.get("history", [])),
        "replication_artifacts_status": replication_artifacts_status,
    }


def list_chain_summaries(project_root: Path | str) -> list[dict[str, Any]]:
    """Return sorted closure summaries for all tracked chains."""
    state = load_chain_state(project_root, create=False)
    summaries = [summarize_chain(chain) for _, chain in sorted(state.get("chains", {}).items())]
    return summaries


def next_results_artifact_id(project_root: Path | str, exp_id: str) -> str:
    """Predict the next RESULTS artifact id without mutating chain state."""
    state = load_chain_state(project_root, create=False)
    chain = state.get("chains", {}).get(exp_id, _new_chain(exp_id))
    return _next_generated_id(chain, "RESULTS", exp_id)


def append_lab_notebook_entry(project_root: Path | str, *, exp_id: str, summary: str) -> str:
    """Append a concise notebook entry and return its generated entry ID."""
    root = Path(project_root)
    notebook = root / ".gsigmad" / "LAB_NOTEBOOK.md"
    notebook.parent.mkdir(parents=True, exist_ok=True)
    if not notebook.exists():
        notebook.write_text("# Lab Notebook\n\n", encoding="utf-8")

    existing = notebook.read_text(encoding="utf-8")
    entry_id = _next_notebook_id(existing, exp_id)
    line = f"- [{_utc_now()}] {entry_id} {summary}\n"
    with notebook.open("a", encoding="utf-8") as handle:
        handle.write(line)
    return entry_id


def _new_chain(exp_id: str) -> dict[str, Any]:
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


def _validate_stage_transition(chain: dict[str, Any], stage: str) -> None:
    current_stage = chain.get("current_stage")
    prerequisites = {
        "PROMPT": current_stage == "TASK" or chain.get("task_id") is not None,
        "EXP": current_stage in {"PROMPT", "EXP", "RESULTS", "RT", "REM", "LAB_NOTEBOOK"},
        "RESULTS": current_stage in {"EXP", "RESULTS", "RT", "REM", "LAB_NOTEBOOK"},
        "RT": current_stage in {"EXP", "RESULTS", "RT", "REM", "LAB_NOTEBOOK"},
        "REM": current_stage in {"EXP", "RESULTS", "RT", "REM", "LAB_NOTEBOOK"},
        "LAB_NOTEBOOK": current_stage in {"RT", "REM", "LAB_NOTEBOOK"},
    }
    if stage in prerequisites and not prerequisites[stage]:
        raise ValueError(f"Cannot record {stage} before prerequisites are satisfied")

    if current_stage is None:
        return
    if STAGE_ORDER[stage] < STAGE_ORDER[current_stage]:
        raise ValueError(f"Cannot move closure chain backwards from {current_stage} to {stage}")


def _highest_present_stage(chain: dict[str, Any]) -> str | None:
    present = []
    if chain.get("task_id"):
        present.append("TASK")
    if chain.get("prompt_id"):
        present.append("PROMPT")
    if chain.get("exp_id"):
        present.append("EXP")
    if chain.get("results_id"):
        present.append("RESULTS")
    if chain.get("rt_id"):
        present.append("RT")
    if chain.get("rem_id"):
        present.append("REM")
    if chain.get("lab_notebook_entry"):
        present.append("LAB_NOTEBOOK")
    if not present:
        return None
    return max(present, key=lambda item: STAGE_ORDER[item])


def _next_generated_id(chain: dict[str, Any], label: str, exp_id: str) -> str:
    count = sum(1 for event in chain.get("history", []) if event.get("stage") == label) + 1
    return f"{label}-{exp_id}-{count}"


def _next_notebook_id(contents: str, exp_id: str) -> str:
    prefix = f"NOTE-{exp_id}-"
    count = sum(1 for line in contents.splitlines() if prefix in line) + 1
    return f"{prefix}{count}"
