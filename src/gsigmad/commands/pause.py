"""gsigmad pause command."""
from __future__ import annotations

import json
from pathlib import Path

import typer

from gsigmad.governance.context_state import write_checkpoint
from gsigmad.hub import best_effort_append_command_w5


def pause_session(
    ctx: typer.Context,
    note: str = typer.Option("", "--note", help="Optional operator note to persist with the checkpoint."),
) -> None:
    """Write a structured checkpoint for the current project."""
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

    payload = write_checkpoint(cwd, note=note)
    best_effort_append_command_w5(
        cwd,
        command="pause",
        action="write_context_checkpoint",
        archive={"kind": "context_checkpoint", "checkpoint_path": payload["path"]},
        metadata={"recommended_command": payload["recommended_command"]},
    )

    if json_output:
        print(json.dumps(payload))
        return

    import rich

    rich.print(f"[green]Checkpoint written[/green] {payload['path']}")
    rich.print(f"Next: [bold]{payload['recommended_command']}[/bold]")
