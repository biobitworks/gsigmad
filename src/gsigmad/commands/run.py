"""gsigmad run command -- execute experiment gate chain.

Loads an EXP YAML file and runs the classification-appropriate governance
gate chain. CONFIRMATORY experiments get all 5 gates; EXPLORATORY and
REPLICATION get data_contract only.

Gate functions are lazy-imported via importlib to avoid pulling in optional
dependencies (PyMC, ArangoDB, etc.) at module load time.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import typer
import yaml

from gsigmad.connectors import get_connector
from gsigmad.governance.artifact_integrity import compare_run_manifests, write_run_manifest
from gsigmad.governance.adapters import (
    discover_registry_root,
    ensure_command_supported,
    inspect_payload,
    resolve_project_target,
)
from gsigmad.governance.closure_chain import (
    ensure_chain_for_experiment,
    load_chain_state,
    next_results_artifact_id,
    record_chain_event,
)
from gsigmad.governance.execution_contract import (
    BlockedClass,
    LaneName,
    ReceiptOutput,
    RetryPolicy,
    StageName,
    StageStatus,
    build_immutable_inputs_hash,
)
from gsigmad.governance.execution_preflight import run_execution_preflight
from gsigmad.governance.receipts import write_stage_receipt
from gsigmad.governance.replay import (
    build_replay_identity,
    build_resume_cursor,
    diagnose_replay_divergence,
    diff_receipt_runs,
    write_manifest_diff,
    write_receipt_diff,
    write_replay_identity,
    write_resume_cursor,
    write_reverification_receipt,
)
from gsigmad.hub import best_effort_append_command_w5

# Gate chain by classification -- module-level constant.
# Each entry: (gate_display_name, module_path, function_name)
GATE_CHAIN: dict[str, list[tuple[str, str, str]]] = {
    "CONFIRMATORY": [
        ("power_analysis", "gsigmad.governance.gates.power_analysis", "check_power_analysis_gate"),
        ("decision_tree", "gsigmad.governance.schemas.decision_tree", "validate_decision_tree"),
        ("fdr_contract", "gsigmad.governance.gates.fdr_contract", "check_fdr_contract_gate"),
        ("null_model", "gsigmad.governance.gates.null_model", "check_null_model_gate"),
        ("temporal_integrity", "gsigmad.governance.gates.temporal_integrity", "check_temporal_integrity"),
        ("red_team", "gsigmad.governance.gates.red_team", "check_red_team_gate"),
        ("data_contract", "gsigmad.governance.gates.data_contract", "validate_data_contract"),
    ],
    "EXPLORATORY": [
        ("null_model", "gsigmad.governance.gates.null_model", "check_null_model_gate"),
        ("data_contract", "gsigmad.governance.gates.data_contract", "validate_data_contract"),
    ],
    "REPLICATION": [
        ("null_model", "gsigmad.governance.gates.null_model", "check_null_model_gate"),
        ("data_contract", "gsigmad.governance.gates.data_contract", "validate_data_contract"),
    ],
}

_PREFLIGHT_CHECKS = ["claim_lint", "hypothesis_promotion"]
_CONFIRMATORY_PREREGISTRATION_FIELDS = ("alpha", "mesi")


def _emit_run_payload(json_output: bool, payload: dict, *, title: str | None = None) -> None:
    """Render run output in JSON or rich text."""
    if json_output:
        print(json.dumps(payload))
        return

    import rich
    from rich.console import Console
    from rich.table import Table

    if title:
        rich.print(f"[bold]{title}[/bold]")

    preflight = payload.get("preflight")
    if preflight is not None:
        rich.print("[bold]Preflight[/bold]")
        checks = preflight.get("checks", [])
        if checks:
            table = Table()
            table.add_column("Check", style="cyan")
            table.add_column("Status", justify="center")
            table.add_column("Details")
            for check in checks:
                status = "[green]PASS[/green]" if check.get("pass") else "[red]FAIL[/red]"
                details = check.get("error") or "; ".join(check.get("warnings", [])) or ""
                table.add_row(check.get("name", "unknown"), status, str(details)[:120])
            Console().print(table)
        for warning in preflight.get("warnings", []):
            rich.print(f"[yellow]Warning:[/yellow] {warning}")
        for failure in preflight.get("failures", []):
            rich.print(f"[red]Failure:[/red] {failure}")

    if payload.get("dry_run"):
        rich.print("Preflight checks: claim_lint, hypothesis_promotion")
        table = Table(title=title or "Gate Chain")
        table.add_column("Gate", style="cyan")
        table.add_column("Module", style="dim")
        table.add_column("Function", style="green")
        for gate in payload.get("gates", []):
            table.add_row(gate["gate"], gate["module"], gate["function"])
        Console().print(table)
        return

    gates = payload.get("gates", [])
    if gates:
        table = Table(title=title or "Gate Results")
        table.add_column("Gate", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("Details")
        for gate in gates:
            status = "[green]PASS[/green]" if gate["pass"] else "[red]FAIL[/red]"
            details = gate.get("error") or gate.get("note") or ""
            table.add_row(gate["gate"], status, str(details)[:120])
        Console().print(table)

    if payload.get("error"):
        rich.print(f"[red]Error:[/red] {payload['error']}")
    integrity = payload.get("integrity")
    if integrity:
        status = str(integrity.get("status", "unknown")).upper()
        color = "green" if integrity.get("verified") else "yellow"
        if integrity.get("status") == "blocked":
            color = "red"
        rich.print(f"[bold]Integrity:[/bold] [{color}]{status}[/{color}]")
        if integrity.get("manifest_path"):
            rich.print(f"Manifest: {integrity['manifest_path']}")
        if integrity.get("error"):
            rich.print(f"[red]Integrity Error:[/red] {integrity['error']}")
    elif payload.get("passed") is False:
        rich.print("[red]FAILED[/red] -- one or more gates did not pass.")
    elif payload.get("passed") is True:
        rich.print("[green]ALL GATES PASSED[/green]")


def _blocked_scaffold_payload(exp_id: str, classification: str, exp_record: dict) -> dict:
    """Build a structured non-runnable scaffold response."""
    scaffold_state = str(exp_record.get("scaffold_state"))
    return {
        "exp_id": exp_id,
        "classification": classification,
        "error": "Experiment scaffold is not runnable",
        "detail": "Non-ready scaffold_state values are blocked in Phase 20",
        "scaffold_state": scaffold_state,
        "scaffold_missing": list(exp_record.get("scaffold_missing", [])),
        "scaffold_warnings": list(exp_record.get("scaffold_warnings", [])),
    }


def _is_missing_contract_value(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _preregistration_contract_failures(exp_record: dict, classification: str) -> list[str]:
    """Return deterministic preregistration failures that do not execute gates."""
    if classification != "CONFIRMATORY":
        return []

    hypothesis = exp_record.get("hypothesis")
    if not isinstance(hypothesis, dict):
        return [
            "CONFIRMATORY_PREREGISTRATION_MISSING: hypothesis.alpha",
            "CONFIRMATORY_PREREGISTRATION_MISSING: hypothesis.mesi",
        ]

    failures = []
    for field in _CONFIRMATORY_PREREGISTRATION_FIELDS:
        if field not in hypothesis or _is_missing_contract_value(hypothesis.get(field)):
            failures.append(f"CONFIRMATORY_PREREGISTRATION_MISSING: hypothesis.{field}")
    return failures


def _preregistration_block_payload(exp_id: str, classification: str, failures: list[str]) -> dict:
    return {
        "exp_id": exp_id,
        "classification": classification,
        "error": "Experiment preregistration is incomplete",
        "detail": "CONFIRMATORY experiments require hypothesis.alpha and hypothesis.mesi before dry-run or execution.",
        "failures": failures,
    }


def _load_gate_fn(module_path: str, fn_name: str) -> Any:
    """Lazy-import a gate function by module path and function name.

    Uses importlib.import_module to avoid importing optional dependencies
    (PyMC, ArangoDB, statsmodels, etc.) at CLI module load time.
    """
    mod = importlib.import_module(module_path)
    return getattr(mod, fn_name)


def _call_gate(
    gate_name: str,
    fn: Any,
    fn_name: str,
    exp_record: dict,
    exp_path: str,
) -> dict:
    """Call a gate function with the appropriate arguments and normalize the result.

    Different gates have different signatures and return formats.
    This function normalizes all results to {"pass": bool, "error": str|None}.
    """
    try:
        if fn_name == "check_power_analysis_gate":
            result = fn(exp_record)
        elif fn_name == "validate_decision_tree":
            dt_path = exp_record.get("decision_tree", "")
            if not dt_path:
                # No decision tree path -- skip with pass and note
                return {"gate": gate_name, "pass": True, "error": None,
                        "note": "No decision_tree path in EXP record; skipped."}
            result = fn(dt_path)
            # Normalize: validate_decision_tree returns {"valid": bool} not {"pass": bool}
            return {"gate": gate_name, "pass": result.get("valid", False),
                    "error": str(result.get("errors", [])) if not result.get("valid") else None}
        elif fn_name == "check_temporal_integrity":
            data_file = exp_record.get("data_file", "")
            result = fn(exp_path, data_file)
        elif fn_name == "check_red_team_gate":
            classification = exp_record.get("classification", "")
            prompt_fields = exp_record.get("hypothesis", {})
            result = fn(classification, prompt_fields)
        elif fn_name == "check_fdr_contract_gate":
            result = fn(exp_record)
        elif fn_name == "validate_data_contract":
            contract = exp_record.get("data_contract", {})
            data = exp_record.get("data", {})
            if not contract:
                # No data contract defined -- pass with note
                return {"gate": gate_name, "pass": True, "error": None,
                        "note": "No data_contract in EXP record; skipped."}
            result = fn(contract, data)
            # Normalize: validate_data_contract returns {"valid": bool}
            return {"gate": gate_name, "pass": result.get("valid", False),
                    "error": result.get("halt_message") if not result.get("valid") else None}
        else:
            result = fn(exp_record)

        # Standard normalization for gates returning {"pass": bool, ...}
        normalized = {
            "gate": gate_name,
            "pass": result.get("pass", False),
            "error": result.get("error"),
        }
        if "traits" in result:
            normalized["traits"] = result["traits"]
        if "note" in result:
            normalized["note"] = result["note"]
        return normalized
    except Exception as exc:
        return {
            "gate": gate_name,
            "pass": False,
            "error": f"Gate execution error: {exc}",
        }


def _gate_outcomes(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reduce gate results to a stable comparison-friendly shape."""
    return [{"gate": item["gate"], "pass": bool(item["pass"])} for item in results]


