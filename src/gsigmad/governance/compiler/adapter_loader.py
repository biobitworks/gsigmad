"""Parse adapters/*.md files into a project_registry list for scan_all_projects().

This module provides a single public function, ``load_project_registry()``, which
globs all ``*.md`` files in the adapters directory and extracts the four fields
required by ``drift_scanner.scan_all_projects()``:

    - name            (str): project identifier, from "# Adapter: <Name>" heading
    - canon_path      (str): absolute path to the project's CANON.md
    - has_canon       (bool): True if the adapter declares has_canon: true
    - namespace_prefix (str): EXP namespace prefix value (empty string if absent)

Design decisions (D-08 from CONTEXT.md):
    - Uses pathlib.Path for all path operations.
    - Regex patterns match the exact markdown syntax used in adapters/*.md.
    - Results are sorted by name for deterministic ordering.
    - ValueError is raised (not silently skipped) for missing required fields so
      operator-facing errors are actionable during adapter authoring.
"""

from __future__ import annotations

import re
from pathlib import Path


# ---------------------------------------------------------------------------
# Regex patterns for field extraction
# (compiled once at module load for performance across 12 adapters)
# ---------------------------------------------------------------------------

_RE_NAME = re.compile(r"^#\s+Adapter:\s+(.+)$", re.MULTILINE)
# Adapters use '**Path:** /path/' where the colon is inside the bold markers (**Path:**)
_RE_PATH = re.compile(r"^\*\*Path:\*\*\s+(.+)$", re.MULTILINE)
_RE_HAS_CANON = re.compile(r"^has_canon:\s*(true|false)", re.MULTILINE | re.IGNORECASE)
# EXP namespace prefix line: '**EXP namespace prefix:** `value:`'
_RE_NAMESPACE = re.compile(
    r"^\*\*EXP namespace prefix:\*\*\s+\x60(.+?)\x60",  # \x60 = backtick
    re.MULTILINE,
)


def _parse_adapter(adapter_file: Path) -> dict:
    """Parse a single adapter *.md file into a project entry dict.

    Args:
        adapter_file: Path to the adapter markdown file.

    Returns:
        Dict with keys: name, canon_path, has_canon, namespace_prefix.

    Raises:
        ValueError: If **Path:** or has_canon fields are missing.
    """
    text = adapter_file.read_text(encoding="utf-8")

    # --- name ---
    name_match = _RE_NAME.search(text)
    if name_match:
        raw_name = name_match.group(1).strip()
        name = raw_name.lower().replace(" ", "-")
    else:
        # Fall back to filename stem if heading is absent
        name = adapter_file.stem

    # --- canon_path (required) ---
    path_match = _RE_PATH.search(text)
    if not path_match:
        raise ValueError(
            f"{adapter_file.name}: missing **Path:** field — "
            "every adapter must declare '**Path:** /absolute/path/'"
        )
    project_path = path_match.group(1).strip().rstrip("/")
    canon_path = f"{project_path}/CANON.md"

    # --- has_canon (required) ---
    canon_match = _RE_HAS_CANON.search(text)
    if not canon_match:
        raise ValueError(
            f"{adapter_file.name}: missing has_canon field — "
            "every adapter must declare 'has_canon: true' or 'has_canon: false'"
        )
    has_canon = canon_match.group(1).lower() == "true"

    # --- namespace_prefix (optional — empty string if absent) ---
    ns_match = _RE_NAMESPACE.search(text)
    namespace_prefix = ns_match.group(1).strip() if ns_match else ""

    return {
        "name": name,
        "canon_path": canon_path,
        "has_canon": has_canon,
        "namespace_prefix": namespace_prefix,
    }


def load_project_registry(gsd_root: str, adapters_dir: str = "adapters") -> list:
    """Parse all adapters/*.md files and return a project_registry list.

    Produces the ``project_registry`` format expected by
    ``governance.compiler.drift_scanner.scan_all_projects()``.

    Each entry dict contains:

    - ``name`` (str): project identifier from "# Adapter: <Name>" heading,
      lowercased with spaces replaced by hyphens.
    - ``canon_path`` (str): absolute path to the project's CANON.md,
      derived as ``<**Path:**> + "/CANON.md"``.
    - ``has_canon`` (bool): True if "has_canon: true" is present
      (case-insensitive), False if "has_canon: false".
    - ``namespace_prefix`` (str): value inside backticks on the
      "**EXP namespace prefix:**" line; empty string if absent.

    Args:
        gsd_root: Path to the gettingsciencedone repo root.
        adapters_dir: Subdirectory containing adapter ``*.md`` files.
            Defaults to ``"adapters"``.

    Returns:
        Sorted list of project entry dicts (sorted alphabetically by name).

    Raises:
        ValueError: If any adapter file is missing **Path:** or has_canon fields.
    """
    adapters_path = Path(gsd_root) / adapters_dir
    adapter_files = sorted(adapters_path.glob("*.md"))

    registry = [_parse_adapter(f) for f in adapter_files]

    # Sort by name for deterministic ordering (D-08)
    registry.sort(key=lambda e: e["name"])
    return registry
