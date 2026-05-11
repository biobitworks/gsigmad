"""Scaffold templates for gsigmad project initialization.

Provides template content for config.yaml, CANON.md, LAB_NOTEBOOK.md,
and experiment (EXP) YAML files.  Also contains replication artifact
validation (REP-01) and RO-Crate type mapping.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


# -- Replication artifact type system (REP-01) --

REPLICATION_ARTIFACT_TYPES = frozenset({
    "notebook", "script", "pipeline", "config", "data", "environment",
})

ROCRATE_TYPE_MAP: dict[str, list[str]] = {
    "script": ["File", "SoftwareSourceCode"],
    "notebook": ["File", "SoftwareSourceCode"],  # + programmingLanguage: Jupyter
    "pipeline": ["File", "SoftwareSourceCode", "ComputationalWorkflow"],
    "config": ["File"],
    "data": ["File", "Dataset"],
    "environment": ["File"],
}


def default_config() -> dict:
    """Return default config.yaml content for a new gsigmad project."""
    return {
        "schema_version": 3,
        "project_name": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "connector_type": "flat_file",
        "governance": {
            "canon_path": "CANON.md",
            "experiment_dir": ".gsigmad/experiments",
            "ledger_dir": ".gsigmad/ledger",
            "coordination_file": ".gsigmad/coordination.json",
            "context_dir": ".gsigmad/context",
        },
        "immutability": {
            "prompt_hash_standard": "RFC8785",
            "hash_algorithm": "sha256",
            "archive_mode": "embedded_ledger",
        },
    }


def canon_template() -> str:
    """Return a CANON.md skeleton for a new gsigmad project."""
    return """# CANON

> **Status**: DRAFT
> **Version**: 0.1.0

## Purpose

Define the invariant rules that govern this project's scientific claims.

## Invariants

### Invariant 1
No fabricated data, claims, or values.

### Invariant 2
All claims must be traceable to an experiment with a pre-registered hypothesis.

### Invariant 3
Statistical results must include effect size and confidence intervals.

## Extensions

