"""Shared governed experiment-creation helpers for register and scaffold."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from gsigmad.connectors import ConnectorProtocol
from gsigmad.governance.anchors import (
    AnchorValidationError,
    load_anchor_document,
    resolve_project_anchor_schema,
)
from gsigmad.governance.closure_chain import record_chain_event
from gsigmad.governance.human_gates import build_promotion_gate
from gsigmad.governance.versioning import allocate_track_id, resolve_coordinate
from gsigmad.hub import build_prompt_artifact
from gsigmad.scaffold.templates import exp_template

PROMOTION_AUTHORITY = "phase20-local-text-classifier-v1"


def _ratified_promotion_authority(value: str | None) -> str | None:
    if value == PROMOTION_AUTHORITY:
        return value
    return None


def _command_action(command_name: str) -> str:
    if command_name == "register":
        return "pre_register_experiment"
    return f"{command_name}_experiment"


def anchor_opt_in_version(connector: ConnectorProtocol) -> int | None:
    """Return the active project anchor schema version, if any."""
    return resolve_project_anchor_schema(connector.load_config())


def anchor_record_fields(
    project_root: Path,
    connector: ConnectorProtocol,
    *,
    anchors_file: str | Path | None,
) -> dict[str, Any]:
    """Validate an anchor file for opted-in projects and return EXP pointer metadata."""
    schema_version = anchor_opt_in_version(connector)
    if anchors_file is None:
        return {}
    if schema_version is None:
        raise AnchorValidationError(
            "Project has not opted into anchor validation. "
            "Set anchor_schema_version in .gsigmad/config.yaml before using --anchors-file."
        )

    document = load_anchor_document(project_root, anchors_file)
    if document.schema_version != schema_version:
        raise AnchorValidationError(
            "Anchor document schema_version does not match project anchor_schema_version"
        )
    return {
        "anchor_schema_name": document.schema_name,
        "anchor_schema_version": document.schema_version,
        "anchors_file": document.relative_path.as_posix(),
    }


def create_experiment_record(
    project_root: Path,
    connector: ConnectorProtocol,
    *,
    classification: str,
    title: str,
    hypothesis: str,
    promotion_authority: str | None = None,
    command_name: str,
    archive_kind: str = "registration_context",
    anchors_file: str | Path | None = None,
    extra_record_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create and persist the shared governed EXP registration record."""
    exp_id = allocate_track_id("EXP", project_root)
    prompt_id = allocate_track_id("PROMPT", project_root)
    task_id = allocate_track_id("TASK", project_root)
    anchor_fields = anchor_record_fields(
        project_root,
        connector,
        anchors_file=anchors_file,
    )

    record = exp_template(
        exp_id=exp_id,
        classification=classification,
        hypothesis=hypothesis,
        title=title,
        anchor_schema_name=anchor_fields.get("anchor_schema_name"),
        anchor_schema_version=anchor_fields.get("anchor_schema_version"),
        anchors_file=anchor_fields.get("anchors_file"),
    )
    record["record_schema_version"] = 3
    record["prompt_id"] = prompt_id
    record["task_id"] = task_id
    record["coordinate_version"] = resolve_coordinate(project_root)
    record["status"] = "planned"

    ratified_authority = _ratified_promotion_authority(promotion_authority)
    if ratified_authority is not None:
        record["promotion_authority"] = ratified_authority
        record["human_review_gates"] = [
            build_promotion_gate(ratified_authority).model_dump(mode="json")
        ]

    if extra_record_fields:
        record.update(extra_record_fields)

    prompt_payload = {
        "command": command_name,
        "classification": classification,
        "title": title,
        "hypothesis": record["hypothesis"],
        "prompt_id": prompt_id,
        "task_id": task_id,
    }
    record["prompt_artifact"] = build_prompt_artifact(
        "experiment_registration",
        prompt_payload,
    )

    exp_path = connector.save_experiment(exp_id, record)
    record_chain_event(project_root, exp_id=exp_id, stage="TASK", artifact_id=task_id)
    record_chain_event(project_root, exp_id=exp_id, stage="PROMPT", artifact_id=prompt_id)
    record_chain_event(project_root, exp_id=exp_id, stage="EXP", artifact_id=exp_id)

    w5_payload = {
        "command": command_name,
        "action": _command_action(command_name),
        "exp_id": exp_id,
        "archive": {
            "kind": archive_kind,
            "classification": classification,
            "title": title,
            "hypothesis_h0": record["hypothesis"]["h0"],
            "prompt_hash": record["prompt_artifact"]["hash"],
            "prompt_id": prompt_id,
            "task_id": task_id,
        },
        "metadata": {
            "classification": classification,
        },
    }
    if ratified_authority is not None:
        w5_payload["archive"]["promotion_authority"] = ratified_authority
        w5_payload["metadata"]["promotion_authority"] = ratified_authority

    return {
        "exp_id": exp_id,
        "prompt_id": prompt_id,
        "task_id": task_id,
        "record": record,
        "exp_path": exp_path,
        "w5_payload": w5_payload,
    }
