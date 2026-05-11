"""Scaffold a governed experiment workspace."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import typer
import yaml

from gsigmad.commands._experiment_creation import (
    PROMOTION_AUTHORITY,
    create_experiment_record,
)
from gsigmad.commands.register import ExperimentType
from gsigmad.connectors import get_connector
from gsigmad.governance.anchors import AnchorValidationError
from gsigmad.governance.closure_chain import append_lab_notebook_entry
from gsigmad.governance.execution_contract import (
    LaneName,
    ReceiptOutput,
    RetryPolicy,
    StageName,
    StageStatus,
    build_immutable_inputs_hash,
)
from gsigmad.governance.receipts import write_stage_receipt
from gsigmad.hub import best_effort_append_command_w5
from gsigmad.scaffold.templates import result_manifest_placeholder, script_template


def _emit(payload: dict[str, Any], *, json_output: bool, success: bool, exp_id: str) -> None:
    if json_output:
        print(json.dumps(payload, default=str))
        return

    import rich

    state = payload.get("scaffold_state", "unknown")
    color = "green" if success else "red"
    rich.print(f"[{color}]Scaffold {state}[/{color}] {exp_id}")
    rich.print(f"Path: {payload['path']}")
    if payload.get("created"):
        rich.print(f"Created: {', '.join(payload['created'])}")
    if payload.get("skipped"):
        rich.print(f"Skipped: {', '.join(payload['skipped'])}")
    if payload.get("missing"):
        rich.print(f"Missing: {', '.join(payload['missing'])}")
    if payload.get("warnings"):
        rich.print(f"Warnings: {', '.join(payload['warnings'])}")


def _write_yaml(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def _save_record(exp_path: Path, record: dict[str, Any]) -> None:
    exp_path.write_text(
        yaml.safe_dump(record, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def _ensure_dir(path: Path, created: list[str], skipped: list[str]) -> None:
    if path.exists():
        if not path.is_dir():
            raise RuntimeError(f"ARTIFACT_COLLISION:{path}")
        skipped.append(str(path))
        return
    path.mkdir(parents=True, exist_ok=False)
    created.append(str(path))


def _ensure_text_file(path: Path, content: str, created: list[str], skipped: list[str]) -> None:
    if path.exists():
        if not path.is_file():
            raise RuntimeError(f"ARTIFACT_COLLISION:{path}")
        skipped.append(str(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    created.append(str(path))


def _append_journal_entry(
    project_root: Path,
    *,
    exp_id: str,
    classification: str,
    script_rel: str,
    manifest_dir_rel: str,
    scaffold_state: str,
    warning_codes: list[str],
    missing_codes: list[str],
) -> Path:
    today = datetime.now(timezone.utc).date().isoformat()
    journal_path = project_root / ".gsigmad" / "journal" / f"{today}.yaml"
    if journal_path.is_file():
        existing = yaml.safe_load(journal_path.read_text(encoding="utf-8")) or []
        if not isinstance(existing, list):
            raise RuntimeError("JOURNAL_INVALID_FORMAT")
        entries = existing
    else:
        entries = []

    entries.append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "exp_id": exp_id,
            "event": "scaffold",
            "classification": classification,
            "script": script_rel,
            "manifest_dir": manifest_dir_rel,
            "scaffold_state": scaffold_state,
            "missing_codes": missing_codes,
            "warning_codes": warning_codes,
        }
    )
    _write_yaml(journal_path, entries)
    return journal_path


def _append_w5_warning_only(project_root: Path, warnings_list: list[str], w5_payload: dict[str, Any]) -> None:
    try:
        best_effort_append_command_w5(project_root, **w5_payload)
    except Exception:
        warnings_list.append("W5_APPEND_FAILED")


def _write_scaffold_receipt(
    project_root: Path,
    *,
    exp_id: str,
    classification: str,
    exp_path: Path,
    manifest_path: Path,
    results_dir: Path,
    record: dict[str, Any],
) -> dict[str, str]:
    root = project_root.resolve()
    return write_stage_receipt(
        root,
        {
            "run_id": f"RUN-SCAFFOLD-{exp_id}",
            "stage": StageName.SCAFFOLD_MATERIALIZE,
            "phase": "26",
            "wave": "2",
            "lane": LaneName.OLLARMA_DEFAULT,
            "required_inputs": [
                exp_path.relative_to(root).as_posix(),
                manifest_path.relative_to(root).as_posix(),
            ],
            "immutable_inputs_hash": build_immutable_inputs_hash(
                {
                    "exp_id": exp_id,
                    "classification": classification,
                    "record_schema_version": record.get("record_schema_version"),
                    "promotion_authority": record.get("promotion_authority"),
                }
            ),
            "outputs": [
                ReceiptOutput(path=exp_path.relative_to(root).as_posix(), kind="note"),
                ReceiptOutput(path=manifest_path.relative_to(root).as_posix(), kind="manifest"),
                ReceiptOutput(path=results_dir.relative_to(root).as_posix(), kind="bundle"),
            ],
            "status": StageStatus.PASS,
            "blocked_class": None,
            "resume_point": "execute",
            "retry_policy": RetryPolicy.BOUNDED_LOCAL,
            "escalation_trigger": None,
            "upstream_receipts": [],
        },
    )


def scaffold_experiment(
    ctx: typer.Context,
    exp_type: ExperimentType = typer.Option(..., "--type", "-t"),
    hypothesis: str = typer.Option("", "--hypothesis", "-H"),
    title: str = typer.Option("", "--title"),
    anchors_file: str = typer.Option(
        "",
        "--anchors-file",
        help="Repo-relative YAML or JSON anchor document for opted-in projects.",
    ),
    promotion_authority: str = typer.Option("", "--promotion-authority"),
) -> None:
    """Scaffold a governed experiment workspace."""
    cwd = Path.cwd()
    connector = get_connector(cwd)
    gsigmad_dir = cwd / ".gsigmad"
    json_output = getattr(ctx.obj, "json_output", False) if ctx.obj else False

    if not gsigmad_dir.is_dir():
        msg = "Not a gsigmad project (no .gsigmad/ directory). Run 'gsigmad init' first."
        if json_output:
            print(json.dumps({"error": msg}))
        else:
            import rich

            rich.print(f"[red]Error:[/red] {msg}")
        raise typer.Exit(code=1)

    if promotion_authority and promotion_authority != PROMOTION_AUTHORITY:
        msg = (
            "Invalid --promotion-authority. "
            f"Only {PROMOTION_AUTHORITY!r} is accepted."
        )
        if json_output:
            print(json.dumps({"error": msg}))
        else:
            import rich

            rich.print(f"[red]Error:[/red] {msg}")
        raise typer.Exit(code=1)

    classification = exp_type.value.upper()
    try:
        creation = create_experiment_record(
            cwd,
            connector,
            classification=classification,
            title=title,
            hypothesis=hypothesis,
            promotion_authority=promotion_authority or None,
            command_name="scaffold",
            archive_kind="scaffold_context",
            anchors_file=anchors_file or None,
        )
    except AnchorValidationError as exc:
        msg = f"Anchor validation failed: {exc}"
        if json_output:
            print(json.dumps({"error": msg}))
        else:
            import rich

            rich.print(f"[red]Error:[/red] {msg}")
        raise typer.Exit(code=1)

    exp_id = creation["exp_id"]
    exp_path = Path(creation["exp_path"])
    record = creation["record"]
    w5_payload = creation["w5_payload"]
    created: list[str] = [str(exp_path)]
    skipped: list[str] = []
    warnings_list: list[str] = []
    missing: list[str] = []

    script_rel = f"scripts/{exp_id}_analysis.py"
    manifest_dir_rel = f".gsigmad/manifests/{exp_id}"
    script_path = cwd / script_rel
    results_dir = cwd / "results" / exp_id
    manifest_dir = cwd / ".gsigmad" / "manifests" / exp_id
    manifest_path = manifest_dir / "MANIFEST.placeholder.yaml"

    try:
        _ensure_text_file(
            script_path,
            script_template(exp_id, classification, title),
            created,
            skipped,
        )
        _ensure_dir(results_dir, created, skipped)
        _ensure_dir(manifest_dir, created, skipped)
        _ensure_text_file(
            manifest_path,
            yaml.safe_dump(
                result_manifest_placeholder(exp_id),
                default_flow_style=False,
                sort_keys=False,
            ),
            created,
            skipped,
        )

        summary = (
            f"Scaffolded {classification} experiment; "
            f"script={script_rel}; manifest_dir={manifest_dir_rel}"
        )
        notebook_id = append_lab_notebook_entry(cwd, exp_id=exp_id, summary=summary)
        created.append(str(cwd / ".gsigmad" / "LAB_NOTEBOOK.md"))
        journal_path = _append_journal_entry(
            cwd,
            exp_id=exp_id,
            classification=classification,
            script_rel=script_rel,
            manifest_dir_rel=manifest_dir_rel,
            scaffold_state="ready",
            warning_codes=[],
            missing_codes=[],
        )
        created.append(str(journal_path))

        record["scaffold_state"] = "ready"
        record["notebook_entry_id"] = notebook_id
        record.pop("scaffold_missing", None)
        record.pop("scaffold_warnings", None)
        _save_record(exp_path, record)
    except Exception as exc:
        code = str(exc)
        missing.append(code if ":" in code else type(exc).__name__.upper())
        record["scaffold_state"] = "incomplete"
        record["scaffold_missing"] = missing
        record["scaffold_warnings"] = warnings_list
        _save_record(exp_path, record)
        try:
            _append_journal_entry(
                cwd,
                exp_id=exp_id,
                classification=classification,
                script_rel=script_rel,
                manifest_dir_rel=manifest_dir_rel,
                scaffold_state="incomplete",
                warning_codes=warnings_list,
                missing_codes=missing,
            )
        except Exception:
            pass
        payload = {
            "result": "incomplete",
            "exp_id": exp_id,
            "path": str(exp_path),
            "created": created,
            "skipped": skipped,
            "missing": missing,
            "warnings": warnings_list,
            "classification": classification,
            "scaffold_state": "incomplete",
            "promotion_authority": record.get("promotion_authority"),
        }
        _emit(payload, json_output=json_output, success=False, exp_id=exp_id)
        raise typer.Exit(code=1)

    receipt = _write_scaffold_receipt(
        cwd,
        exp_id=exp_id,
        classification=classification,
        exp_path=exp_path,
        manifest_path=manifest_path,
        results_dir=results_dir,
        record=record,
    )
    _append_w5_warning_only(cwd, warnings_list, w5_payload)
    payload = {
        "result": "ready",
        "exp_id": exp_id,
        "path": str(exp_path),
        "created": created,
        "skipped": skipped,
        "warnings": warnings_list,
        "classification": classification,
        "scaffold_state": "ready",
        "promotion_authority": record.get("promotion_authority"),
        "receipts": [receipt["receipt_relpath"]],
    }
    _emit(payload, json_output=json_output, success=True, exp_id=exp_id)
