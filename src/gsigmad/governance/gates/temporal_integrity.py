"""
Temporal integrity gate — GOV-04.

Prevents LLM-assisted HARKing by verifying that a CONFIRMATORY experiment's
pre-registration commit timestamp predates the data file's mtime.

Reference: CANON-CORE Invariant 5, EXPERIMENT_STANDARDS.md §2
"""
import subprocess
import os
from datetime import datetime, timezone
from typing import Optional

# -- TRAITS pillar mapping (REP-02) --

TRAITS_PILLARS: dict[str, list[str]] = {
    "temporal_integrity": ["Traceable"],
}


def check_temporal_integrity(prereg_file: str, data_file: str) -> dict:
    """
    Verify that the pre-registration commit predates the data file mtime.

    Args:
        prereg_file: Path to the pre-registration file (must be git-tracked).
        data_file: Path to the data file being analyzed.

    Returns:
        {"pass": bool, "error": Optional[str], "details": dict}
        On failure, error contains "HARKING_PREVENTION_ERROR" with explicit instructions.
    """
    # Edge case: data file does not exist yet (pre-registering before data collection)
    if not os.path.exists(data_file):
        return {
            "pass": True,
            "error": None,
            "details": {
                "prereg_file": prereg_file,
                "data_file": f"{data_file} (not yet created)",
                "note": "Pre-registration before data collection — temporal gate passes by definition."
            }
        }

    # Get pre-registration commit timestamp from git
    try:
        result = subprocess.run(
            ["git", "log", "--format=%aI", "-1", "--", prereg_file],
            capture_output=True,
            text=True,
            check=True,
            timeout=30
        )
        commit_ts_str = result.stdout.strip()
    except subprocess.TimeoutExpired:
        return {
            "pass": False,
            "error": (
                "HARKING_PREVENTION_ERROR: git log timed out. "
                "Cannot verify pre-registration commit timestamp. "
                "Ensure the repository is accessible and try again."
            ),
            "details": {"prereg_file": prereg_file, "commit_ts": None}
        }
    except subprocess.CalledProcessError as e:
        return {
            "pass": False,
            "error": (
                f"HARKING_PREVENTION_ERROR: git log failed for {prereg_file}. "
                f"Error: {e.stderr.strip()}. "
                "Ensure the file is in a git repository."
            ),
            "details": {"prereg_file": prereg_file, "commit_ts": None}
        }

    # No commit history: treat as failing (uncommitted pre-registration)
    if not commit_ts_str:
        return {
            "pass": False,
            "error": (
                f"HARKING_PREVENTION_ERROR: Pre-registration file '{prereg_file}' has no git "
                "commit history. Commit the pre-registration document BEFORE loading data. "
                "This ensures the hypothesis was locked before the data was observed."
            ),
            "details": {"prereg_file": prereg_file, "commit_ts": None}
        }

    # Parse timestamps
    try:
        commit_ts = datetime.fromisoformat(commit_ts_str)
    except ValueError:
        return {
            "pass": False,
            "error": (
                f"HARKING_PREVENTION_ERROR: Could not parse commit timestamp '{commit_ts_str}'. "
                "This is a git configuration issue — check git log output format."
            ),
            "details": {"prereg_file": prereg_file, "commit_ts": commit_ts_str}
        }

    data_mtime = datetime.fromtimestamp(os.stat(data_file).st_mtime, tz=timezone.utc)

    # Make commit_ts timezone-aware if it isn't already
    if commit_ts.tzinfo is None:
        commit_ts = commit_ts.replace(tzinfo=timezone.utc)

    # Temporal integrity check: commit must PREDATE data file mtime
    if commit_ts >= data_mtime:
        delta = (commit_ts - data_mtime).total_seconds()
        return {
            "pass": False,
            "error": (
                f"HARKING_PREVENTION_ERROR: Pre-registration commit ({commit_ts.isoformat()}) "
                f"postdates or equals data file mtime ({data_mtime.isoformat()}) "
                f"by {abs(delta):.1f} seconds. "
                f"This experiment cannot be classified CONFIRMATORY. "
                f"Options: "
                f"(1) Reclassify as EXPLORATORY and spawn a new CONFIRMATORY EXP with independent data. "
                f"(2) Re-register the hypothesis on a new independent dataset and re-commit before loading data. "
                f"Reference: EXPERIMENT_STANDARDS.md §2, CANON-CORE Invariant 5."
            ),
            "details": {
                "prereg_file": prereg_file,
                "commit_ts": commit_ts.isoformat(),
                "data_mtime": data_mtime.isoformat(),
                "delta_seconds": (commit_ts - data_mtime).total_seconds()
            }
        }

    # Pass: pre-registration commit predates data file
    delta = (data_mtime - commit_ts).total_seconds()
    return {
        "pass": True,
        "error": None,
        "details": {
            "prereg_file": prereg_file,
            "commit_ts": commit_ts.isoformat(),
            "data_mtime": data_mtime.isoformat(),
            "delta_seconds": delta
        }
    }
