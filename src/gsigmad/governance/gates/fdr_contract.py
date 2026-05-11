"""
FDR/PEP propagation contract gate -- FDR-01, FDR-02, FDR-03.

Validates that CONFIRMATORY experiments declare their full FDR/PEP propagation
chain before execution.  Enforces:

  - Schema completeness (Pydantic FDRChain model)
  - Method validation against ALLOWED_METHODS
  - Monotonicity: downstream levels cannot claim stricter FDR than upstream
  - Tool-version binding with amendment protocol on drift

Pre-v1.7 backward compatibility: records without fdr_chain get SKIP (pass with
note), not FAIL.

Reference: EXPERIMENT_STANDARDS.md, D-01 through D-07
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List

from pydantic import BaseModel, Field, ValidationError


# -- TRAITS pillar mapping (D-09, D-10) --

TRAITS_PILLARS: dict[str, list[str]] = {
    "fdr_contract": ["Rigorous", "Traceable"],
}

# -- Allowed FDR correction methods --

ALLOWED_METHODS = frozenset({
    "fdr_bh",
    "fdr_by",
    "fdr_tsbh",
    "fdr_tsbky",
    "bonferroni",
    "sidak",
    "holm",
    "holm-sidak",
    "none",
})


# -- Pydantic schema models --

class FDRLevel(BaseModel):
    """A single level in the FDR propagation chain."""
    name: str
    threshold: float = Field(ge=0.0, le=1.0)


class FDRChain(BaseModel):
    """Complete FDR propagation chain declaration."""
    levels: List[FDRLevel] = Field(min_length=1)
    method: str
    tool: str
    tool_version: str


# -- Gate function --

def check_fdr_contract_gate(exp_record: dict) -> dict:
    """Validate the FDR propagation chain in an EXP record.

    Returns {"pass": bool, "error": str|None, "traits": list, ...}.

    Pre-v1.7 backward compatibility: if fdr_chain key is absent or None,
    returns pass=True with a skip note.
    """
    traits = TRAITS_PILLARS["fdr_contract"]

    # -- Backward compat: no fdr_chain means pre-v1.7 record --
    fdr_raw = exp_record.get("fdr_chain")
    if fdr_raw is None:
        return {
            "pass": True,
            "error": None,
            "traits": traits,
            "note": "No fdr_chain in EXP record; skipped (pre-v1.7 backward compat).",
        }

    # -- Schema validation via Pydantic --
    try:
        chain = FDRChain.model_validate(fdr_raw)
    except ValidationError as e:
        return {
            "pass": False,
            "error": f"FDR_CHAIN_SCHEMA_INVALID: {e}",
            "traits": traits,
        }

    # -- Method validation --
    if chain.method not in ALLOWED_METHODS:
        return {
            "pass": False,
            "error": (
                f"FDR_INVALID_METHOD: '{chain.method}' not in "
                f"{sorted(ALLOWED_METHODS)}"
            ),
            "traits": traits,
        }

    # -- Monotonicity check (D-02, D-04) --
    levels = chain.levels
    for i in range(len(levels) - 1):
        upstream = levels[i]
        downstream = levels[i + 1]
        if downstream.threshold < upstream.threshold:
            return {
                "pass": False,
                "error": (
                    f"FDR_MONOTONICITY_VIOLATION: {downstream.name} threshold "
                    f"({downstream.threshold}) is stricter than upstream "
                    f"{upstream.name} threshold ({upstream.threshold}). "
                    f"Downstream levels must use equal or looser thresholds. "
                    f"Fix: set {downstream.name} threshold >= {upstream.threshold} "
                    f"or tighten {upstream.name} threshold to <= {downstream.threshold}"
                ),
                "traits": traits,
            }

    # -- Tool-version binding (FDR-03, D-07) --
    original = exp_record.get("__original_fdr_chain__")
    if original is not None:
        orig_tool = original.get("tool", "")
        orig_ver = original.get("tool_version", "")
        new_tool = chain.tool
        new_ver = chain.tool_version
        if orig_tool != new_tool or orig_ver != new_ver:
            exp_id = exp_record.get("exp_id", "unknown")
            project_root = exp_record.get("__project_root__", "")
            if not _has_tool_version_amendment(exp_id, Path(project_root) if project_root else Path.cwd()):
                return {
                    "pass": False,
                    "error": (
                        f"FDR_TOOL_VERSION_DRIFT: tool changed from '{orig_tool}' "
                        f"to '{new_tool}' (or version from '{orig_ver}' to "
                        f"'{new_ver}') without amendment. Run 'gsigmad amend "
                        f"{exp_id}' with justification for the change. "
                        f"Required by: pre-registration binding (D-07)."
                    ),
                    "traits": traits,
                }

    # -- All checks passed --
    return {
        "pass": True,
        "error": None,
        "traits": traits,
    }


# -- Cross-experiment FDR consistency check (FDR-04) --


def check_fdr_consistency(exp_records: list[dict]) -> dict:
    """Check FDR chain consistency across same-pipeline CONFIRMATORY experiments.

    Groups CONFIRMATORY experiments by (tool, method) tuple and for each group
    compares threshold values per level name.  If any level has multiple
    distinct threshold values across experiments, that is an inconsistency.

    Args:
        exp_records: List of EXP record dicts (as returned by list_experiments).

    Returns:
        {"consistent": bool, "inconsistencies": list[dict], "pipelines_checked": int}
    """
    from collections import defaultdict

    # Filter to CONFIRMATORY with fdr_chain present
    relevant = [
        r for r in exp_records
        if str(r.get("classification", "")).upper() == "CONFIRMATORY"
        and r.get("fdr_chain") is not None
    ]

    # Group by (tool, method)
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in relevant:
        chain = r["fdr_chain"]
        key = (chain.get("tool", ""), chain.get("method", ""))
        groups[key].append(r)

    inconsistencies: list[dict] = []
    pipelines_checked = 0

    for (tool, method), group_exps in groups.items():
        if len(group_exps) < 2:
            continue  # Nothing to compare for single-experiment pipelines
        pipelines_checked += 1

        # Collect threshold values per level name
        level_thresholds: dict[str, dict[float, list[str]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for r in group_exps:
            exp_id = r.get("exp_id", "unknown")
            for level in r["fdr_chain"].get("levels", []):
                name = level.get("name", "")
                threshold = level.get("threshold")
                if threshold is not None:
                    level_thresholds[name][threshold].append(exp_id)

        # Flag inconsistencies
        for level_name, threshold_map in level_thresholds.items():
            if len(threshold_map) > 1:
                inconsistencies.append({
                    "tool": tool,
                    "method": method,
                    "level": level_name,
                    "thresholds": sorted(threshold_map.keys()),
                    "exp_ids": [
                        eid
                        for eids in threshold_map.values()
                        for eid in eids
                    ],
                })

    return {
        "consistent": len(inconsistencies) == 0,
        "inconsistencies": inconsistencies,
        "pipelines_checked": pipelines_checked,
    }


# -- TRAITS coverage matrix (REP-02) --


def traits_coverage_matrix(gate_chain: dict) -> dict:
    """Build a TRAITS pillar coverage matrix from the gate chain.

    For each gate module in all classification chains, reads the TRAITS_PILLARS
    constant and builds a coverage map: {pillar: [gate_names]}.

    Args:
        gate_chain: The GATE_CHAIN dict from commands/run.py.

    Returns:
        {"covered": dict, "uncovered": list, "total_pillars": 6, "covered_count": int}
    """
    import importlib

    all_pillars = {"Traceable", "Rigorous", "Accurate", "Interpretable", "Transparent", "Secure"}
    covered: dict[str, list[str]] = {}
    seen_gates: set[str] = set()

    for _classification, gates in gate_chain.items():
        for gate_name, module_path, _fn_name in gates:
            if gate_name in seen_gates:
                continue
            seen_gates.add(gate_name)

            try:
                mod = importlib.import_module(module_path)
                tp = getattr(mod, "TRAITS_PILLARS", None)
            except (ImportError, AttributeError):
                tp = None

            if tp and isinstance(tp, dict):
                for _gname, pillars in tp.items():
                    for pillar in pillars:
                        if pillar not in covered:
                            covered[pillar] = []
                        if gate_name not in covered[pillar]:
                            covered[pillar].append(gate_name)

    uncovered = sorted(all_pillars - set(covered.keys()))
    return {
        "covered": covered,
        "uncovered": uncovered,
        "total_pillars": 6,
        "covered_count": len(covered),
    }


def _has_tool_version_amendment(exp_id: str, project_root: Path) -> bool:
    """Check if a valid tool-version amendment exists for the given experiment.

    Globs .agent/amendments/{exp_id}-*.json and checks if any amendment's
    changed_fields list contains 'fdr_chain.tool' or 'fdr_chain.tool_version'.
    """
    amendments_dir = project_root / ".agent" / "amendments"
    if not amendments_dir.is_dir():
        return False

    for amendment_file in amendments_dir.glob(f"{exp_id}-*.json"):
        try:
            data = json.loads(amendment_file.read_text(encoding="utf-8"))
            changed = data.get("changed_fields", [])
            if "fdr_chain.tool" in changed or "fdr_chain.tool_version" in changed:
                return True
        except (json.JSONDecodeError, OSError):
            continue

    return False
