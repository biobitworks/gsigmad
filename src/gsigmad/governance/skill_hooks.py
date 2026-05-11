"""Deterministic governance trigger resolution for commands and skills."""
from __future__ import annotations

from typing import Any


_RULES = {
    "register": {
        "requires_project": True,
        "requires_exp_context": False,
        "closure_stage": "EXP",
        "actions": ["allocate_task_id", "allocate_prompt_id", "allocate_exp_id", "hash_prompt", "record_closure"],
    },
    "run": {
        "requires_project": True,
        "requires_exp_context": True,
        "closure_stage": "RESULTS",
        "actions": ["load_exp", "run_gate_chain", "record_results", "append_w5"],
    },
    "redteam": {
        "requires_project": True,
        "requires_exp_context": True,
        "closure_stage": "RT",
        "actions": ["load_exp", "require_results", "record_redteam", "append_w5"],
    },
    "report amend": {
        "requires_project": True,
        "requires_exp_context": True,
        "closure_stage": "REM",
        "actions": ["load_exp", "require_results", "record_remediation", "append_lab_notebook", "append_w5"],
    },
    "pause": {
        "requires_project": True,
        "requires_exp_context": False,
        "closure_stage": None,
        "actions": ["write_checkpoint", "summarize_open_chains", "append_w5"],
    },
    "resume": {
        "requires_project": True,
        "requires_exp_context": False,
        "closure_stage": None,
        "actions": ["load_latest_checkpoint", "summarize_next_step", "append_w5"],
    },
    "status": {
        "requires_project": True,
        "requires_exp_context": False,
        "closure_stage": None,
        "actions": ["summarize_experiments", "summarize_closure", "append_w5"],
    },
    "fair-check": {
        "requires_project": True,
        "requires_exp_context": True,
        "closure_stage": None,
        "actions": ["load_exp", "run_fair_assessment", "append_w5"],
    },
    "drift-scan": {
        "requires_project": True,
        "requires_exp_context": False,
        "closure_stage": None,
        "actions": ["scan_governance_drift", "append_w5"],
    },
    "run-experiment": {
        "requires_project": True,
        "requires_exp_context": True,
        "closure_stage": "RESULTS",
        "actions": ["load_exp", "run_gate_chain", "record_results", "append_w5"],
    },
    "review-report": {
        "requires_project": True,
        "requires_exp_context": True,
        "closure_stage": "REM",
        "actions": ["require_results", "record_remediation", "append_lab_notebook", "append_w5"],
    },
    "session-pause": {
        "requires_project": True,
        "requires_exp_context": False,
        "closure_stage": None,
        "actions": ["write_checkpoint", "review_open_chains"],
    },
    "session-start": {
        "requires_project": True,
        "requires_exp_context": False,
        "closure_stage": None,
        "actions": ["load_latest_checkpoint", "summarize_experiments", "summarize_closure"],
    },
}

_ALIASES = {
    "a": "audit",
    "r": "run",
    "rr": "report amend",
    "rt": "redteam",
    "session_pause": "session-pause",
    "session_start": "session-start",
    "report_amend": "report amend",
}


def required_governance_actions(name: str) -> dict[str, Any]:
    """Resolve deterministic governance actions for a command or skill name."""
    normalized = _normalize_name(name)
    canonical = _ALIASES.get(normalized, normalized)
    rule = _RULES.get(canonical)
    if rule is None:
        return {
            "name": canonical,
            "requires_project": False,
            "requires_exp_context": False,
            "closure_stage": None,
            "actions": [],
        }
    return {"name": canonical, **rule}


def _normalize_name(name: str) -> str:
    return " ".join(
        str(name).strip().lower().replace("_", "-").split()
    )
