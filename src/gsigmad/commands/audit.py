"""gsigmad audit command -- validate experiment claims.

Extracts claims from EXP YAML files and runs them through audit_claims_gate
which checks effect size reporting and optionally verifies DOI/PMID citations.

Gate function is lazy-imported to avoid pulling in requests/network
dependencies at module load time.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import typer

from gsigmad.connectors import get_connector
from gsigmad.governance.artifact_integrity import find_run_manifest, verify_run_manifest
from gsigmad.governance.closure_chain import list_chain_summaries, load_chain_state
from gsigmad.governance.receipts import load_stage_receipt
from gsigmad.hub import (
    best_effort_append_command_w5,
    verify_ledger_chain,
)


def _load_audit_gate() -> Any:
    """Lazy-import audit_claims_gate function.

    Uses importlib.import_module to avoid importing requests and network
    dependencies at CLI module load time.
    """
    mod = importlib.import_module("gsigmad.governance.gates.audit_claims")
    return getattr(mod, "audit_claims_gate")


def _latest_results_integrity(chain: dict[str, Any]) -> dict[str, Any]:
    """Return the latest RESULTS integrity marker for one experiment chain."""
    history = chain.get("history", []) if isinstance(chain, dict) else []
    results_events = [event for event in history if event.get("stage") == "RESULTS"]
    latest = results_events[-1] if results_events else {}
    metadata = latest.get("metadata") or {}
    artifact_id = latest.get("artifact_id") or chain.get("results_id")
    return {
        "required": bool(metadata.get("artifact_integrity_required")),
        "results_id": artifact_id,
        "manifest_relpath": metadata.get("manifest_relpath"),
        "artifact_integrity_status": metadata.get("artifact_integrity_status"),
        "receipt_run_id": metadata.get("receipt_run_id"),
        "receipt_relpaths": metadata.get("receipt_relpaths") or [],
    }


def _receipt_visibility(project_root: Path, marker: dict[str, Any]) -> dict[str, Any]:
    relpaths = list(marker.get("receipt_relpaths") or [])
    run_id = marker.get("receipt_run_id")
    if not relpaths:
        return {
            "available": False,
            "advisory": True,
            "run_id": run_id,
            "count": 0,
            "paths": [],
            "stages": [],
            "errors": [],
        }

    stages: list[str] = []
    errors: list[dict[str, str]] = []
    for relpath in relpaths:
        try:
            receipt = load_stage_receipt(project_root, relpath)
            stages.append(receipt.stage.value)
        except Exception as exc:
            errors.append({"path": relpath, "detail": str(exc)})
    return {
        "available": not errors,
        "advisory": bool(errors),
        "run_id": run_id,
        "count": len(relpaths),
        "paths": relpaths,
        "stages": stages,
        "errors": errors,
    }


def _advisory_integrity(project_root: Path, exp_id: str) -> dict[str, Any]:
    """Return backward-compatible unavailable integrity status for legacy records."""
    placeholder = project_root / ".gsigmad" / "manifests" / exp_id / "MANIFEST.placeholder.yaml"
    result = {
        "pass": True,
        "status": "unavailable",
        "advisory": True,
        "errors": [],
    }
    if placeholder.is_file():
        result["manifest_path"] = placeholder.relative_to(project_root).as_posix()
    return result


def _verify_integrity(project_root: Path, exp_record: dict[str, Any], marker: dict[str, Any]) -> dict[str, Any]:
    """Verify artifact integrity for one experiment using RESULTS metadata as authority."""
    exp_id = str(exp_record.get("exp_id", "UNKNOWN"))
    if not marker.get("required"):
        return _advisory_integrity(project_root, exp_id)

    manifest_relpath = marker.get("manifest_relpath")
    results_id = marker.get("results_id")
    if manifest_relpath:
        manifest_path = project_root / manifest_relpath
    elif results_id:
        manifest_path = find_run_manifest(project_root, exp_id, str(results_id))
    else:
        return {
            "pass": False,
            "status": "missing",
            "advisory": False,
            "errors": [{"code": "RESULTS_ID_MISSING"}],
        }

    integrity = verify_run_manifest(project_root, exp_record=exp_record, manifest_path=manifest_path)
    if integrity.get("status") == "unavailable":
        return {
            "pass": False,
            "status": "missing",
            "advisory": False,
            "manifest_path": integrity.get("manifest_path"),
            "errors": [{"code": "MANIFEST_REQUIRED_BUT_PLACEHOLDER_ONLY"}],
        }
    return integrity


def audit_experiment(
    ctx: typer.Context,
    exp_id: str = typer.Argument(
        "",
        help="Experiment ID (e.g., EXP-1.1). Omit to audit all experiments.",
    ),
    skip_citations: bool = typer.Option(
        False,
        "--skip-citations",
        help="Skip DOI/PMID citation verification.",
    ),
    ledger: bool = typer.Option(
        False,
        "--ledger",
        help="Verify W5 ledger chain integrity instead of claim audits.",
    ),
    fdr_consistency: bool = typer.Option(
        False,
        "--fdr-consistency",
        help="Check FDR chain consistency across same-pipeline experiments.",
    ),
    traits: bool = typer.Option(
        False,
        "--traits",
        help="Show TRAITS pillar coverage matrix for all gates.",
    ),
) -> None:
    """Validate experiment claims against evidence standards."""
    cwd = Path.cwd()
    connector = get_connector(cwd)
    gsigmad_dir = cwd / ".gsigmad"
    json_output = getattr(ctx.obj, "json_output", False) if ctx.obj else False

    # Check project is initialized
    if not gsigmad_dir.is_dir():
        msg = "Not a gsigmad project (no .gsigmad/ directory). Run 'gsigmad init' first."
        if json_output:
            print(json.dumps({"error": msg}))
        else:
            import rich
            rich.print(f"[red]Error:[/red] {msg}")
        raise typer.Exit(code=1)

    if ledger:
        result = verify_ledger_chain(cwd)
        if json_output:
            print(json.dumps({"ledger": result, "passed": result["pass"]}))
        else:
            import rich

            if result["pass"]:
                rich.print(
                    f"[green]LEDGER OK[/green] -- verified {result['verified']} entry/entries."
                )
            else:
                rich.print(
                    "[red]LEDGER FAILED[/red] "
                    f"(entry {result['entry_index']}, error={result['error']})"
                )

        if result["pass"]:
            best_effort_append_command_w5(
                cwd,
                command="audit",
                action="verify_ledger_chain",
                archive={
                    "kind": "ledger_verification",
                    "verified_entries": result["verified"],
                },
                metadata={
                    "ledger_mode": True,
                },
            )
        raise typer.Exit(code=0 if result["pass"] else 1)

    # -- FDR consistency check (FDR-04) --
    if fdr_consistency:
        exp_records = connector.list_experiments()
        fdr_mod = importlib.import_module("gsigmad.governance.gates.fdr_contract")
        check_fn = getattr(fdr_mod, "check_fdr_consistency")
        fdr_result = check_fn(exp_records)

        if json_output:
            print(json.dumps({"fdr_consistency": fdr_result}))
        else:
            import rich

            if fdr_result["consistent"]:
                rich.print(
                    f"[green]FDR CONSISTENT[/green] -- "
                    f"{fdr_result['pipelines_checked']} pipeline(s) checked."
                )
            else:
                rich.print("[red]FDR INCONSISTENT[/red]")
                for inc in fdr_result["inconsistencies"]:
                    rich.print(
                        f"  [yellow]{inc['tool']}:{inc['method']}[/yellow] "
                        f"level '{inc['level']}' has thresholds "
                        f"{inc['thresholds']} across {inc['exp_ids']}"
                    )

        if fdr_result["consistent"]:
            best_effort_append_command_w5(
                cwd,
                command="audit",
                action="fdr_consistency_check",
                archive={
                    "kind": "fdr_consistency",
                    "pipelines_checked": fdr_result["pipelines_checked"],
                },
                metadata={"consistent": True},
            )
        raise typer.Exit(code=0 if fdr_result["consistent"] else 1)

    # -- TRAITS coverage matrix (REP-02) --
    if traits:
        fdr_mod = importlib.import_module("gsigmad.governance.gates.fdr_contract")
        traits_fn = getattr(fdr_mod, "traits_coverage_matrix")
        run_mod = importlib.import_module("gsigmad.commands.run")
        gate_chain = getattr(run_mod, "GATE_CHAIN")
        traits_result = traits_fn(gate_chain)

        if json_output:
            print(json.dumps({"traits_coverage": traits_result}))
        else:
            import rich

            rich.print("[bold]TRAITS Pillar Coverage Matrix[/bold]")
            for pillar, gates_list in sorted(traits_result["covered"].items()):
                rich.print(f"  [green]{pillar}[/green]: {', '.join(gates_list)}")
            if traits_result["uncovered"]:
                for pillar in traits_result["uncovered"]:
                    rich.print(f"  [yellow]{pillar}[/yellow]: (uncovered)")
            rich.print(
                f"\n  Covered: {traits_result['covered_count']}/{traits_result['total_pillars']}"
            )
        raise typer.Exit(code=0)

    # Determine which experiments to audit
    if exp_id:
        exp_path = gsigmad_dir / "experiments" / f"{exp_id}.yaml"
        try:
            exp_records = [connector.load_experiment(exp_id)]
        except KeyError:
            msg = f"Experiment file not found: {exp_path}"
            if json_output:
                print(json.dumps({"error": msg}))
            else:
                import rich
                rich.print(f"[red]Error:[/red] {msg}")
            raise typer.Exit(code=1)
    else:
        exp_records = connector.list_experiments()
        if not exp_records:
            msg = "No experiment files found in .gsigmad/experiments/"
            if json_output:
                print(json.dumps({"error": msg, "experiments": []}))
            else:
                import rich
                rich.print(f"[yellow]Warning:[/yellow] {msg}")
            raise typer.Exit(code=0)

    # Load audit gate function
    audit_gate = _load_audit_gate()

    # Process each experiment
    all_results: list[dict] = []
    any_failed = False
    closure_by_exp = {item["exp_id"]: item for item in list_chain_summaries(cwd)}
    raw_chains = load_chain_state(cwd, create=False).get("chains", {})

    for exp_record in exp_records:
        current_exp_id = exp_record.get("exp_id", exp_id or "UNKNOWN")
        marker = _latest_results_integrity(raw_chains.get(current_exp_id, {}))
        integrity = _verify_integrity(
            cwd,
            exp_record,
            marker,
        )
        receipts = _receipt_visibility(cwd, marker)
        claims = exp_record.get("claims", [])
        claim_pass = True
        failures: list[dict[str, Any]] = []
        warnings: list[str] = []
        note: str | None = None

        if not claims:
            note = "No claims to audit."
        else:
            gate_result = audit_gate(claims, verify_citations=not skip_citations)
            claim_pass = gate_result["pass"]
            failures = gate_result.get("failures", [])
            warnings = gate_result.get("warnings", [])

        passed = claim_pass and integrity.get("pass", False)
        result = {
            "exp_id": current_exp_id,
            "pass": passed,
            "failures": failures,
            "warnings": warnings,
            "note": note,
            "closure": closure_by_exp.get(current_exp_id),
            "integrity": integrity,
            "receipts": receipts,
        }
        all_results.append(result)
        if not passed:
            any_failed = True

    if not any_failed:
        best_effort_append_command_w5(
            cwd,
            command="audit",
            action="audit_claims",
            exp_id=exp_id or None,
            archive={
                "kind": "claim_audit",
                "experiment_count": len(all_results),
                "skip_citations": skip_citations,
            },
            metadata={
                "passed": True,
                "experiment_count": len(all_results),
            },
        )

    # Output results
    if json_output:
        print(json.dumps({"experiments": all_results, "passed": not any_failed}))
    else:
        import rich
        from rich.table import Table

        for r in all_results:
            status_str = "[green]PASS[/green]" if r["pass"] else "[red]FAIL[/red]"
            rich.print(f"\n[bold]{r['exp_id']}[/bold]: {status_str}")
            if r.get("note"):
                rich.print(f"  [dim]{r['note']}[/dim]")

            integrity = r.get("integrity") or {}
            integrity_status = str(integrity.get("status", "unknown")).upper()
            integrity_color = "green" if integrity.get("pass") and not integrity.get("advisory") else "yellow"
            if not integrity.get("pass"):
                integrity_color = "red"
            rich.print(f"  Integrity: [{integrity_color}]{integrity_status}[/{integrity_color}]")
            if integrity.get("manifest_path"):
                rich.print(f"  Manifest: {integrity['manifest_path']}")
            for err in integrity.get("errors", []):
                detail = err.get("detail") or err.get("path") or err.get("code")
                rich.print(f"  [yellow]Integrity detail:[/yellow] {detail}")

            if r["failures"]:
                table = Table(title=f"Failures: {r['exp_id']}")
                table.add_column("Claim", style="cyan")
                table.add_column("Error")
                table.add_column("Recommendation", style="dim")

                for f in r["failures"]:
                    claim_text = f.get("text", f.get("citation", ""))[:60]
                    error = f.get("error", "")[:80]
                    rec = f.get("recommendation", "") or ""
                    table.add_row(claim_text, error, str(rec)[:60])

                console = rich.console.Console()
                console.print(table)

            if r["warnings"]:
                for w in r["warnings"]:
                    rich.print(f"  [yellow]Warning:[/yellow] {w[:80]}")

            closure = r.get("closure")
            if closure and closure.get("missing"):
                rich.print(
                    f"  [yellow]Closure gaps:[/yellow] {', '.join(closure['missing'])}"
                )

        if any_failed:
            rich.print("\n[red]AUDIT FAILED[/red] -- one or more claim or integrity checks did not pass.")
        else:
            total_claims = sum(
                len(r.get("failures", [])) + (1 if r["pass"] and not r.get("note") else 0)
                for r in all_results
            )
            no_claims = all(r.get("note") for r in all_results)
            if no_claims:
                rich.print("[dim]No claims to audit across all experiments.[/dim]")
            else:
                rich.print("\n[green]ALL CLAIMS PASSED[/green]")

    if any_failed:
        raise typer.Exit(code=1)
