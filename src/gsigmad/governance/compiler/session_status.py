"""
Session-start EXP status display — EXP-02.

Primary: ArangoDB query via python-arango.
Fallback: local `.gsigmad/experiments/*.yaml` scan, with legacy markdown support.

Reference: D-06/D-07/D-08 decisions, Overwatch arangodb_collections.md §6.
"""
import os
import re
import warnings
from pathlib import Path

import yaml

from gsigmad.connectors import get_connector

# python-arango is optional — fallback gracefully
try:
    from arango import ArangoClient
    ARANGO_AVAILABLE = True
except ImportError:
    ARANGO_AVAILABLE = False
    ArangoClient = None

_AQL_EXP_STATUS = """
FOR e IN experiments
    FILTER e.status IN ["planned", "in_progress", "completed", "failed"]
    SORT e.status ASC, e.exp_id DESC
    LIMIT 50
    RETURN {
        exp_id: e.exp_id,
        classification: e.classification,
        status: e.status,
        project: e.project,
        last_run_id: e.run_ids[-1],
        scaffold_state: e.scaffold_state,
        scaffold_missing: e.scaffold_missing,
        promotion_authority: e.promotion_authority
    }
"""


def get_exp_status_summary(
    project_root: str,
    arango_host: str = "localhost:8531",
    arango_db: str = "overwatch",
) -> dict:
    """
    Fetch EXP status summary. Primary: ArangoDB. Fallback: local file scan.

    Args:
        project_root: Path to the project root directory.
        arango_host: ArangoDB host:port (default: localhost:8531).
        arango_db: ArangoDB database name (default: overwatch).

    Returns:
        {"pass": True, "exps": list[dict], "source": "kg"|"local_fallback", "warning": None|str}
        {"pass": False, "error": str}
    """
    # Primary: ArangoDB
    if ARANGO_AVAILABLE:
        try:
            client = ArangoClient(hosts=f"http://{arango_host}")
            db = client.db(arango_db, verify=False)
            cursor = db.aql.execute(_AQL_EXP_STATUS, count=True)
            exps = [_normalize_exp(doc) for doc in cursor]
            return {"pass": True, "exps": exps, "source": "kg", "warning": None}
        except Exception:
            pass  # fall through to local scan

    # Fallback: local file scan
    warning = "KG_UNAVAILABLE: using local file scan fallback"
    warnings.warn(warning, RuntimeWarning, stacklevel=2)
    exps = _local_exp_scan(project_root)
    return {"pass": True, "exps": exps, "source": "local_fallback", "warning": warning}


def _normalize_exp(doc: dict) -> dict:
    """Ensure all required fields are present (fill placeholder for missing)."""
    return {
        "exp_id": doc.get("exp_id", "UNKNOWN"),
        "classification": doc.get("classification", "UNKNOWN"),
        "status": doc.get("status", "UNKNOWN"),
        "project": doc.get("project", "UNKNOWN"),
        "last_run_id": doc.get("last_run_id") or "\u2014",
        "scaffold_state": doc.get("scaffold_state"),
        "scaffold_missing": doc.get("scaffold_missing") or [],
        "promotion_authority": doc.get("promotion_authority"),
    }


def _local_exp_scan(project_root: str) -> list:
    """Scan local experiment files, preferring modern gsigmad YAML records."""
    project_path = Path(project_root)
    yaml_dir = project_path / ".gsigmad" / "experiments"
    if yaml_dir.exists():
        exps = _scan_yaml_experiments(project_path)
        if exps:
            return exps[:50]

    legacy_dir = project_path / "experiments"
    if not legacy_dir.exists():
        return []

    exps = []
    for md_file in sorted(legacy_dir.glob("EXP-*.md")):
        try:
            content = md_file.read_text(encoding="utf-8")
        except OSError:
            continue

        exp_id = md_file.stem  # e.g., EXP-001
        status_match = re.search(r"Status:\s*(\S+)", content, re.IGNORECASE)
        class_match = re.search(r"Classification:\s*(\S+)", content, re.IGNORECASE)
        proj_match = re.search(r"Project:\s*(.+)", content, re.IGNORECASE)

        exps.append({
            "exp_id": exp_id,
            "classification": class_match.group(1) if class_match else "UNKNOWN",
            "status": status_match.group(1) if status_match else "unknown",
            "project": proj_match.group(1).strip() if proj_match else "UNKNOWN",
            "last_run_id": "\u2014",
        })

    return exps[:50]


def _scan_yaml_experiments(project_root: Path) -> list[dict]:
    """Read `.gsigmad/experiments/*.yaml` records through the connector layer."""
    exps: list[dict] = []
    connector = get_connector(project_root)
    for record in connector.list_experiments():
        if not isinstance(record, dict):
            continue

        exps.append({
            "exp_id": record.get("exp_id", "UNKNOWN"),
            "classification": str(record.get("classification", "UNKNOWN")).upper(),
            "status": record.get("status", "planned"),
            "project": record.get("project", project_root.name),
            "last_run_id": record.get("last_run_id") or "\u2014",
            "scaffold_state": record.get("scaffold_state"),
            "scaffold_missing": record.get("scaffold_missing") or [],
            "promotion_authority": record.get("promotion_authority"),
        })

    return exps


def render_exp_table(exps: list) -> str:
    """
    Render EXP list as a markdown table.

    Returns markdown string with header row:
    | EXP-### | Classification | Status | Project | Last Run |
    """
    header = "| EXP-### | Classification | Status | Project | Last Run |"
    separator = "|---------|----------------|--------|---------|----------|"

    if not exps:
        return (
            f"{header}\n{separator}\n"
            "| (no experiments found) | \u2014 | \u2014 | \u2014 | \u2014 |"
        )

    rows = []
    for e in exps:
        rows.append(
            f"| {e['exp_id']} | {e['classification']} | {e['status']} "
            f"| {e['project']} | {e['last_run_id']} |"
        )

    return "\n".join([header, separator] + rows)
