"""
Automated drift detection — GOV-01.

Increments a per-project counter. Every 5 completed experiments, classifies
the last 5 EXPs by SCIENCE/INFRASTRUCTURE/VISUALIZATION. Halts if SCIENCE < 50%.

Pattern: gate-function returning {"pass": bool, ...} — consistent with governance/gates/*.py.
Reference: D-09/D-10/D-11 decisions, GOAL_ALIGNMENT_PROTOCOL.md Layer 3.
"""
import re
from pathlib import Path

DRIFT_TRIGGER: int = 5
SCIENCE_THRESHOLD: float = 50.0

# Classification keywords (from GOAL_ALIGNMENT_PROTOCOL.md taxonomy)
_SCIENCE_KEYWORDS = {"SCIENCE", "CONFIRMATORY", "EXPLORATORY", "REPLICATION"}
_INFRA_KEYWORDS = {"INFRASTRUCTURE", "TASK-"}
_VIZ_KEYWORDS = {"VISUALIZATION"}


def check_drift(project_root: str) -> dict:
    """
    Increment drift counter. If counter reaches DRIFT_TRIGGER, run drift analysis.
    Re-reads MISSION_ANCHOR as part of check (D-11).

    Args:
        project_root: Path to the project root directory (contains .agent/ subdirectory).

    Returns:
        {"pass": True, "triggered": False, "counter": int}
            — counter has not yet reached DRIFT_TRIGGER

        {"pass": True, "triggered": True, "science_pct": float, "breakdown": dict}
            — triggered and SCIENCE% >= 50% (no drift)

        {"pass": False, "triggered": True, "error": str, "science_pct": float,
         "breakdown": dict, "mission_anchor": str}
            — triggered and SCIENCE% < 50% (drift halt)
    """
    root = Path(project_root)
    agent_dir = root / ".agent"
    agent_dir.mkdir(parents=True, exist_ok=True)

    counter_path = agent_dir / "drift_counter.txt"
    current = int(counter_path.read_text().strip()) if counter_path.exists() else 0
    current += 1

    if current < DRIFT_TRIGGER:
        counter_path.write_text(str(current))
        return {"pass": True, "triggered": False, "counter": current}

    # Triggered — reset counter, run analysis
    counter_path.write_text("0")

    # Re-read MISSION_ANCHOR (D-11)
    anchor_path = agent_dir / "MISSION_ANCHOR.md"
    anchor_text = anchor_path.read_text(encoding="utf-8") if anchor_path.exists() else ""

    breakdown = _classify_last_5_exps(project_root)
    total = sum(breakdown.values())
    science_pct = (breakdown.get("SCIENCE", 0) / max(total, 1)) * 100

    if science_pct < SCIENCE_THRESHOLD:
        return {
            "pass": False,
            "triggered": True,
            "error": (
                f"DRIFT_WARNING: SCIENCE classification at {science_pct:.0f}% "
                f"(below 50% threshold). Breakdown: {breakdown}. "
                f"Re-read MISSION_ANCHOR and propose course correction."
            ),
            "science_pct": science_pct,
            "breakdown": breakdown,
            "mission_anchor": anchor_text[:200],
        }

    return {
        "pass": True,
        "triggered": True,
        "science_pct": science_pct,
        "breakdown": breakdown,
    }


def _classify_last_5_exps(project_root: str) -> dict:
    """
    Read LAB_NOTEBOOK.md (last 200 lines). Extract up to 5 EXP header entries and classify.

    EXP headers are expected in the form: ## EXP-### — KEYWORD — description
    Classification rules (in priority order):
      1. Contains VISUALIZATION keyword → VISUALIZATION
      2. Contains INFRASTRUCTURE keyword → INFRASTRUCTURE
      3. Contains any SCIENCE keyword (SCIENCE, CONFIRMATORY, EXPLORATORY, REPLICATION) → SCIENCE
      4. Default (unknown) → INFRASTRUCTURE (conservative — undeclared work not credited as science)

    Returns:
        {"SCIENCE": int, "INFRASTRUCTURE": int, "VISUALIZATION": int}
        If LAB_NOTEBOOK.md does not exist, returns all zeros.
    """
    nb_path = Path(project_root) / "LAB_NOTEBOOK.md"
    if not nb_path.exists():
        return {"SCIENCE": 0, "INFRASTRUCTURE": 0, "VISUALIZATION": 0}

    lines = nb_path.read_text(encoding="utf-8").splitlines()
    recent = lines[-200:]  # last 200 lines only

    breakdown = {"SCIENCE": 0, "INFRASTRUCTURE": 0, "VISUALIZATION": 0}
    exp_count = 0

    for line in reversed(recent):
        if re.match(r"^##\s+EXP-\d+", line):
            classification = _classify_exp_line(line)
            breakdown[classification] += 1
            exp_count += 1
            if exp_count >= 5:
                break

    return breakdown


def _classify_exp_line(line: str) -> str:
    """
    Classify a single LAB_NOTEBOOK EXP header line by scanning for keywords.

    Priority: VISUALIZATION > INFRASTRUCTURE > SCIENCE > default(INFRASTRUCTURE).
    """
    upper = line.upper()
    for kw in _VIZ_KEYWORDS:
        if kw in upper:
            return "VISUALIZATION"
    for kw in _INFRA_KEYWORDS:
        if kw in upper:
            return "INFRASTRUCTURE"
    for kw in _SCIENCE_KEYWORDS:
        if kw in upper:
            return "SCIENCE"
    # Default: conservative assumption — unknown = INFRASTRUCTURE
    return "INFRASTRUCTURE"
