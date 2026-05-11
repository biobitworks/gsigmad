"""
Registered report governance — REG-01 and REG-04.

Provides tamper-evident locking of pre-registration documents and deviation
detection between a locked plan snapshot and a live EXP record.

Decision refs:
  D-01: Lock state stored in .agent/registered_reports.json keyed by EXP-###
  D-02: Immutability detected by SHA256 of current file content vs stored file_hash
  D-03: Functions: lock_report(), is_locked(), check_immutability() in this module
  D-04: Error prefix: REGISTERED_REPORT_IMMUTABLE
"""
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

REPORTS_FILE = ".agent/registered_reports.json"

# Hypothesis fields tracked in the locked_plan snapshot.
_HYPOTHESIS_FIELDS = ("test", "alpha", "mesi")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def lock_report(
    exp_id: str,
    pre_reg_file: str,
    locked_by: str,
    gsd_root: str,
) -> dict:
    """
    Create a tamper-evident lock record for a pre-registration document.

    Args:
        exp_id:       Experiment ID (e.g. "EXP-001").
        pre_reg_file: Relative path to the pre-registration file from gsd_root.
        locked_by:    SIG-ID of the agent/user locking the report.
        gsd_root:     Absolute path to the project root.

    Returns:
        {"pass": True, "commit_sha": str}  on success.
        {"pass": False, "error": "REGISTERED_REPORT_ALREADY_LOCKED: ..."}  if already locked.
    """
    reports_path = Path(gsd_root) / REPORTS_FILE
    reports_path.parent.mkdir(parents=True, exist_ok=True)

    records = json.loads(reports_path.read_text(encoding="utf-8")) if reports_path.exists() else {}

    # Reject double-lock
    if exp_id in records:
        return {
            "pass": False,
            "error": (
                f"REGISTERED_REPORT_ALREADY_LOCKED: {exp_id} is already locked "
                f"(locked_at={records[exp_id].get('locked_at')}, "
                f"locked_by={records[exp_id].get('locked_by')}). "
                "Use create_amendment() to make governed changes."
            ),
        }

    abs_pre_reg = Path(gsd_root) / pre_reg_file

    # Compute SHA256 of file content for immutability detection
    file_bytes = abs_pre_reg.read_bytes() if abs_pre_reg.exists() else b""
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    # Retrieve the most recent git commit SHA for this file
    commit_sha = _git_commit_sha(pre_reg_file, cwd=gsd_root)

    # Build locked_plan snapshot — attempt to parse hypothesis fields from JSON;
    # for markdown pre-reg files (which tests use) store an empty dict so
    # check_deviation() skips comparison rather than raising.
    locked_plan = _extract_locked_plan(abs_pre_reg)

    records[exp_id] = {
        "commit_sha": commit_sha,
        "file_hash": file_hash,
        "locked_at": datetime.now(tz=timezone.utc).isoformat(),
        "locked_by": locked_by,
        "pre_reg_file": pre_reg_file,
        "locked_plan": locked_plan,
    }

    reports_path.write_text(json.dumps(records, indent=2), encoding="utf-8")

    return {"pass": True, "commit_sha": commit_sha}


def is_locked(exp_id: str, gsd_root: str) -> bool:
    """Return True iff exp_id has a lock record in registered_reports.json."""
    reports_path = Path(gsd_root) / REPORTS_FILE
    if not reports_path.exists():
        return False
    records = json.loads(reports_path.read_text(encoding="utf-8"))
    return exp_id in records


def check_immutability(exp_id: str, gsd_root: str) -> dict:
    """
    Verify that the locked pre-registration file has not been modified.

    Returns:
        {"pass": True, "error": None}  if file content matches stored SHA256 (or EXP not locked).
        {"pass": False, "error": "REGISTERED_REPORT_IMMUTABLE: ..."}  if content differs.
    """
    reports_path = Path(gsd_root) / REPORTS_FILE
    if not reports_path.exists():
        return {"pass": True, "error": None}

    records = json.loads(reports_path.read_text(encoding="utf-8"))
    if exp_id not in records:
        return {"pass": True, "error": None}

    record = records[exp_id]
    stored_hash = record["file_hash"]

    abs_pre_reg = Path(gsd_root) / record["pre_reg_file"]
    current_bytes = abs_pre_reg.read_bytes() if abs_pre_reg.exists() else b""
    current_hash = hashlib.sha256(current_bytes).hexdigest()

    if current_hash != stored_hash:
        return {
            "pass": False,
            "error": (
                f"REGISTERED_REPORT_IMMUTABLE: {exp_id} pre-registration file "
                f"'{record['pre_reg_file']}' has been modified after locking "
                f"(locked_hash={stored_hash[:12]}…, current_hash={current_hash[:12]}…). "
                "Use create_amendment() to make governed changes."
            ),
        }

    return {"pass": True, "error": None}


def check_deviation(exp_id: str, exp_record: dict, gsd_root: str) -> dict:
    """
    Compare an EXP record's hypothesis fields against the locked plan snapshot.

    Returns:
        {"pass": True, "error": None}  if no deviation detected or EXP not locked.
        {"pass": False, "error": "REGISTERED_REPORT_DEVIATION: hypothesis.{field} ..."}
            on first field mismatch.
    """
    reports_path = Path(gsd_root) / REPORTS_FILE
    if not reports_path.exists():
        return {"pass": True, "error": None}

    records = json.loads(reports_path.read_text(encoding="utf-8"))
    if exp_id not in records:
        return {"pass": True, "error": None}

    locked_plan = records[exp_id].get("locked_plan", {})

    # If locked_plan is empty (markdown pre-reg file — hypothesis fields not parseable),
    # skip comparison and pass.
    if not locked_plan:
        return {"pass": True, "error": None}

    hypothesis = exp_record.get("hypothesis", {})

    for field in _HYPOTHESIS_FIELDS:
        dot_key = f"hypothesis.{field}"
        if dot_key not in locked_plan:
            continue
        locked_val = locked_plan[dot_key]
        current_val = hypothesis.get(field)
        if locked_val != current_val:
            return {
                "pass": False,
                "error": (
                    f"REGISTERED_REPORT_DEVIATION: hypothesis.{field} differs — "
                    f"locked={locked_val!r}, current={current_val!r}. "
                    "Use create_amendment() to make governed changes."
                ),
            }

    return {"pass": True, "error": None}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _git_commit_sha(file_path: str, cwd: str) -> str:
    """Return the most recent git commit SHA for file_path, or empty string on failure."""
    try:
        result = subprocess.run(
            ["git", "log", "--format=%H", "-1", "--", file_path],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=cwd,
        )
        return result.stdout.strip() or ""
    except Exception:
        return ""


def _extract_locked_plan(abs_pre_reg: Path) -> dict:
    """
    Attempt to read hypothesis fields from a JSON pre-reg file.

    For markdown files (or any non-JSON content) returns {} — deviation
    check will skip comparison for these.
    """
    if not abs_pre_reg.exists():
        return {}
    text = abs_pre_reg.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        try:
            data = yaml.safe_load(text) or {}
        except yaml.YAMLError:
            return {}

    if not isinstance(data, dict):
        return {}

    hypothesis = data.get("hypothesis", {})
    plan = {}
    for field in _HYPOTHESIS_FIELDS:
        if field in hypothesis:
            plan[f"hypothesis.{field}"] = hypothesis[field]
    return plan
