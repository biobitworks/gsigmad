"""
FAIR compliance check -- governance/fair/fair_check.py

Evaluates experiment outputs against all 4 FAIR dimensions:
  - Findable: persistent identifiers (DOI/PMID), searchable metadata
  - Accessible: output files retrievable, license declared
  - Interoperable: community formats, linked vocabulary, PROV-JSON provenance
  - Reusable: license, methodology, variable definitions, units

Decision refs: D-01 through D-15 (09-CONTEXT.md)
Requirements: FAIR-01, FAIR-02, FAIR-03, FAIR-04
"""
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

from gsigmad.governance.gates.audit_claims import DOI_PATTERN, PMID_PATTERN


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

PROV_JSON_REQUIRED_KEYS = {"entity", "activity", "wasGeneratedBy"}
COMMUNITY_FORMATS = {".json", ".csv", ".prov.json"}
FAIR_CHECK_FAILED = "FAIR_CHECK_FAILED"
METADATA_FIELDS = ("title", "description", "keywords", "creator")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _load_exp_record(exp_id: str, gsd_root: str) -> dict:
    """Find and load the EXP record from current YAML storage or legacy JSON."""
    root = Path(gsd_root)
    num_str = exp_id.replace("EXP-", "")
    yaml_path = root / ".gsigmad" / "experiments" / f"{exp_id}.yaml"
    if yaml_path.exists():
        try:
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            return data if isinstance(data, dict) else {}
        except (yaml.YAMLError, UnicodeDecodeError):
            return {}

    pattern = f"EXP_{num_str}*.json"
    exp_dir = root / "experiments"
    if exp_dir.exists():
        matches = sorted(exp_dir.glob(pattern))
        if matches:
            try:
                return json.loads(matches[0].read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return {}

    return {}


def _discover_output_files(exp_record: dict, gsd_root: str):
    """Discover output files for an experiment.

    If exp_record has output_files list, resolve those paths relative to gsd_root.
    Also scans results/ for files matching the experiment number to catch
    files present on disk but not listed in output_files (e.g. .prov.json).

    Returns:
        (existing: list[Path], missing: list[Path])
    """
    root = Path(gsd_root)
    existing = []
    missing = []
    seen = set()

    output_files = exp_record.get("output_files", [])
    if output_files:
        for rel_path in output_files:
            abs_path = root / rel_path
            if abs_path.exists():
                existing.append(abs_path)
                seen.add(abs_path.resolve())
            else:
                missing.append(abs_path)

    # Also scan results/ for experiment-matching files not already discovered
    exp_id = exp_record.get("exp_id", "")
    num_str = exp_id.replace("EXP-", "")
    results_dir = root / "results"
    if results_dir.exists() and num_str:
        for match in sorted(results_dir.glob(f"exp{num_str}*")):
            if match.resolve() not in seen:
                existing.append(match)
                seen.add(match.resolve())

    return existing, missing


def _validate_prov_json(file_path: Path) -> dict:
    """Validate a .prov.json file against W3C PROV-JSON structure.

    Checks for required top-level keys: entity, activity, wasGeneratedBy.
    """
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return {"pass": False, "detail": f"{file_path.name}: invalid JSON ({e})"}

    if not isinstance(data, dict):
        return {
            "pass": False,
            "detail": f"{file_path.name}: PROV-JSON must be a JSON object, got {type(data).__name__}",
        }

    missing_keys = PROV_JSON_REQUIRED_KEYS - data.keys()
    if missing_keys:
        return {
            "pass": False,
            "detail": f"{file_path.name}: missing PROV-JSON keys: {sorted(missing_keys)}",
        }

    return {
        "pass": True,
        "detail": f"{file_path.name}: valid PROV-JSON (entity, activity, wasGeneratedBy keys present)",
    }


def _validate_csv_has_headers(file_path: Path) -> dict:
    """Check that a CSV file has a header row with string column names."""
    try:
        with file_path.open(encoding="utf-8") as f:
            reader = csv.reader(f)
            first_row = next(reader, None)
    except Exception as e:
        return {"pass": False, "detail": f"{file_path.name}: cannot read as CSV ({e})"}

    if first_row is None:
        return {"pass": False, "detail": f"{file_path.name}: empty CSV file"}

    has_string_header = any(
        cell.strip()
        and not cell.strip().replace(".", "", 1).replace("-", "", 1).isdigit()
        for cell in first_row
    )

    if not has_string_header:
        return {
            "pass": False,
            "detail": (
                f"{file_path.name}: CSV first row appears to be data, not headers. "
                "Add a header row with column names."
            ),
        }

    return {
        "pass": True,
        "detail": f"{file_path.name}: CSV with headers ({len(first_row)} columns: {', '.join(first_row[:5])})",
    }


def _check_persistent_id(exp_record: dict, gsd_root: str) -> dict:
    """Check for DOI or PMID in the EXP record or .agent/identifiers.json.

    Returns sub-check dict: {"id": "F-ID", "pass": bool, "detail": str}
    """
    exp_id = exp_record.get("exp_id", "unknown")

    # Check exp_record["identifiers"] for DOI or PMID
    identifiers = exp_record.get("identifiers", {})
    if isinstance(identifiers, dict):
        for key, value in identifiers.items():
            val_str = str(value)
            if DOI_PATTERN.search(val_str):
                return {
                    "id": "F-ID",
                    "pass": True,
                    "detail": f"Persistent identifier found: {val_str}",
                }
            if PMID_PATTERN.search(val_str):
                return {
                    "id": "F-ID",
                    "pass": True,
                    "detail": f"Persistent identifier found: PMID {val_str}",
                }

    # Fallback: check .agent/identifiers.json
    root = Path(gsd_root)
    agent_ids_path = root / ".agent" / "identifiers.json"
    if agent_ids_path.exists():
        try:
            agent_ids = json.loads(agent_ids_path.read_text(encoding="utf-8"))
            if exp_id in agent_ids:
                entry = agent_ids[exp_id]
                if isinstance(entry, dict):
                    for key, value in entry.items():
                        val_str = str(value)
                        if DOI_PATTERN.search(val_str):
                            return {
                                "id": "F-ID",
                                "pass": True,
                                "detail": f"Persistent identifier found in identifiers.json: {val_str}",
                            }
                        if PMID_PATTERN.search(val_str):
                            return {
                                "id": "F-ID",
                                "pass": True,
                                "detail": f"Persistent identifier found in identifiers.json: PMID {val_str}",
                            }
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

    return {
        "id": "F-ID",
        "pass": False,
        "detail": (
            f"No persistent identifier (DOI/PMID) found in {exp_id} "
            "identifiers field or .agent/identifiers.json"
        ),
    }


def _check_license(exp_record: dict, gsd_root: str) -> tuple:
    """Check for license in EXP record or LICENSE/LICENSE.md file.

    Returns (found: bool, detail: str).
    """
    # Check record field first
    license_val = exp_record.get("license", "")
    if license_val and str(license_val).strip():
        return True, str(license_val).strip()

    # Check LICENSE files on disk
    root = Path(gsd_root)
    for license_name in ("LICENSE", "LICENSE.md"):
        license_path = root / license_name
        if license_path.exists():
            return True, f"LICENSE file found ({license_name})"

    return False, ""


# ---------------------------------------------------------------------------
# Public API: dimension check functions
# ---------------------------------------------------------------------------

def check_findable(exp_record: dict, gsd_root: str) -> dict:
    """Check Findable dimension: persistent ID + searchable metadata.

    Sub-checks: F-ID, F-META.
    Per D-05, D-06.
    """
    sub_checks = []

    # F-ID: persistent identifier
    f_id = _check_persistent_id(exp_record, gsd_root)
    sub_checks.append(f_id)

    # F-META: metadata completeness
    missing_fields = []
    for field in METADATA_FIELDS:
        val = exp_record.get(field)
        if val is None or val == "" or val == []:
            missing_fields.append(field)

    if missing_fields:
        f_meta = {
            "id": "F-META",
            "pass": False,
            "detail": f"Missing metadata fields: {', '.join(missing_fields)}",
        }
    else:
        f_meta = {
            "id": "F-META",
            "pass": True,
            "detail": "All metadata fields present: title, description, keywords, creator",
        }
    sub_checks.append(f_meta)

    # Dimension passes only if ALL sub-checks pass (D-03)
    dimension_pass = all(sc["pass"] for sc in sub_checks)

    return {
        "dimension": "findable",
        "pass": dimension_pass,
        "sub_checks": sub_checks,
    }


def check_accessible(exp_record: dict, gsd_root: str) -> dict:
    """Check Accessible dimension: output files retrievable, license declared.

    Sub-checks: A-PROTOCOL, A-LICENSE.
    Per D-02.
    """
    sub_checks = []

    # A-PROTOCOL: verify output files exist on disk
    existing, missing = _discover_output_files(exp_record, gsd_root)
    if missing:
        missing_names = [p.name for p in missing]
        a_protocol = {
            "id": "A-PROTOCOL",
            "pass": False,
            "detail": f"Missing output files: {', '.join(missing_names)}",
        }
    elif not existing and not missing:
        a_protocol = {
            "id": "A-PROTOCOL",
            "pass": True,
            "detail": "No output files to check",
        }
    else:
        a_protocol = {
            "id": "A-PROTOCOL",
            "pass": True,
            "detail": f"All {len(existing)} output files retrievable via local filesystem",
        }
    sub_checks.append(a_protocol)

    # A-LICENSE: license declared
    found, detail = _check_license(exp_record, gsd_root)
    if found:
        a_license = {
            "id": "A-LICENSE",
            "pass": True,
            "detail": f"License declared: {detail}",
        }
    else:
        a_license = {
            "id": "A-LICENSE",
            "pass": False,
            "detail": "No license found in EXP record or LICENSE/LICENSE.md file",
        }
    sub_checks.append(a_license)

    dimension_pass = all(sc["pass"] for sc in sub_checks)

    return {
        "dimension": "accessible",
        "pass": dimension_pass,
        "sub_checks": sub_checks,
    }


def check_interoperable(exp_record: dict, gsd_root: str) -> dict:
    """Check Interoperable dimension: community formats, vocabulary, PROV-JSON.

    Sub-checks: I-FORMAT, I-VOCAB, I-PROV.
    Per D-07, D-08.
    """
    sub_checks = []
    existing, _ = _discover_output_files(exp_record, gsd_root)

    # I-FORMAT: check output files against community format whitelist
    non_conforming = []
    for fpath in existing:
        # Handle .prov.json compound extension first
        if fpath.name.endswith(".prov.json"):
            # .prov.json is in the whitelist -- also validate PROV structure later
            continue
        ext = fpath.suffix.lower()
        if ext not in COMMUNITY_FORMATS:
            non_conforming.append(fpath.name)
        elif ext == ".csv":
            # Also validate CSV has headers
            csv_result = _validate_csv_has_headers(fpath)
            if not csv_result["pass"]:
                non_conforming.append(fpath.name)

    if non_conforming:
        names = ", ".join(non_conforming)
        i_format = {
            "id": "I-FORMAT",
            "pass": False,
            "detail": (
                f"{names}: not a community standard format. "
                "Convert to CSV with headers or JSON."
            ),
        }
    else:
        i_format = {
            "id": "I-FORMAT",
            "pass": True,
            "detail": "All output files use community standard formats",
        }
    sub_checks.append(i_format)

    # I-VOCAB: check for JSON-LD @context or vocabulary field
    vocab_found = False
    has_json_outputs = False

    if exp_record.get("vocabulary"):
        vocab_found = True

    if not vocab_found:
        for fpath in existing:
            ext = fpath.suffix.lower()
            if ext == ".json" and not fpath.name.endswith(".prov.json"):
                has_json_outputs = True
                try:
                    data = json.loads(fpath.read_text(encoding="utf-8"))
                    if isinstance(data, dict) and "@context" in data:
                        vocab_found = True
                        break
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass

    if vocab_found:
        i_vocab = {
            "id": "I-VOCAB",
            "pass": True,
            "detail": "Linked vocabulary references found in output metadata",
        }
    elif not has_json_outputs:
        # No regular JSON output files to check -- vacuously true
        i_vocab = {
            "id": "I-VOCAB",
            "pass": True,
            "detail": "No JSON output files to check for vocabulary references",
        }
    else:
        i_vocab = {
            "id": "I-VOCAB",
            "pass": False,
            "detail": "No linked vocabulary found. Add JSON-LD @context to JSON output files or vocabulary field to EXP record.",
        }
    sub_checks.append(i_vocab)

    # I-PROV: find and validate .prov.json files
    prov_files = [f for f in existing if f.name.endswith(".prov.json")]
    if not prov_files:
        i_prov = {
            "id": "I-PROV",
            "pass": False,
            "detail": "No PROV-JSON provenance file found",
        }
    else:
        # Validate each prov file
        all_valid = True
        prov_details = []
        for pf in prov_files:
            result = _validate_prov_json(pf)
            if not result["pass"]:
                all_valid = False
            prov_details.append(result["detail"])

        i_prov = {
            "id": "I-PROV",
            "pass": all_valid,
            "detail": "; ".join(prov_details),
        }
    sub_checks.append(i_prov)

    dimension_pass = all(sc["pass"] for sc in sub_checks)

    return {
        "dimension": "interoperable",
        "pass": dimension_pass,
        "sub_checks": sub_checks,
    }


def check_reusable(exp_record: dict, gsd_root: str) -> dict:
    """Check Reusable dimension: license, methodology, variable defs, units.

    Sub-checks: R-LICENSE, R-METHOD, R-VARDEF, R-UNITS.
    Per D-09, D-10, D-11.
    """
    sub_checks = []

    # R-LICENSE: license detection (same sources as A-LICENSE)
    found, detail = _check_license(exp_record, gsd_root)
    if found:
        r_license = {
            "id": "R-LICENSE",
            "pass": True,
            "detail": f"License: {detail}",
        }
    else:
        r_license = {
            "id": "R-LICENSE",
            "pass": False,
            "detail": "No license found in EXP record or LICENSE/LICENSE.md file",
        }
    sub_checks.append(r_license)

    # R-METHOD: methodology field
    methodology = exp_record.get("methodology", "")
    if methodology and str(methodology).strip():
        char_count = len(str(methodology).strip())
        r_method = {
            "id": "R-METHOD",
            "pass": True,
            "detail": f"Methodology field present in EXP record ({char_count} chars)",
        }
    else:
        r_method = {
            "id": "R-METHOD",
            "pass": False,
            "detail": "No methodology field in EXP record or methodology is empty",
        }
    sub_checks.append(r_method)

    # R-VARDEF: variable definitions
    variables = exp_record.get("variables")
    if variables is None:
        r_vardef = {
            "id": "R-VARDEF",
            "pass": False,
            "detail": "No variables array in EXP record",
        }
    else:
        missing_def = []
        for var in variables:
            var_name = var.get("name", "unnamed")
            if "definition" not in var or not str(var.get("definition", "")).strip():
                missing_def.append(var_name)
        if missing_def:
            names = ", ".join(missing_def)
            r_vardef = {
                "id": "R-VARDEF",
                "pass": False,
                "detail": f"Variable(s) missing definition: {names}",
            }
        else:
            r_vardef = {
                "id": "R-VARDEF",
                "pass": True,
                "detail": "All variables have definition fields",
            }
    sub_checks.append(r_vardef)

    # R-UNITS: variable units
    if variables is None:
        r_units = {
            "id": "R-UNITS",
            "pass": False,
            "detail": "No variables array in EXP record",
        }
    else:
        missing_unit = []
        for var in variables:
            var_name = var.get("name", "unnamed")
            if "unit" not in var or not str(var.get("unit", "")).strip():
                missing_unit.append(var_name)
        if missing_unit:
            names = ", ".join(missing_unit)
            r_units = {
                "id": "R-UNITS",
                "pass": False,
                "detail": f"Variable(s) missing unit: {names}",
            }
        else:
            r_units = {
                "id": "R-UNITS",
                "pass": True,
                "detail": "All variables have unit fields",
            }
    sub_checks.append(r_units)

    dimension_pass = all(sc["pass"] for sc in sub_checks)

    return {
        "dimension": "reusable",
        "pass": dimension_pass,
        "sub_checks": sub_checks,
    }


# ---------------------------------------------------------------------------
# Public API: orchestrator
# ---------------------------------------------------------------------------

def run_fair_check(exp_id: str, gsd_root: str = None) -> dict:
    """Run full FAIR compliance check on an experiment.

    Per D-12: loads EXP record, calls all 4 dimension checkers, aggregates results,
    writes JSON to experiments/fair/EXP_NNN_fair.json, returns result dict.

    Args:
        exp_id:   Experiment ID (e.g. "EXP-042").
        gsd_root: Path to project root (defaults to ".").

    Returns:
        Structured dict with exp_id, checked_at, dimensions, total_score, pass, summary.
    """
    if gsd_root is None:
        gsd_root = "."

    root = Path(gsd_root)
    exp_record = _load_exp_record(exp_id, gsd_root)

    # Handle missing EXP record
    if not exp_record:
        result = {
            "exp_id": exp_id,
            "checked_at": _utc_now_iso(),
            "dimensions": {},
            "total_score": 0,
            "pass": False,
            "summary": f"{FAIR_CHECK_FAILED}: {exp_id} record not found. Cannot assess FAIR compliance.",
        }
        _write_fair_json(result, exp_id, root)
        return result

    # Ensure exp_id is in record
    if "exp_id" not in exp_record:
        exp_record["exp_id"] = exp_id

    # Run all 4 dimension checks
    findable = check_findable(exp_record, gsd_root)
    accessible = check_accessible(exp_record, gsd_root)
    interoperable = check_interoperable(exp_record, gsd_root)
    reusable = check_reusable(exp_record, gsd_root)

    dimensions = {
        "findable": findable,
        "accessible": accessible,
        "interoperable": interoperable,
        "reusable": reusable,
    }

    # Count passing dimensions (D-01)
    total_score = sum(1 for d in dimensions.values() if d["pass"])

    # Build summary
    summary = _build_summary(dimensions, total_score)

    result = {
        "exp_id": exp_id,
        "checked_at": _utc_now_iso(),
        "dimensions": dimensions,
        "total_score": total_score,
        "pass": total_score == 4,
        "summary": summary,
    }

    _write_fair_json(result, exp_id, root)
    return result


# ---------------------------------------------------------------------------
# Private utilities
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    """Return current UTC time as ISO 8601 string with Z suffix."""
    ts = datetime.now(timezone.utc).isoformat()
    return ts.replace("+00:00", "Z")


def _write_fair_json(result: dict, exp_id: str, root: Path) -> None:
    """Write FAIR result JSON to native and legacy coexistence locations."""
    payload = json.dumps(result, indent=2)

    native_dir = root / ".gsigmad" / "fair"
    native_dir.mkdir(parents=True, exist_ok=True)
    native_path = native_dir / f"{exp_id}_fair.json"
    native_path.write_text(payload, encoding="utf-8")

    legacy_dir = root / "experiments" / "fair"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    legacy_exp_id = exp_id.replace("-", "_")
    legacy_path = legacy_dir / f"{legacy_exp_id}_fair.json"
    legacy_path.write_text(payload, encoding="utf-8")


def _build_summary(dimensions: dict, total_score: int) -> str:
    """Build human-readable summary of FAIR assessment."""
    passing = []
    failing = []

    dim_names = {
        "findable": "Findable",
        "accessible": "Accessible",
        "interoperable": "Interoperable",
        "reusable": "Reusable",
    }

    for key, name in dim_names.items():
        dim = dimensions[key]
        if dim["pass"]:
            passing.append(name)
        else:
            # Collect failing sub-check details
            fail_details = []
            for sc in dim["sub_checks"]:
                if not sc["pass"]:
                    fail_details.append(f"{sc['id']}: {sc['detail']}")
            failing.append(f"{name} ({'; '.join(fail_details)})")

    passing_str = ", ".join(passing) if passing else "none"
    parts = [f"FAIR score: {total_score}/4 ({passing_str})."]

    if failing:
        parts.append(f"Failing: {'; '.join(failing)}.")

    return " ".join(parts)
