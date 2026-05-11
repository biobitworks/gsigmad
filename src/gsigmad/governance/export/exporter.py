"""
Publication export bundle assembly -- governance/export/exporter.py

Assembles experiment artifacts into a submission-ready export directory
with a machine-readable manifest.json containing SHA-256 checksums,
artifact types, and provenance/FAIR metadata.

Decision refs: D-01 through D-05 (10-CONTEXT.md)
Requirements: PUB-01 (manifest with checksums), PUB-02 (all 6 artifact types)
"""
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    """Return current UTC time as ISO 8601 string with Z suffix."""
    ts = datetime.now(timezone.utc).isoformat()
    return ts.replace("+00:00", "Z")


def _compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 checksum of a file, reading in 8192-byte chunks.

    Per Pitfall 5 in RESEARCH.md: compute checksum on the COPIED file
    (caller copies first, then calls this on the copy).

    Returns:
        64-char hex digest string.
    """
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _exp_id_variants(exp_id: str) -> tuple[str, str]:
    """Return hyphenated and underscored experiment id variants."""
    return exp_id, exp_id.replace("-", "_")


def _first_existing_path(*candidates: Path) -> Path:
    """Return the first existing path, or the first candidate if none exist."""
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _load_exp_record(exp_id: str, root: Path) -> dict:
    """Find and load the EXP record from current YAML storage or legacy JSON."""
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


def _collect_artifact(
    src_path: Path,
    bundle_dir: Path,
    artifact_type: str,
    exp_id: str,
    extra: dict = None,
) -> dict:
    """Copy a single artifact into the bundle directory and build its manifest entry.

    If src_path does not exist, returns a manifest entry with status "missing"
    and sha256 None -- does NOT copy (per D-04).

    Per Pitfall 5: copies first, then checksums the copy.

    Args:
        src_path: Source file to copy.
        bundle_dir: Destination bundle directory.
        artifact_type: One of data, script, pre-reg, notebook, provenance, fair.
        exp_id: Experiment ID for manifest entry.
        extra: Optional dict with prov_json_hash and/or fair_score overrides.

    Returns:
        Manifest entry dict.
    """
    extra = extra or {}

    if not src_path.exists():
        return {
            "filename": src_path.name,
            "artifact_type": artifact_type,
            "sha256": None,
            "exp_id": exp_id,
            "prov_json_hash": extra.get("prov_json_hash"),
            "fair_score": extra.get("fair_score"),
            "status": "missing",
        }

    # Copy file to bundle directory
    dest = bundle_dir / src_path.name
    shutil.copy2(src_path, dest)

    # Compute checksum on the copy (Pitfall 5)
    sha = _compute_sha256(dest)

    return {
        "filename": src_path.name,
        "artifact_type": artifact_type,
        "sha256": sha,
        "exp_id": exp_id,
        "prov_json_hash": extra.get("prov_json_hash"),
        "fair_score": extra.get("fair_score"),
        "status": "present",
    }


def _extract_notebook_excerpt(
    exp_id: str, root: Path, bundle_dir: Path
) -> dict:
    """Extract lab notebook lines mentioning the experiment and write an excerpt file.

    Reads LAB_NOTEBOOK.md, extracts all lines containing the exp_id string,
    writes excerpt to bundle_dir/notebook_excerpt.md.

    Returns a manifest entry. If LAB_NOTEBOOK.md does not exist or has no
    mentions, returns a "missing" entry.
    """
    notebook_path = _first_existing_path(
        root / ".gsigmad" / "LAB_NOTEBOOK.md",
        root / "LAB_NOTEBOOK.md",
    )

    if not notebook_path.exists():
        return {
            "filename": "notebook_excerpt.md",
            "artifact_type": "notebook",
            "sha256": None,
            "exp_id": exp_id,
            "prov_json_hash": None,
            "fair_score": None,
            "status": "missing",
        }

    content = notebook_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Extract lines containing the exp_id (case-insensitive via regex)
    pattern = re.compile(re.escape(exp_id), re.IGNORECASE)
    matching_lines = [line for line in lines if pattern.search(line)]

    if not matching_lines:
        return {
            "filename": "notebook_excerpt.md",
            "artifact_type": "notebook",
            "sha256": None,
            "exp_id": exp_id,
            "prov_json_hash": None,
            "fair_score": None,
            "status": "missing",
        }

    # Write excerpt
    excerpt_path = bundle_dir / "notebook_excerpt.md"
    excerpt_content = (
        f"# Lab Notebook Excerpt: {exp_id}\n\n"
        + "\n".join(matching_lines)
        + "\n"
    )
    excerpt_path.write_text(excerpt_content, encoding="utf-8")

    # Checksum on the written file
    sha = _compute_sha256(excerpt_path)

    return {
        "filename": "notebook_excerpt.md",
        "artifact_type": "notebook",
        "sha256": sha,
        "exp_id": exp_id,
        "prov_json_hash": None,
        "fair_score": None,
        "status": "present",
    }


def _resolve_pre_reg_path(exp_id: str, root: Path) -> Path:
    """Resolve native or legacy pre-registration paths for an experiment."""
    hyphenated, underscored = _exp_id_variants(exp_id)
    return _first_existing_path(
        root / ".gsigmad" / "experiments" / f"{hyphenated}.yaml",
        root / "experiments" / "pre-reg" / f"{underscored}_pre_reg.md",
        root / "experiments" / "pre-reg" / f"{hyphenated}_pre_reg.md",
    )


def _resolve_fair_path(exp_id: str, root: Path) -> Path:
    """Resolve native or legacy FAIR assessment paths for an experiment."""
    hyphenated, underscored = _exp_id_variants(exp_id)
    return _first_existing_path(
        root / ".gsigmad" / "fair" / f"{hyphenated}_fair.json",
        root / ".gsigmad" / "fair" / f"{underscored}_fair.json",
        root / "experiments" / "fair" / f"{underscored}_fair.json",
        root / "experiments" / "fair" / f"{hyphenated}_fair.json",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_bundle(
    exp_id: str, gsd_root: str = None, target_dir: str = None
) -> tuple:
    """Assemble an export bundle for an experiment.

    Collects 6 artifact types (per D-03): data files, analysis scripts,
    pre-registration document, lab notebook excerpts, PROV-JSON provenance
    chain, and FAIR assessment JSON. Copies each into a bundle directory,
    computes SHA-256 checksums, and writes manifest.json.

    Per D-05: signature is create_bundle(exp_id, gsd_root=None, target_dir=None).
    Per D-01: default output directory is exports/EXP-###/.
    Per D-04: missing artifacts get status "missing" without halting.

    Args:
        exp_id:     Experiment ID (e.g. "EXP-042").
        gsd_root:   Path to project root (defaults to ".").
        target_dir: Override output directory (defaults to exports/<exp_id>/).

    Returns:
        (bundle_path: str, manifest: dict)
    """
    root = Path(gsd_root or ".")
    num_str = exp_id.replace("EXP-", "")

    # Determine bundle directory (D-01)
    bundle_dir = Path(target_dir) if target_dir else root / "exports" / exp_id
    bundle_dir.mkdir(parents=True, exist_ok=True)

    # Load EXP record
    exp_record = _load_exp_record(exp_id, root)

    artifacts = []

    # --- (a) Data files: glob results/ for files matching exp{NNN}* ---
    results_dir = root / "results"
    if results_dir.exists():
        data_pattern = f"exp{num_str}*"
        for data_file in sorted(results_dir.glob(data_pattern)):
            # Skip .prov.json files (handled separately as provenance)
            if data_file.name.endswith(".prov.json"):
                continue
            entry = _collect_artifact(data_file, bundle_dir, "data", exp_id)
            artifacts.append(entry)

    # If no data files found via glob but EXP record lists output_files,
    # try those explicitly (they may have different naming)
    if not any(a["artifact_type"] == "data" for a in artifacts):
        output_files = exp_record.get("output_files", [])
        for rel_path in output_files:
            src = root / rel_path
            entry = _collect_artifact(src, bundle_dir, "data", exp_id)
            artifacts.append(entry)

    # --- (b) Analysis scripts: from EXP record scripts field ---
    scripts_list = exp_record.get("scripts", [])
    for script_rel in scripts_list:
        src = root / script_rel
        entry = _collect_artifact(src, bundle_dir, "script", exp_id)
        artifacts.append(entry)

    # --- (c) Pre-registration document ---
    pre_reg_path = _resolve_pre_reg_path(exp_id, root)
    entry = _collect_artifact(pre_reg_path, bundle_dir, "pre-reg", exp_id)
    artifacts.append(entry)

    # --- (d) Lab notebook excerpts ---
    notebook_entry = _extract_notebook_excerpt(exp_id, root, bundle_dir)
    artifacts.append(notebook_entry)

    # --- (e) PROV-JSON provenance files ---
    if results_dir.exists():
        prov_pattern = f"exp{num_str}*.prov.json"
        for prov_file in sorted(results_dir.glob(prov_pattern)):
            # Load content to compute a hash for prov_json_hash field
            try:
                prov_content = prov_file.read_text(encoding="utf-8")
                prov_hash = hashlib.sha256(
                    prov_content.encode("utf-8")
                ).hexdigest()
            except (UnicodeDecodeError, OSError):
                prov_hash = None

            entry = _collect_artifact(
                prov_file,
                bundle_dir,
                "provenance",
                exp_id,
                extra={"prov_json_hash": prov_hash},
            )
            artifacts.append(entry)

    # If no provenance files found, add a missing entry
    if not any(a["artifact_type"] == "provenance" for a in artifacts):
        artifacts.append({
            "filename": f"exp{num_str}.prov.json",
            "artifact_type": "provenance",
            "sha256": None,
            "exp_id": exp_id,
            "prov_json_hash": None,
            "fair_score": None,
            "status": "missing",
        })

    # --- (f) FAIR assessment JSON ---
    fair_path = _resolve_fair_path(exp_id, root)
    fair_score = None
    if fair_path.exists():
        try:
            fair_data = json.loads(fair_path.read_text(encoding="utf-8"))
            fair_score = fair_data.get("total_score")
        except (json.JSONDecodeError, UnicodeDecodeError):
            fair_score = None

    fair_entry = _collect_artifact(
        fair_path,
        bundle_dir,
        "fair",
        exp_id,
        extra={"fair_score": fair_score},
    )
    artifacts.append(fair_entry)

    # --- Build and write manifest (D-02) ---
    manifest = {
        "exp_id": exp_id,
        "created_at": _utc_now_iso(),
        "artifacts": artifacts,
    }

    manifest_path = bundle_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return str(bundle_dir), manifest