def _latest_verified_results_event(project_root: Path | str, exp_id: str) -> dict[str, Any] | None:
    """Return the latest RESULTS event with verified integrity metadata."""
    state = load_chain_state(project_root, create=False)
    chain = state.get("chains", {}).get(exp_id, {})
    for event in reversed(chain.get("history", [])):
        if event.get("stage") != "RESULTS":
            continue
        metadata = event.get("metadata", {})
        if metadata.get("passed") and metadata.get("artifact_integrity_status") == "verified":
            return event
    return None


def _receipt_run_id(results_id: str) -> str:
    return results_id.replace("RESULTS-", "RUN-", 1) if results_id.startswith("RESULTS-") else f"RUN-{results_id}"


def _write_run_stage_receipt(
    project_root: Path,
    *,
    run_id: str,
    stage: StageName,
    lane: LaneName,
    exp_record: dict[str, Any],
    results_id: str,
    required_inputs: list[str],
    outputs: list[ReceiptOutput],
    status: StageStatus,
    resume_point: str,
    retry_policy: RetryPolicy,
    upstream_receipts: list[str],
    blocked_class: BlockedClass | None = None,
    escalation_trigger: str | None = None,
    hash_payload: dict[str, Any] | None = None,
) -> dict[str, str]:
    return write_stage_receipt(
        project_root,
        {
            "run_id": run_id,
            "stage": stage,
            "phase": "26",
            "wave": "2",
            "lane": lane,
            "required_inputs": required_inputs,
            "immutable_inputs_hash": build_immutable_inputs_hash(
                hash_payload
                or {
                    "exp_id": exp_record["exp_id"],
                    "classification": exp_record["classification"],
                    "results_id": results_id,
                    "stage": stage.value,
                }
            ),
            "outputs": outputs,
            "status": status,
            "blocked_class": blocked_class,
            "resume_point": resume_point,
            "retry_policy": retry_policy,
            "escalation_trigger": escalation_trigger,
            "upstream_receipts": upstream_receipts,
        },
    )


