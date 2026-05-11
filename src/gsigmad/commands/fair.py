"""gsigmad fair command."""
from __future__ import annotations

import json
from pathlib import Path

import typer

from gsigmad.hub import best_effort_append_command_w5


def fair_check(
    ctx: typer.Context,
    exp_id: str = typer.Argument(..., help="Experiment ID (e.g., EXP-1.1)"),
) -> None:
    """Run FAIR compliance assessment for an experiment."""
    cwd = Path.cwd()
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

    from gsigmad.governance.fair.fair_check import run_fair_check

    result = run_fair_check(exp_id=exp_id, gsd_root=str(cwd))
    if json_output:
        print(json.dumps(result))
    else:
        import rich
        from rich.table import Table

        rich.print(f"[bold]{exp_id}[/bold]: {result['summary']}")
        table = Table(title="FAIR Dimensions")
        table.add_column("Dimension", style="cyan")
        table.add_column("Status")
        for dimension, payload in result.get("dimensions", {}).items():
            table.add_row(dimension, "PASS" if payload.get("pass") else "FAIL")
        rich.print(table)

    if result.get("pass"):
        best_effort_append_command_w5(
            cwd,
            command="fair",
            action="run_fair_check",
            exp_id=exp_id,
            archive={"kind": "fair_result", "total_score": result.get("total_score")},
            metadata={"passed": True, "total_score": result.get("total_score")},
        )
    else:
        raise typer.Exit(code=1)