<!-- Project-specific invariants go here. Extensions may only add rules, never weaken core invariants. -->
"""


def lab_notebook_template() -> str:
    """Return a LAB_NOTEBOOK.md skeleton for a new gsigmad project."""
    return "# Lab Notebook\n\nAppend-only record of experiment entries.\n"


def exp_template(
    exp_id: str,
    classification: str,
    hypothesis: str = "",
    title: str = "",
    anchor_schema_name: str | None = None,
    anchor_schema_version: int | None = None,
    anchors_file: str | None = None,
) -> dict:
    """Return an experiment record dict for a new EXP YAML file.

    Parameters
    ----------
    exp_id : str
        Experiment identifier (e.g., "EXP-1.1").
    classification : str
        One of EXPLORATORY, CONFIRMATORY, REPLICATION (uppercase).
    hypothesis : str, optional
        Null hypothesis text. Defaults to placeholder.
    title : str, optional
        Experiment title. Defaults to empty string.
    """
    h0 = hypothesis if hypothesis else "TODO: state null hypothesis"

    record: dict = {
        "exp_id": exp_id,
        "record_schema_version": 3,
        "title": title,
        "classification": classification,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "author": "",
        "hypothesis": {
            "h0": h0,
            "h1": "TODO: state alternative hypothesis",
            "test": "TODO: specify statistical test",
            "alpha": 0.05,
            "mesi": None,
        },
        "power_analysis": {
            "tier": "TODO",
            "test_type": "TODO",
            "required_n": None,
            "effect_size_mesi": None,
            "alpha": 0.05,
            "achieved_power": None,
        },
        "gates": _gates_for_classification(classification),
        "claims": [],
        "replication_artifacts": [],
    }

    if classification == "CONFIRMATORY":
        record["fdr_chain"] = {
            "levels": [{"name": "primary", "threshold": 0.05}],
            "method": "none",
            "tool": "TODO",
            "tool_version": "TODO",
        }
        record["null_model"] = {
            "strategy": "TODO",
            "n_permutations": None,
            "baseline_description": "TODO: describe the null baseline",
            "exchangeability_assumption": "TODO: state what is exchangeable under null",
            "novel_space": False,
            "justification": None,
            "validation_evidence": None,
        }
        record["calibration_contract"] = {
            "scored_fields": [],
            "default_calibration": {
                "calibrated": False,
                "method": None,
                "tool": None,
                "tool_version": None,
                "brier_score": None,
                "ece_score": None,
                "procedure_ref": None,
            },
        }

    if anchor_schema_name is not None:
        record["anchor_schema_name"] = anchor_schema_name
    if anchor_schema_version is not None:
        record["anchor_schema_version"] = anchor_schema_version
    if anchors_file is not None:
        record["anchors_file"] = anchors_file

    return record


def script_template(exp_id: str, classification: str, title: str) -> str:
    """Return a minimal analysis script stub for a scaffolded experiment."""
    safe_title = title or "Untitled experiment"
    return f'''"""Analysis scaffold for {exp_id} ({classification})."""

from __future__ import annotations


def main() -> None:
    """Entrypoint for {safe_title}."""
    print("Run analysis for {exp_id}")


if __name__ == "__main__":
    main()
'''


def result_manifest_placeholder(exp_id: str) -> dict:
    """Return the Phase 20 manifest placeholder payload for one experiment."""
    return {
        "schema_version": 1,
        "exp_id": exp_id,
        "status": "placeholder",
        "phase": 20,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "note": "Placeholder only; immutable run manifests arrive in Phase 22.",
    }


def validate_replication_artifacts(
    artifacts: list[dict] | None,
    classification: str,
    project_root: Path | None = None,
) -> dict:
    """Validate replication artifact entries for an EXP record.

    Returns ``{"valid": bool, "errors": [...], "warnings": [...], "skipped": bool}``.

    Rules (per REP-01 decisions D-14 through D-19):
    - ``None`` artifacts (pre-v1.7 record): SKIP, valid=True
    - Each artifact must have ``path`` (str) and ``type`` (in REPLICATION_ARTIFACT_TYPES)
    - ``description`` is required for CONFIRMATORY, optional for EXPLORATORY
    - If ``project_root`` provided, missing file paths are errors for CONFIRMATORY,
      warnings for EXPLORATORY
    """
    if artifacts is None:
        return {"valid": True, "errors": [], "warnings": [], "skipped": True}

    errors: list[str] = []
    warnings: list[str] = []

    for i, art in enumerate(artifacts):
        prefix = f"artifact[{i}]"

        # path is always required
        art_path = art.get("path")
        if not art_path or not isinstance(art_path, str):
            errors.append(f"{prefix}: 'path' is required (non-empty string)")

        # type is always required and must be in enum
        art_type = art.get("type")
        if not art_type or art_type not in REPLICATION_ARTIFACT_TYPES:
            errors.append(
                f"{prefix}: 'type' must be one of {sorted(REPLICATION_ARTIFACT_TYPES)}, "
                f"got {art_type!r}"
            )

        # description required for CONFIRMATORY only (D-16)
        if classification == "CONFIRMATORY" and not art.get("description"):
            errors.append(f"{prefix}: 'description' is required for CONFIRMATORY experiments")

        # path existence check (D-17)
        if project_root is not None and art_path and isinstance(art_path, str):
            full_path = project_root / art_path
            if not full_path.exists():
                msg = f"{prefix}: declared path '{art_path}' does not exist"
                if classification == "CONFIRMATORY":
                    errors.append(msg)
                else:
                    warnings.append(msg)

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "skipped": False,
    }


def _gates_for_classification(classification: str) -> dict:
    """Return the gates block appropriate for the experiment classification.

    EXPLORATORY: data_contract only (minimal).
    CONFIRMATORY: full gates (power_analysis, decision_tree, temporal_integrity,
                  red_team, data_contract).
    REPLICATION: data_contract only.
    """
    if classification == "CONFIRMATORY":
        return {
            "power_analysis": "PENDING",
            "decision_tree": "PENDING",
            "temporal_integrity": "PENDING",
            "red_team": "PENDING",
            "data_contract": "PENDING",
        }
    # EXPLORATORY and REPLICATION get minimal gates
    return {
        "data_contract": "PENDING",
    }