def run_experiment(
    ctx: typer.Context,
    exp_id: str = typer.Argument(..., help="Experiment ID (e.g., EXP-1.1)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="List gates without executing them."),
    replay: bool = typer.Option(False, "--replay", help="Replay a previously verified experiment run."),
) -> None:
    """Execute experiment through the governance gate chain."""
    cwd = Path.cwd()
    connector = get_connector(cwd)
    gsigmad_dir = cwd / ".gsigmad"
    json_output = getattr(ctx.obj, "json_output", False) if ctx.obj else False

    # Compatibility probe for routed/non-native project paths.
    probe_target = Path(exp_id)
    if probe_target.exists():
        registry_root = discover_registry_root(Path.cwd())
        resolution = resolve_project_target(probe_target.resolve(), registry_root=registry_root)
        routing = inspect_payload(resolution)
        try:
            ensure_command_supported(resolution, "run")
        except ValueError as exc:
            msg = str(exc)
            payload = {
                "error": msg,
                "routing": routing,
                "failure_class": "unsupported_command",
                "error_identifier": "NOT_ROUTED_SAFELY",
                "pre_dispatch_rejection": True,
            }
            if json_output:
                print(json.dumps(payload))
            else:
                import rich

                rich.print(f"[red]Error:[/red] {msg}")
            raise typer.Exit(code=1)

        msg = (
            "Project-path invocation is only supported for routed compatibility probes. "
            "Pass an experiment ID for native execution."
        )
        payload = {
            "error": msg,
            "routing": routing,
            "failure_class": "operator_misconfiguration",
            "error_identifier": "RUN_PATH_PROBE_UNSUPPORTED",
            "pre_dispatch_rejection": True,
        }
        if json_output:
            print(json.dumps(payload))
        else:
            import rich

            rich.print(f"[red]Error:[/red] {msg}")
        raise typer.Exit(code=1)

    # Check project is initialized
    if not gsigmad_dir.is_dir():
        msg = "Not a gsigmad project (no .gsigmad/ directory). Run 'gsigmad init' first."
        if json_output:
            print(json.dumps({"error": msg}))
        else:
            import rich
            rich.print(f"[red]Error:[/red] {msg}")
        raise typer.Exit(code=1)

    # Load EXP YAML
    exp_path = gsigmad_dir / "experiments" / f"{exp_id}.yaml"
    try:
        exp_record = connector.load_experiment(exp_id)
    except KeyError:
        msg = f"Experiment file not found: {exp_path}"
        if json_output:
            print(json.dumps({"error": msg}))
        else:
            import rich
            rich.print(f"[red]Error:[/red] {msg}")
        raise typer.Exit(code=1)

    classification = str(exp_record.get("classification", "")).upper()

    # Look up gate chain for classification
    if classification not in GATE_CHAIN:
        msg = f"Unknown classification '{classification}'. Must be one of: {', '.join(GATE_CHAIN.keys())}"
        if json_output:
            print(json.dumps({"error": msg}))
        else:
            import rich
            rich.print(f"[red]Error:[/red] {msg}")
        raise typer.Exit(code=1)

    gates = GATE_CHAIN[classification]

    scaffold_state = exp_record.get("scaffold_state")
    if scaffold_state is not None and str(scaffold_state) != "ready":
        payload = _blocked_scaffold_payload(exp_id, classification, exp_record)
        _emit_run_payload(json_output, payload, title=f"Run Blocked: {exp_id} ({classification})")
        raise typer.Exit(code=1)

    preregistration_failures = _preregistration_contract_failures(exp_record, classification)
    if preregistration_failures:
        payload = _preregistration_block_payload(exp_id, classification, preregistration_failures)
        _emit_run_payload(json_output, payload, title=f"Run Blocked: {exp_id} ({classification})")
        raise typer.Exit(code=1)

    exp_record["__project_root__"] = str(cwd)
    ensure_chain_for_experiment(cwd, exp_record)
    replay_baseline = _latest_verified_results_event(cwd, exp_id) if replay else None
    if replay and replay_baseline is None:
        payload = {
            "exp_id": exp_id,
            "classification": classification,
            "error": "Replay requires a prior verified RESULTS baseline",
        }
        _emit_run_payload(json_output, payload, title=f"Run Blocked: {exp_id} ({classification})")
        raise typer.Exit(code=1)
    replay_results_id = next_results_artifact_id(cwd, exp_id) if replay else None

    # Dry run: list gates without executing
    if dry_run:
        gate_info = [
            {"gate": name, "module": mod, "function": fn}
            for name, mod, fn in gates
        ]
        payload = {
            "exp_id": exp_id,
            "classification": classification,
            "dry_run": True,
            "preflight_checks": list(_PREFLIGHT_CHECKS),
            "gates": gate_info,
        }
        _emit_run_payload(json_output, payload, title=f"Gate Chain: {exp_id} ({classification}) -- DRY RUN")
        raise typer.Exit(code=0)

    results_id = replay_results_id if replay and replay_results_id is not None else next_results_artifact_id(cwd, exp_id)
    run_id = _receipt_run_id(results_id)
    receipt_relpaths: list[str] = []
    receipt_ids: list[str] = []

    preflight = {
        "passed": True,
        "failures": [],
        "warnings": [],
        "checks": [],
    }
    if classification in {"CONFIRMATORY", "EXPLORATORY"}:
        preflight = run_execution_preflight(exp_record)

    preflight_receipt = _write_run_stage_receipt(
        cwd,
        run_id=run_id,
        stage=StageName.PREFLIGHT,
        lane=LaneName.OLLARMA_DEFAULT,
        exp_record=exp_record,
        results_id=results_id,
        required_inputs=[exp_path.relative_to(cwd).as_posix()],
        outputs=[],
        status=StageStatus.PASS if preflight.get("passed", False) else StageStatus.BLOCKED,
        resume_point="execute" if preflight.get("passed", False) else "preflight",
        retry_policy=RetryPolicy.BOUNDED_LOCAL,
        upstream_receipts=[],
        blocked_class=None if preflight.get("passed", False) else BlockedClass.NON_RETRYABLE,
        escalation_trigger=None if preflight.get("passed", False) else "preflight-failed",
        hash_payload={
            "exp_id": exp_id,
            "classification": classification,
            "preflight_checks": list(_PREFLIGHT_CHECKS),
            "authority": preflight.get("authority"),
        },
    )
    receipt_relpaths.append(preflight_receipt["receipt_relpath"])
    receipt_ids.append(preflight_receipt["receipt_id"])

    if classification == "CONFIRMATORY" and not preflight.get("passed", False):
        promotion_details = preflight.get("details", {}).get("hypothesis_promotion", [])
        best_effort_append_command_w5(
            cwd,
            command="run",
            action="blocked_by_preflight",
            exp_id=exp_id,
            archive={
                "kind": "preflight_block",
                "classification": classification,
                "failures": list(preflight.get("failures", [])),
            },
            metadata={
                "classification": classification,
                "preflight_authority": preflight.get("authority"),
                "ratified_findings": [
                    detail for detail in promotion_details if detail.get("ratified")
                ],
            },
        )
        payload = {
            "exp_id": exp_id,
            "classification": classification,
            "passed": False,
            "preflight": preflight,
            "gates": [],
            "receipts": {"run_id": run_id, "paths": receipt_relpaths},
        }
        _emit_run_payload(json_output, payload, title=f"Run Blocked: {exp_id} ({classification})")
        raise typer.Exit(code=1)

    # Execute gate chain
    results: list[dict] = []
    any_failed = False

    for gate_name, module_path, fn_name in gates:
        gate_fn = _load_gate_fn(module_path, fn_name)
        gate_result = _call_gate(gate_name, gate_fn, fn_name, exp_record, str(exp_path))
        results.append(gate_result)
        if not gate_result["pass"]:
            any_failed = True

    payload = {
        "exp_id": exp_id,
        "classification": classification,
        "passed": not any_failed,
        "preflight": preflight,
        "gates": results,
        "receipts": {"run_id": run_id, "paths": receipt_relpaths},
    }
    gate_outcomes = _gate_outcomes(results)

    execute_receipt = _write_run_stage_receipt(
        cwd,
        run_id=run_id,
        stage=StageName.EXECUTE,
        lane=LaneName.OLLARMA_DEFAULT,
        exp_record=exp_record,
        results_id=results_id,
        required_inputs=[exp_path.relative_to(cwd).as_posix()],
        outputs=[],
        status=StageStatus.PASS,
        resume_point="validate",
        retry_policy=RetryPolicy.BOUNDED_LOCAL,
        upstream_receipts=[preflight_receipt["receipt_id"]],
        hash_payload={
            "exp_id": exp_id,
            "classification": classification,
            "gate_chain": [item["gate"] for item in results],
        },
    )
    receipt_relpaths.append(execute_receipt["receipt_relpath"])
    receipt_ids.append(execute_receipt["receipt_id"])

    if any_failed:
        validate_receipt = _write_run_stage_receipt(
            cwd,
            run_id=run_id,
            stage=StageName.VALIDATE,
            lane=LaneName.SIDECAR_PARALLEL,
            exp_record=exp_record,
            results_id=results_id,
            required_inputs=[exp_path.relative_to(cwd).as_posix()],
            outputs=[],
            status=StageStatus.FAIL,
            resume_point="validate",
            retry_policy=RetryPolicy.BOUNDED_LOCAL,
            upstream_receipts=[execute_receipt["receipt_id"]],
            hash_payload={
                "exp_id": exp_id,
                "classification": classification,
                "gate_outcomes": gate_outcomes,
            },
        )
        receipt_relpaths.append(validate_receipt["receipt_relpath"])
        if replay and replay_baseline is not None and replay_results_id is not None:
            baseline_outcomes = replay_baseline.get("metadata", {}).get("gate_outcomes") or []
            drift_reasons: list[dict[str, Any]] = []
            if baseline_outcomes != gate_outcomes:
                drift_reasons.append(
                    {
                        "code": "GATE_OUTCOME_DRIFT",
                        "baseline": baseline_outcomes,
                        "candidate": gate_outcomes,
                    }
                )
            payload["replay"] = {
                "replay": True,
                "replay_source_results_id": replay_baseline.get("artifact_id"),
                "governance_drift": bool(drift_reasons),
                "governance_drift_reasons": drift_reasons,
                "status": "GOVERNANCE_DRIFT" if drift_reasons else "REPLAY_FAILED",
            }
        record_chain_event(
            cwd,
            exp_id=exp_id,
            stage="RESULTS",
            artifact_id=replay_results_id if replay else None,
            metadata={
                "passed": False,
                "gate_count": len(results),
                "gate_outcomes": gate_outcomes,
                "receipt_run_id": run_id,
                "receipt_relpaths": list(receipt_relpaths),
                **(payload.get("replay") or {}),
            },
            terminal_state="FAILED",
        )
        exp_record["status"] = "failed"
        if replay and replay_results_id is not None:
            exp_record["last_run_id"] = replay_results_id
        exp_path.write_text(
            yaml.safe_dump(exp_record, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
        _emit_run_payload(json_output, payload, title=f"Gate Results: {exp_id} ({classification})")
        raise typer.Exit(code=1)

    validate_receipt = _write_run_stage_receipt(
        cwd,
        run_id=run_id,
        stage=StageName.VALIDATE,
        lane=LaneName.SIDECAR_PARALLEL,
        exp_record=exp_record,
        results_id=results_id,
        required_inputs=[exp_path.relative_to(cwd).as_posix()],
        outputs=[],
        status=StageStatus.PASS,
        resume_point="summarize",
        retry_policy=RetryPolicy.BOUNDED_LOCAL,
        upstream_receipts=[execute_receipt["receipt_id"]],
        hash_payload={
            "exp_id": exp_id,
            "classification": classification,
            "gate_outcomes": gate_outcomes,
        },
    )
    receipt_relpaths.append(validate_receipt["receipt_relpath"])
    try:
        manifest = write_run_manifest(cwd, exp_record=exp_record, results_id=results_id)
    except Exception as exc:
        error_text = str(exc)
        summarize_receipt = _write_run_stage_receipt(
            cwd,
            run_id=run_id,
            stage=StageName.SUMMARIZE,
            lane=LaneName.SIDECAR_PARALLEL,
            exp_record=exp_record,
            results_id=results_id,
            required_inputs=[exp_path.relative_to(cwd).as_posix()],
            outputs=[],
            status=StageStatus.BLOCKED,
            blocked_class=BlockedClass.NON_RETRYABLE,
            resume_point="summarize",
            retry_policy=RetryPolicy.HUMAN_RESET,
            escalation_trigger="artifact-integrity-blocked",
            upstream_receipts=[validate_receipt["receipt_id"]],
        )
        receipt_relpaths.append(summarize_receipt["receipt_relpath"])
        record_chain_event(
            cwd,
            exp_id=exp_id,
            stage="RESULTS",
            artifact_id=results_id,
            metadata={
                "passed": True,
                "gate_count": len(results),
                "gate_outcomes": gate_outcomes,
                "artifact_integrity_required": True,
                "artifact_integrity_status": "blocked",
                "artifact_integrity_error": error_text,
                "receipt_run_id": run_id,
                "receipt_relpaths": list(receipt_relpaths),
            },
            terminal_state="BLOCKED",
        )
        exp_record["status"] = "blocked"
        exp_record["last_run_id"] = results_id
        exp_path.write_text(
            yaml.safe_dump(exp_record, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
        best_effort_append_command_w5(
            cwd,
            command="run",
            action="blocked_by_artifact_integrity",
            exp_id=exp_id,
            archive={
                "kind": "artifact_integrity_block",
                "classification": classification,
                "passed_gates": [result["gate"] for result in results if result["pass"]],
            },
            metadata={
                "classification": classification,
                "gate_count": len(results),
                "passed": True,
                "artifact_integrity_required": True,
                "artifact_integrity_status": "blocked",
                "artifact_integrity_error": error_text,
            },
        )
        payload["passed"] = False
        payload["error"] = f"Artifact integrity closeout failed: {error_text}"
        payload["integrity"] = {
            "required": True,
            "status": "blocked",
            "verified": False,
            "results_id": results_id,
            "error": error_text,
        }
        payload["receipts"] = {"run_id": run_id, "paths": receipt_relpaths}
        _emit_run_payload(json_output, payload, title=f"Run Blocked: {exp_id} ({classification})")
        raise typer.Exit(code=1) from exc

    replay_metadata: dict[str, Any] = {}
    summarize_receipt = _write_run_stage_receipt(
        cwd,
        run_id=run_id,
        stage=StageName.SUMMARIZE,
        lane=LaneName.SIDECAR_PARALLEL,
        exp_record=exp_record,
        results_id=results_id,
        required_inputs=[manifest["manifest_relpath"]],
        outputs=[ReceiptOutput(path=manifest["manifest_relpath"], kind="manifest")],
        status=StageStatus.PASS,
        resume_point="interpret/escalate",
        retry_policy=RetryPolicy.BOUNDED_LOCAL,
        upstream_receipts=[validate_receipt["receipt_id"]],
        hash_payload={
            "exp_id": exp_id,
            "classification": classification,
            "manifest_relpath": manifest["manifest_relpath"],
        },
    )
    receipt_relpaths.append(summarize_receipt["receipt_relpath"])
    if replay and replay_baseline is not None:
        baseline_outcomes = replay_baseline.get("metadata", {}).get("gate_outcomes") or []
        manifest_comparison = compare_run_manifests(
            cwd,
            baseline_manifest_path=replay_baseline["metadata"]["manifest_relpath"],
            candidate_manifest_path=manifest["manifest_relpath"],
        )
        receipt_diff = diff_receipt_runs(
            cwd,
            baseline_run_id=replay_baseline.get("metadata", {}).get("receipt_run_id") or "",
            candidate_run_id=run_id,
        )
        drift_reasons = list(manifest_comparison["reasons"])
        if baseline_outcomes != gate_outcomes:
            drift_reasons.insert(
                0,
                {
                    "code": "GATE_OUTCOME_DRIFT",
                    "baseline": baseline_outcomes,
                    "candidate": gate_outcomes,
                },
            )
        drift_reasons.extend(receipt_diff["reasons"])
        governance_drift = bool(drift_reasons)
        replay_identity = build_replay_identity(
            exp_id=exp_id,
            baseline_results_id=replay_baseline["artifact_id"],
            replay_results_id=results_id,
            baseline_receipt_run_id=replay_baseline.get("metadata", {}).get("receipt_run_id"),
            replay_receipt_run_id=run_id,
            baseline_manifest_path=replay_baseline["metadata"].get("manifest_relpath"),
            replay_manifest_path=manifest["manifest_relpath"],
        )
        replay_identity_path = write_replay_identity(cwd, replay_identity)
        manifest_diff_path = write_manifest_diff(
            cwd,
            exp_id=exp_id,
            replay_results_id=results_id,
            payload=manifest_comparison,
        )
        receipt_diff_path = write_receipt_diff(
            cwd,
            exp_id=exp_id,
            replay_results_id=results_id,
            payload=receipt_diff,
        )
        diagnosis = diagnose_replay_divergence(drift_reasons)
        resume_cursor = build_resume_cursor(
            replay_id=replay_identity.replay_id,
            exp_id=exp_id,
            source_receipt_id=summarize_receipt["receipt_id"],
            stage=StageName.SUMMARIZE,
            resume_point="interpret/escalate",
            reverification_status=diagnosis["reverification_status"],
            blocked_class=BlockedClass(diagnosis["blocked_class"]) if diagnosis["blocked_class"] else None,
        )
        resume_cursor_path = write_resume_cursor(cwd, resume_cursor)
        reverification_path = write_reverification_receipt(
            cwd,
            {
                "replay_id": replay_identity.replay_id,
                "exp_id": exp_id,
                "baseline_results_id": replay_baseline["artifact_id"],
                "replay_results_id": results_id,
                "manifest_diff_path": manifest_diff_path,
                "receipt_diff_path": receipt_diff_path,
                "resume_cursor_path": resume_cursor_path,
                "reverification_status": diagnosis["reverification_status"],
                "blocked_class": diagnosis["blocked_class"],
                "reasons": drift_reasons,
            },
        )
        replay_metadata = {
            "replay": True,
            "replay_source_results_id": replay_baseline["artifact_id"],
            "governance_drift": governance_drift,
            "governance_drift_reasons": drift_reasons,
            "status": "GOVERNANCE_DRIFT" if governance_drift else "REPLAY_OK",
            "replay_identity_path": replay_identity_path,
            "manifest_diff_path": manifest_diff_path,
            "receipt_diff_path": receipt_diff_path,
            "resume_cursor_path": resume_cursor_path,
            "reverification_path": reverification_path,
            "reverification_status": diagnosis["reverification_status"],
        }
        payload["replay"] = replay_metadata
    record_chain_event(
        cwd,
        exp_id=exp_id,
        stage="RESULTS",
        artifact_id=results_id,
        metadata={
            "passed": True,
            "gate_count": len(results),
            "gate_outcomes": gate_outcomes,
            "artifact_integrity_required": True,
            "artifact_integrity_status": "verified",
            "manifest_relpath": manifest["manifest_relpath"],
            "frozen_governance_sha256": manifest["frozen_governance_sha256"],
            "receipt_run_id": run_id,
            "receipt_relpaths": list(receipt_relpaths),
            **replay_metadata,
        },
    )
    exp_record["status"] = "completed"
    exp_record["last_run_id"] = results_id
    exp_path.write_text(
        yaml.safe_dump(exp_record, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    best_effort_append_command_w5(
        cwd,
        command="run",
        action="execute_gate_chain",
        exp_id=exp_id,
        archive={
            "kind": "gate_results",
            "classification": classification,
            "passed_gates": [result["gate"] for result in results if result["pass"]],
            "manifest_relpath": manifest["manifest_relpath"],
        },
        metadata={
            "classification": classification,
            "gate_count": len(results),
            "passed": True,
            "artifact_integrity_required": True,
            "artifact_integrity_status": "verified",
        },
    )
    payload["integrity"] = {
        "required": True,
        "status": "verified",
        "verified": True,
        "results_id": results_id,
        "manifest_path": manifest["manifest_relpath"],
        "frozen_governance_sha256": manifest["frozen_governance_sha256"],
    }
    payload["receipts"] = {"run_id": run_id, "paths": receipt_relpaths}
    _emit_run_payload(json_output, payload, title=f"Gate Results: {exp_id} ({classification})")
