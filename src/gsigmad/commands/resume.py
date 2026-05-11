"""gsigmad resume command."""
from __future__ import annotations

import json
from pathlib import Path

import typer

from gsigmad.governance.context_state import load_latest_checkpoint
from gsigmad.hub import best_effort_append_command_w5


def resume_session(ctx: typer.Context) -> None:
    """Restore the latest structured checkpoint for the current project."""
    cwd = Path.cwd()
    json_output = getattr(ctx.obj, "json_output", False) if ctx.obj else False
    if not (cwd / ".gsigmad").is_dir():
        msg = "Not a gsigmad project (no .gsigmad/ directory). Run 'gsigmad init' first."
        if json_output:
            print(json.dumps({"error": msg}))
        else:
            import rich

            rich.print(f"[red]Error:[/red] {msg}")
        raise typer.Exit(code=1)

    payload = load_latest_checkpoint(cwd)
    if payload is None:
        msg = "No checkpoint found. Run 'gsigmad pause' first."
        if json_output:
            print(json.dumps({"error": msg}))
        else:
            import rich

            rich.print(f"[red]Error:[/red] {msg}")
        raise typer.Exit(code=1)

    best_effort_append_command_w5(
        cwd,
        command="resume",
        action="load_context_checkpoint",
        archive={"kind": "context_resume", "checkpoint_path": payload["path"]},
        metadata={"recommended_command": payload.get("recommended_command")},
    )

    if json_output:
        print(json.dumps(payload))
        return

    import rich

    rich.print(f"[green]Restored[/green] {payload['path']}")
    rich.print(f"Coordinate: [bold]{payload.get('coordinate') or 'unknown'}[/bold]")
    rich.print(f"Next: [bold]{payload.get('recommended_command', 'gsigmad status')}[/bold]")
