"""gsigmad status command -- project health dashboard.

Displays active experiments, drift score, and governance health.
Uses lazy imports for governance modules to avoid circular dependencies.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from gsigmad.governance.adapters import (
    build_compatibility_report,
    discover_registry_root,
    ensure_command_supported,
    inspect_payload,
    resolve_project_target,
)
from gsigmad.governance.closure_chain import list_chain_summaries
from gsigmad.governance.degradation import compute_degradation_state
from gsigmad.hub import best_effort_append_command_w5


def show_status(
    ctx: typer.Context,
    path: Path = typer.Argument(
        Path("."),
        help="Project directory to inspect.",
    ),
) -> None:
    """Show project status: active experiments, drift score, governance health."""
    cwd = path.resolve()
    registry_root = discover_registry_root(Path.cwd())
    resolution = resolve_project_target(cwd, registry_root=registry_root)
    json_output = getattr(ctx.obj, "json_output", False) if ctx.obj else False

    try:
        mode = ensure_command_supported(resolution, "status")
    except ValueError as exc:
        msg = str(exc)
        if json_output:
            print(json.dumps({"error": msg, "routing": inspect_payload(resolution)}))
        else:
            import rich

            rich.print(f"[red]Error:[/red] {msg}")
        raise typer.Exit(code=1)

    # Lazy imports to avoid circular deps and heavy module loading
    from gsigmad.governance.compiler.session_status import get_exp_status_summary

    project_root = resolution.project_root
    is_native = mode == "gsigmad" and (project_root / ".gsigmad").is_dir()
    exp_result = get_exp_status_summary(str(project_root))

    drift_result: dict | None = None
    drift_error = False
    closure_result = []
    if is_native:
        from gsigmad.governance.compiler.drift_check import check_drift

        try:
            drift_result = check_drift(str(project_root))
        except Exception:
            drift_error = True
        closure_result = list_chain_summaries(project_root)
        best_effort_append_command_w5(
            project_root,
            command="status",
            action="inspect_project_status",
            archive={
                "kind": "status_snapshot",
                "experiment_count": len(exp_result.get("exps", [])),
                "status_source": exp_result.get("source"),
                "drift_triggered": False if drift_result is None else drift_result.get("triggered", False),
                "closure_count": len(closure_result),
            },
            metadata={
                "drift_error": drift_error,
            },
        )
    else:
        drift_error = True

    routing = inspect_payload(resolution)
    degradation: dict[str, Any] | None = getattr(ctx.obj, "degradation_state", None) if ctx.obj else None
    if degradation is None and is_native:
        degradation = compute_degradation_state(project_root)

    # JSON output mode
    if json_output:
        output = {
            "routing": routing,
            "experiments": exp_result,
            "drift": drift_result if not drift_error else {"error": "not yet tracked"},
            "closure": closure_result,
            "degradation": degradation,
        }
        print(json.dumps(output, default=str))
        return

    # Rich output mode
    import rich
    from rich.table import Table
    from rich.panel import Panel

    rich.print(
        Panel(
            f"Root: {project_root}\nMode: {mode}\nSource: {resolution.source}",
            title="Routing",
        )
    )
    if degradation is not None and degradation.get("tier") != "FULL_SERVICE":
        unavailable = ", ".join(degradation.get("unavailable_services", [])) or "unknown"
        rich.print(f"Degradation: {degradation['tier']} ({unavailable})")

    # -- Experiment Table --
    exps = exp_result.get("exps", [])
    if exps:
        table = Table(title="Active Experiments")
        table.add_column("EXP ID", style="cyan")
        table.add_column("Classification", style="magenta")
        table.add_column("Status", style="green")
        table.add_column("Scaffold", style="blue")
        table.add_column("Closure", style="yellow")
        closure_by_exp = {item["exp_id"]: item for item in closure_result}
        for exp in exps:
            closure = closure_by_exp.get(exp.get("exp_id", ""))
            if closure is None:
                closure_label = "untracked"
            elif closure.get("complete"):
                closure_label = "COMPLETE"
            elif closure.get("blocked"):
                closure_label = "BLOCKED"
            else:
                closure_label = "OPEN"

            scaffold_state = exp.get("scaffold_state") or "—"
            if exp.get("scaffold_missing"):
                scaffold_state = f"{scaffold_state}:{len(exp['scaffold_missing'])}"
            table.add_row(
                exp.get("exp_id", "?"),
                exp.get("classification", "?"),
                exp.get("status", "?"),
                scaffold_state,
                closure_label,
            )
        rich.print(table)
    else:
        rich.print("[dim]No active experiments.[/dim]")

    # -- Drift Score --
    if drift_error or drift_result is None:
        rich.print(Panel("Drift: not yet tracked", title="Drift Score"))
    elif drift_result.get("triggered"):
        science_pct = drift_result.get("science_pct", 0)
        breakdown = drift_result.get("breakdown", {})
        drift_text = f"Science: {science_pct:.0f}%\nBreakdown: {breakdown}"
        if drift_result.get("pass"):
            rich.print(Panel(drift_text, title="Drift Score", subtitle="OK"))
        else:
            rich.print(
                Panel(
                    drift_text,
                    title="Drift Score",
                    subtitle="[red]DRIFT WARNING[/red]",
                )
            )
    else:
        counter = drift_result.get("counter", 0)
        rich.print(
            Panel(
                f"Counter: {counter}/{5} (next check at 5)",
                title="Drift Score",
            )
        )

    # -- Governance Health --
    health = "PASS" if exp_result.get("pass", True) else "FAIL"
    if health == "PASS":
        rich.print(f"Governance: [green]{health}[/green]")
    else:
        rich.print(f"Governance: [red]{health}[/red]")

    if closure_result:
        incomplete = [item for item in closure_result if not item.get("complete")]
        if incomplete:
            rich.print(
                f"Closure chains: [yellow]{len(incomplete)} incomplete[/yellow] "
                f"of {len(closure_result)} tracked"
            )

    compatibility = build_compatibility_report(resolution)
    unsupported = compatibility["unsupported_commands"]
    if unsupported:
        rich.print(f"Unsupported here: {', '.join(unsupported)}")
