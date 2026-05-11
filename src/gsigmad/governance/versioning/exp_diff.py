"""
EXP re-run versioning and structured diff — EXP-03.

When an experiment is re-run, the result carries a version-suffixed EXP ID
(EXP-042.1, EXP-042.2, ...) and a structured diff is committed to the lab
notebook so any consumer can see exactly what changed between runs.

Pattern: gate-function returning {"pass": bool, ...} — consistent with
governance/gates/*.py. All functions use stdlib only — no external dependencies.

Decision refs:
  D-04: Re-run produces version-suffixed EXP: EXP-042.1, EXP-042.2, etc.
  D-05: Structured diff output from governance/versioning/exp_diff.py
  D-06: Diff includes changed_inputs, changed_parameters, changed_governance,
        summary, and markdown_diff.
"""
from gsigmad.governance.versioning.track_ids import next_rerun_version

# ---------------------------------------------------------------------------
# Field category constants (D-06)
# ---------------------------------------------------------------------------

_DIFF_INPUTS = ["data_file", "protein", "sample_set", "n_actual"]
_DIFF_PARAMETERS = ["hypothesis", "power_analysis", "decision_tree"]
_DIFF_GOVERNANCE = ["classification", "gates", "canon_version"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def diff_exp_records(original: dict, rerun: dict) -> dict:
    """
    Compare two EXP records and return a structured diff.

    Args:
        original: The original EXP record dict (e.g., exp_id="EXP-042").
        rerun:    The re-run EXP record dict (e.g., exp_id="EXP-042.1").

    Returns:
        {
            "pass": True,                     # always True — diff is informational
            "original_id": str,               # e.g., "EXP-042"
            "rerun_id":    str,               # e.g., "EXP-042.1"
            "changed_inputs":     list[dict], # [{field, old, new}]
            "changed_parameters": list[dict], # [{field, old, new}]
            "changed_governance": list[dict], # [{field, old, new}]
            "summary": str,                   # "N field(s) changed between ..."
            "markdown_diff": str,             # markdown block for lab notebook
        }

    Raises:
        ValueError: If rerun["exp_id"] does not start with original["exp_id"] + "."
                    — prevents comparing unrelated EXP records.
    """
    orig_id = original["exp_id"]
    rerun_id = rerun["exp_id"]

    # Validate version relationship (Pitfall 5 — mismatched ID guard)
    if not rerun_id.startswith(orig_id + "."):
        raise ValueError(
            f"Rerun exp_id '{rerun_id}' must start with '{orig_id}.' "
            f"— cannot diff unrelated EXP records."
        )

    changed_inputs = _diff_fields(original, rerun, _DIFF_INPUTS)
    changed_parameters = _diff_nested(original, rerun, _DIFF_PARAMETERS)
    changed_governance = _diff_fields(original, rerun, _DIFF_GOVERNANCE)

    all_changes = changed_inputs + changed_parameters + changed_governance
    n = len(all_changes)

    summary = f"{n} field(s) changed between {orig_id} and {rerun_id}"

    markdown_diff = _build_markdown_diff(orig_id, rerun_id, all_changes)

    return {
        "pass": True,
        "original_id": orig_id,
        "rerun_id": rerun_id,
        "changed_inputs": changed_inputs,
        "changed_parameters": changed_parameters,
        "changed_governance": changed_governance,
        "summary": summary,
        "markdown_diff": markdown_diff,
    }


def next_version_id(base_exp_id: str, gsd_root: str) -> str:
    """
    Return the next version-suffixed EXP ID for a base EXP.

    Reads and increments a per-base-EXP counter stored in
    ``<gsd_root>/.agent/exp_versions.json``. Never touches ``next_exp.txt``.

    Args:
        base_exp_id: The base experiment ID, e.g., "EXP-042".
        gsd_root:    Path to the project root (contains or will contain .agent/).

    Returns:
        The next version string, e.g., "EXP-042.1" on first call, "EXP-042.2"
        on the second call, etc.
    """
    return next_rerun_version(base_exp_id, gsd_root)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _diff_fields(a: dict, b: dict, fields: list) -> list:
    """
    Compare top-level fields between two dicts.

    Returns list of {field, old, new} for each field where
    ``a.get(field) != b.get(field)``. Fields absent from both records
    are skipped.

    Args:
        a:      First dict (original).
        b:      Second dict (rerun).
        fields: List of top-level field names to compare.

    Returns:
        List of {"field": str, "old": any, "new": any} dicts.
    """
    changes = []
    for field in fields:
        old_val = a.get(field)
        new_val = b.get(field)
        if old_val is None and new_val is None:
            continue  # absent from both — skip
        if old_val != new_val:
            changes.append({"field": field, "old": old_val, "new": new_val})
    return changes


def _diff_nested(a: dict, b: dict, fields: list) -> list:
    """
    Compare nested dict fields one level deep between two dicts.

    For each field in ``fields``:
    - If both values are dicts, compare their sub-keys with dot notation
      (e.g., "hypothesis.alpha").
    - If either value is not a dict (or absent), fall back to direct comparison
      at the top-level field name.

    Args:
        a:      First dict (original).
        b:      Second dict (rerun).
        fields: List of top-level field names whose values may be dicts.

    Returns:
        List of {"field": str, "old": any, "new": any} dicts, where field uses
        dot notation for nested sub-keys (e.g., "hypothesis.alpha").
    """
    changes = []
    for field in fields:
        old_val = a.get(field)
        new_val = b.get(field)

        if isinstance(old_val, dict) and isinstance(new_val, dict):
            # Compare sub-keys one level deep
            all_subkeys = set(old_val.keys()) | set(new_val.keys())
            for subkey in sorted(all_subkeys):
                old_sub = old_val.get(subkey)
                new_sub = new_val.get(subkey)
                if old_sub != new_sub:
                    changes.append({
                        "field": f"{field}.{subkey}",
                        "old": old_sub,
                        "new": new_sub,
                    })
        else:
            # Non-dict or absent — direct comparison
            if old_val is None and new_val is None:
                continue
            if old_val != new_val:
                changes.append({"field": field, "old": old_val, "new": new_val})

    return changes


def _build_markdown_diff(orig_id: str, rerun_id: str, all_changes: list) -> str:
    """
    Build a markdown-formatted diff block suitable for lab notebook insertion.

    Args:
        orig_id:     Original EXP ID (e.g., "EXP-042").
        rerun_id:    Re-run EXP ID (e.g., "EXP-042.1").
        all_changes: Combined list of {field, old, new} from all three categories.

    Returns:
        A markdown string starting with a ## header and containing a table or
        a '(no changes)' note.
    """
    header = f"## {orig_id} \u2192 {rerun_id} Diff\n"

    if not all_changes:
        return header + "\n_(no changes)_\n"

    lines = [header, ""]
    lines.append("| Field | Old | New |")
    lines.append("|-------|-----|-----|")
    for change in all_changes:
        field = change["field"]
        old = _fmt_value(change["old"])
        new = _fmt_value(change["new"])
        lines.append(f"| {field} | {old} | {new} |")
    lines.append("")
    return "\n".join(lines)


def _fmt_value(val) -> str:
    """Format a value for markdown table display."""
    if val is None:
        return "—"
    return str(val)
