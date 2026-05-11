"""
Amendment protocol for registered reports — REG-02.

Allows governed changes to locked pre-registration documents via append-only
amendment records. Amendments do NOT modify the locked file.

Decision refs:
  D-05: Amendments in .agent/amendments/{EXP}-{N}.json, do NOT modify locked file
  D-06: Amendment appended to lab notebook as append-only entry
  D-07: validate_amendment() requires justification >= 20 chars + PI countersignature
"""
import json
from datetime import datetime, timezone
from pathlib import Path

AMENDMENTS_DIR = ".agent/amendments"
REPORTS_FILE = ".agent/registered_reports.json"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_amendment(amendment_dict: dict, gsd_root: str = "") -> dict:
    """
    Validate an amendment dict before writing.

    Checks (in order):
      1. justification >= 20 characters
      2. pi_countersignature is non-empty
      3. changed_fields is non-empty list
      4. changed_fields keys match original_values and new_values keys

    Args:
        amendment_dict: Dict with amendment fields.
        gsd_root:       Project root (reserved for future checks; unused currently).

    Returns:
        {"pass": True}  if all rules pass.
        {"pass": False, "error": str}  on first failing rule.
    """
    justification = amendment_dict.get("justification", "")
    if len(justification) < 20:
        return {
            "pass": False,
            "error": "Amendment justification must be at least 20 characters",
        }

    pi_sig = amendment_dict.get("pi_countersignature")
    if not pi_sig:
        return {
            "pass": False,
            "error": "Amendment requires PI countersignature",
        }

    changed_fields = amendment_dict.get("changed_fields") or []
    if not changed_fields:
        return {
            "pass": False,
            "error": "Amendment must specify changed_fields",
        }

    original_values = amendment_dict.get("original_values", {})
    new_values = amendment_dict.get("new_values", {})
    cf_set = set(changed_fields)
    if cf_set != set(original_values.keys()) or cf_set != set(new_values.keys()):
        return {
            "pass": False,
            "error": "changed_fields keys must match original_values and new_values keys",
        }

    return {"pass": True}


def create_amendment(amendment_dict: dict, gsd_root: str) -> dict:
    """
    Validate and write an amendment record to .agent/amendments/{exp_id}-{N}.json.

    Args:
        amendment_dict: Dict with amendment fields (exp_id, justification,
                        pi_countersignature, changed_fields, original_values,
                        new_values, and optionally created_by).
        gsd_root:       Absolute path to project root.

    Returns:
        {"pass": True, "amendment_file": str, "amendment_n": int}  on success.
        {"pass": False, "error": str}  on validation failure.
    """
    # Validate first
    validation = validate_amendment(amendment_dict, gsd_root=gsd_root)
    if not validation["pass"]:
        return validation

    exp_id = amendment_dict.get("exp_id", "")
    amendments_dir = Path(gsd_root) / AMENDMENTS_DIR
    amendments_dir.mkdir(parents=True, exist_ok=True)

    # Compute amendment counter N via glob count
    existing = list(amendments_dir.glob(f"{exp_id}-*.json"))
    n = len(existing) + 1

    # Retrieve original_sha from lock record if available
    original_sha = _get_original_sha(exp_id, gsd_root)

    record = {
        "exp_id": exp_id,
        "amendment_n": n,
        "original_sha": original_sha,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "created_by": amendment_dict.get("created_by", ""),
        "pi_countersignature": amendment_dict["pi_countersignature"],
        "justification": amendment_dict["justification"],
        "changed_fields": amendment_dict["changed_fields"],
        "original_values": amendment_dict["original_values"],
        "new_values": amendment_dict["new_values"],
    }

    filename = f"{exp_id}-{n}.json"
    file_path = amendments_dir / filename
    file_path.write_text(json.dumps(record, indent=2), encoding="utf-8")

    return {
        "pass": True,
        "amendment_file": str(Path(AMENDMENTS_DIR) / filename),
        "amendment_n": n,
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_original_sha(exp_id: str, gsd_root: str) -> str:
    """Load original commit_sha from lock record, return '' if not found."""
    reports_path = Path(gsd_root) / REPORTS_FILE
    if not reports_path.exists():
        return ""
    try:
        records = json.loads(reports_path.read_text(encoding="utf-8"))
        return records.get(exp_id, {}).get("commit_sha", "")
    except Exception:
        return ""
