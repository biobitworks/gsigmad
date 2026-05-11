"""
Zenodo REST API client -- governance/export/zenodo_client.py

Deposits export bundles to Zenodo, maps experiment metadata to Zenodo
deposit fields, and reserves a DOI without auto-publishing.

Decision refs: D-10 (deposit_to_zenodo signature), D-11 (token resolution),
               D-12 (metadata mapping), D-13 (mocked tests)
Requirements: PUB-04 (Zenodo deposit returning reserved DOI)
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ZENODO_API_BASE = "https://zenodo.org/api"


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_zenodo_token() -> str:
    """Read Zenodo token from env var or .agent/zenodo_token file.

    Resolution order (per D-11):
      1. ZENODO_TOKEN environment variable
      2. .agent/zenodo_token file in working directory

    Raises:
        ValueError: If no token is found, with setup instructions.
    """
    token = os.environ.get("ZENODO_TOKEN")
    if token:
        return token.strip()

    token_path = Path(".agent/zenodo_token")
    if token_path.exists():
        return token_path.read_text(encoding="utf-8").strip()

    raise ValueError(
        "ZENODO_TOKEN not found. Set the ZENODO_TOKEN environment variable "
        "or create .agent/zenodo_token containing your personal access token. "
        "Generate a token at https://zenodo.org/account/settings/applications/"
    )


def _load_manifest(bundle_path: str) -> dict:
    """Read manifest.json from the bundle directory.

    Args:
        bundle_path: Path to the export bundle directory.

    Returns:
        Parsed manifest dict, or minimal fallback dict if not found.
    """
    manifest_path = Path(bundle_path) / "manifest.json"
    if manifest_path.exists():
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
    return {"exp_id": "unknown", "artifacts": []}


def _load_exp_record(bundle_path: str) -> dict:
    """Attempt to load the EXP record from the bundle or project.

    Looks for the EXP record JSON in the experiments/ directory
    relative to the bundle's parent structure.

    Returns:
        Parsed EXP record dict, or empty dict if not found.
    """
    manifest = _load_manifest(bundle_path)
    exp_id = manifest.get("exp_id", "")

    if not exp_id:
        return {}

    num_str = exp_id.replace("EXP-", "")
    bundle_dir = Path(bundle_path)

    # Walk up from bundle directory to find experiments/
    for parent in [bundle_dir.parent.parent, bundle_dir.parent, Path(".")]:
        exp_dir = parent / "experiments"
        if exp_dir.exists():
            pattern = f"EXP_{num_str}*.json"
            matches = sorted(exp_dir.glob(pattern))
            if matches:
                try:
                    return json.loads(matches[0].read_text(encoding="utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass

    return {}


def _map_exp_to_zenodo(manifest: dict, exp_record: dict = None) -> dict:
    """Map EXP metadata to Zenodo deposit metadata fields (per D-12).

    Maps experiment record fields to Zenodo's required schema:
    - upload_type: "dataset" (hardcoded)
    - title: from EXP record or manifest exp_id
    - description: from EXP record or default
    - creators: from EXP record creator field, formatted as [{"name": str}]
    - keywords: from EXP record or empty list
    - license: from EXP record or "cc-by-4.0"
    - publication_date: current date YYYY-MM-DD
    - access_right: "open"

    Args:
        manifest: Bundle manifest dict.
        exp_record: Optional EXP record dict for rich metadata.

    Returns:
        Zenodo metadata dict ready for deposit PUT.
    """
    exp_record = exp_record or {}
    exp_id = manifest.get("exp_id", "unknown")

    # Build creators list from EXP record creator field
    creators = []
    creator = exp_record.get("creator", "Unknown Author")
    if isinstance(creator, str):
        creators.append({"name": creator})
    elif isinstance(creator, list):
        creators.extend({"name": c} for c in creator)

    if not creators:
        creators = [{"name": "Unknown Author"}]

    return {
        "upload_type": "dataset",
        "title": exp_record.get("title", f"Export bundle for {exp_id}"),
        "description": exp_record.get(
            "description",
            f"Publication export for experiment {exp_id}",
        ),
        "creators": creators,
        "keywords": exp_record.get("keywords", []),
        "license": exp_record.get("license", "cc-by-4.0"),
        "publication_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "access_right": "open",
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def deposit_to_zenodo(bundle_path: str, zenodo_token: str = None) -> dict:
    """Deposit an export bundle to Zenodo and reserve a DOI.

    Creates a Zenodo deposit, uploads all bundle files to the deposit's
    bucket URL, maps experiment metadata, and reserves a DOI. Does NOT
    auto-publish (per RESEARCH.md anti-patterns).

    Args:
        bundle_path:   Path to the export bundle directory.
        zenodo_token:  Zenodo personal access token (optional; falls back
                       to env var / .agent/zenodo_token per D-11).

    Returns:
        {"pass": True, "doi": str, "deposit_id": int} on success.
        {"pass": False, "error": str} on failure.
    """
    try:
        # Resolve token
        token = zenodo_token or _get_zenodo_token()

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        # --- Step 1: Create empty deposit ---
        resp = requests.post(
            f"{ZENODO_API_BASE}/deposit/depositions",
            json={},
            headers=headers,
        )

        deposit = resp.json()
        deposit_id = deposit["id"]
        bucket_url = deposit["links"]["bucket"]

        # Read DOI from the create response
        doi = deposit["metadata"]["prereserve_doi"]["doi"]

        # --- Step 2: Upload files to bucket ---
        bundle_dir = Path(bundle_path)
        for fpath in sorted(bundle_dir.iterdir()):
            if fpath.is_file():
                with fpath.open("rb") as f:
                    requests.put(
                        f"{bucket_url}/{fpath.name}",
                        data=f.read(),
                        headers={"Authorization": f"Bearer {token}"},
                    )

        # --- Step 3: Map metadata and update deposit (with prereserve_doi) ---
        manifest = _load_manifest(bundle_path)
        exp_record = _load_exp_record(bundle_path)
        metadata = _map_exp_to_zenodo(manifest, exp_record)
        metadata["prereserve_doi"] = True

        requests.put(
            f"{ZENODO_API_BASE}/deposit/depositions/{deposit_id}",
            json={"metadata": metadata},
            headers=headers,
        )

        # --- Step 4: Return reserved DOI (do NOT publish) ---
        return {"pass": True, "doi": doi, "deposit_id": deposit_id}

    except ValueError:
        # Re-raise ValueError for missing token (not an API error)
        raise
    except Exception as e:
        return {"pass": False, "error": str(e)}
