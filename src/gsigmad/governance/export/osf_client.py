"""
OSF API v2 client -- governance/export/osf_client.py

Uploads export bundles to the Open Science Framework via the OSF API v2
(JSON:API format) and WaterButler file upload.

Decision refs: D-06 (upload_to_osf signature), D-07 (token resolution),
               D-08 (component creation), D-09 (mocked tests)
Requirements: PUB-03 (OSF upload returning URL)
"""
import json
import os
from pathlib import Path

import requests


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OSF_API_BASE = "https://api.osf.io/v2"


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_osf_token() -> str:
    """Read OSF token from env var or .agent/osf_token file.

    Resolution order (per D-07):
      1. OSF_TOKEN environment variable
      2. .agent/osf_token file in working directory

    Raises:
        ValueError: If no token is found, with setup instructions.
    """
    token = os.environ.get("OSF_TOKEN")
    if token:
        return token.strip()

    token_path = Path(".agent/osf_token")
    if token_path.exists():
        return token_path.read_text(encoding="utf-8").strip()

    raise ValueError(
        "OSF_TOKEN not found. Set the OSF_TOKEN environment variable "
        "or create .agent/osf_token containing your personal access token. "
        "Generate a token at https://osf.io/settings/tokens/"
    )


def _load_osf_config(bundle_path: str) -> dict:
    """Load OSF project configuration and manifest metadata.

    Reads .agent/osf_config.json for project_id, and manifest.json
    from the bundle directory for exp_id.

    Args:
        bundle_path: Path to the export bundle directory.

    Returns:
        Dict with at least 'project_id' and optionally 'exp_id'.
    """
    config = {}

    # Try loading .agent/osf_config.json from project root
    config_path = Path(".agent/osf_config.json")
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

    # Load manifest for exp_id
    manifest_path = Path(bundle_path) / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            config["exp_id"] = manifest.get("exp_id", "unknown")
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

    if "project_id" not in config:
        config["project_id"] = "default"

    return config


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def upload_to_osf(bundle_path: str, osf_token: str = None) -> dict:
    """Upload an export bundle to OSF as a new component.

    Creates an OSF component under a parent project (per D-08), then
    uploads all files from the bundle directory via WaterButler PUT.

    Uses JSON:API Content-Type 'application/vnd.api+json' for the
    component creation POST (Pitfall 1). Follows HATEOAS to discover
    the WaterButler upload link from the component's files relationship
    (Pitfall 2).

    Args:
        bundle_path: Path to the export bundle directory.
        osf_token:   OSF personal access token (optional; falls back
                     to env var / .agent/osf_token per D-07).

    Returns:
        {"pass": True, "osf_url": str} on success.
        {"pass": False, "error": str} on failure.
    """
    try:
        # Resolve token
        token = osf_token or _get_osf_token()

        # Load configuration
        config = _load_osf_config(bundle_path)
        project_id = config["project_id"]
        exp_id = config.get("exp_id", "unknown")

        # --- Step 1: Create component via OSF API v2 (JSON:API) ---
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/vnd.api+json",
        }
        body = {
            "data": {
                "type": "nodes",
                "attributes": {
                    "title": f"Export: {exp_id}",
                    "category": "data",
                }
            }
        }
        resp = requests.post(
            f"{OSF_API_BASE}/nodes/{project_id}/children/",
            json=body,
            headers=headers,
        )

        node_data = resp.json()["data"]
        node_id = node_data["id"]

        # --- Step 2: Extract upload link from files relationship (HATEOAS) ---
        upload_link = (
            node_data["relationships"]["files"]["links"]["related"]["href"]
        )

        # --- Step 3: Upload each file via WaterButler PUT ---
        bundle_dir = Path(bundle_path)
        for fpath in sorted(bundle_dir.iterdir()):
            if fpath.is_file():
                with fpath.open("rb") as f:
                    requests.put(
                        f"{upload_link}?kind=file&name={fpath.name}",
                        data=f.read(),
                        headers={"Authorization": f"Bearer {token}"},
                    )

        return {"pass": True, "osf_url": f"https://osf.io/{node_id}/"}

    except ValueError:
        # Re-raise ValueError for missing token (not an API error)
        raise
    except Exception as e:
        return {"pass": False, "error": str(e)}
