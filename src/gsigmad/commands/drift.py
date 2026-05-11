"""gsigmad drift command."""
from __future__ import annotations

import json
from pathlib import Path

import typer

from gsigmad.hub import best_effort_append_command_w5


def scan_drift(ctx: typer.Context) -> None:
    """Run the drift check for the current project."""
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

    from gsigmad.governance.compiler.drift_check import check_drift

    result = check_drift(str(cwd))
    if json_output:
        print(json.dumps(result))
    else:
        import rich

        if result.get("triggered"):
            if result.get("pass"):
                rich.print(
                    f"[green]DRIFT PASS[/green] science={result.get('science_pct', 0):.0f}% breakdown={result.get('breakdown', {})}"
                )
            else:
                rich.print(result.get("error", "DRIFT_WARNING"))
        else:
            rich.print(f"[dim]Counter: {result.get('counter', 0)}/5[/dim]")

    if result.get("pass"):
        best_effort_append_command_w5(
            cwd,
            command="drift",
            action="run_drift_check",
            archive={"kind": "drift_result", "triggered": result.get("triggered", False)},
            metadata={"passed": True},
        )
    else:
        raise typer.Exit(code=1)
