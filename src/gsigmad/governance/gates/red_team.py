"""
Red team pre-execution gate — GOV-03.

Makes the red team step NON-OPTIONAL for CONFIRMATORY experiments.
Checks that PROMPT-### has: risk_tier, red_team_status=PASS,
remediation_constraints (non-empty), execution_decision=GO.

Reference: CANON-CORE Invariant 8, WORKFLOW_RULES §2b, EXPERIMENT_STANDARDS.md §2
"""
from typing import Optional

# -- TRAITS pillar mapping (REP-02) --

TRAITS_PILLARS: dict[str, list[str]] = {
    "red_team": ["Rigorous", "Transparent"],
}

# Required fields in the PROMPT-### for CONFIRMATORY experiments.
# Note: challenge_target is NOT in this list -- it is a metadata field for
# RT record tracking (REP-03, D-14), not a gate-blocking field.  When present
# in prompt_fields it passes through without validation because the gate only
# checks _REQUIRED_CONFIRMATORY_FIELDS.
_REQUIRED_CONFIRMATORY_FIELDS = ["risk_tier", "red_team_status", "remediation_constraints", "execution_decision"]


def check_red_team_gate(classification: str, prompt_fields: dict) -> dict:
    """
    Verify the red team gate for experiment execution.

    Args:
        classification: "CONFIRMATORY", "EXPLORATORY", or "REPLICATION"
        prompt_fields: Dict of fields from the experiment's PROMPT-### file.
                       Required keys for CONFIRMATORY: risk_tier, red_team_status,
                       remediation_constraints, execution_decision.

    Returns:
        {"pass": bool, "error": Optional[str], "log": Optional[str]}
    """
    # EXPLORATORY and REPLICATION: red team is RECOMMENDED but not blocking
    if classification in ("EXPLORATORY", "REPLICATION"):
        return {
            "pass": True,
            "error": None,
            "log": f"RED_TEAM_STATUS: not required for {classification} classification."
        }

    # CONFIRMATORY: red team is mandatory and blocking
    missing_fields = []
    for field in _REQUIRED_CONFIRMATORY_FIELDS:
        if field not in prompt_fields or not prompt_fields[field]:
            missing_fields.append(field)

    if missing_fields:
        return {
            "pass": False,
            "error": (
                "RED TEAM GATE FAILED — CONFIRMATORY experiment cannot execute without completed red team. "
                f"Missing or incomplete fields: {', '.join(missing_fields)}. "
                "Required by: CANON-CORE Invariant 8, EXPERIMENT_STANDARDS.md §2. "
                "Fix: Complete the pre-execution red team in PROMPT-### before re-running. "
                "Required fields: risk_tier (P0/P1/P2), red_team_status (PASS), "
                "remediation_constraints (non-empty list), execution_decision (GO)."
            ),
            "log": None
        }

    # Check specific values
    red_team_status = prompt_fields.get("red_team_status", "")
    if red_team_status != "PASS":
        return {
            "pass": False,
            "error": (
                f"RED TEAM GATE FAILED — CONFIRMATORY experiment cannot execute without completed red team. "
                f"red_team_status is '{red_team_status}' — must be 'PASS'. "
                "Fix: Complete the red team review and set red_team_status: PASS in PROMPT-###."
            ),
            "log": None
        }

    execution_decision = prompt_fields.get("execution_decision", "")
    if execution_decision != "GO":
        return {
            "pass": False,
            "error": (
                f"RED TEAM GATE FAILED — execution_decision is '{execution_decision}' — must be 'GO'. "
                "The red team must explicitly authorize execution before proceeding."
            ),
            "log": None
        }

    # Check remediation_constraints is non-empty list
    constraints = prompt_fields.get("remediation_constraints", [])
    if not constraints or (isinstance(constraints, list) and len(constraints) == 0):
        return {
            "pass": False,
            "error": (
                "RED TEAM GATE FAILED — remediation_constraints is empty. "
                "Must list at least one constraint (not 'N/A'). "
                "If no constraints exist, document why: 'No scope constraints identified — "
                "confirmed by red team that full execution is safe.'"
            ),
            "log": None
        }

    # All checks pass
    return {
        "pass": True,
        "error": None,
        "log": (
            f"RED_TEAM_GATE: PASS. "
            f"risk_tier={prompt_fields['risk_tier']}, "
            f"constraints={len(constraints)} documented."
        )
    }
