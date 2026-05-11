"""gsigmad redteam command."""
from __future__ import annotations

import json
from pathlib import Path

import typer

from gsigmad.connectors import get_connector
from gsigmad.governance.closure_chain import (
    append_lab_notebook_entry,
    ensure_chain_for_experiment,
    record_chain_event,
)
from gsigmad.governance.versioning import allocate_track_id
from gsigmad.hub import best_effort_append_command_w5


def redteam_experiment(
    ctx: typer.Context,
    exp_id: str = typer.Argument(..., help="Experiment ID (e.g., EXP-1.1)"),
) -> None:
    """Run the red-team gate for an experiment."""
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

    connector = get_connector(cwd)
    try:
        exp_record = connector.load_experiment(exp_id)
    except KeyError:
        msg = f"Experiment file not found: {gsigmad_dir / 'experiments' / f'{exp_id}.yaml'}"
        if json_output:
            print(json.dumps({"error": msg}))
        else:
            import rich

            rich.print(f"[red]Error:[/red] {msg}")
        raise typer.Exit(code=1)
    ensure_chain_for_experiment(cwd, exp_record)

    from gsigmad.governance.gates.red_team import check_red_team_gate

    classification = str(exp_record.get("classification", "EXPLORATORY")).upper()
    prompt_fields = exp_record.get("prompt_fields") or exp_record.get("red_team") or exp_record.get("hypothesis", {})
    result = check_red_team_gate(classification, prompt_fields)

    if json_output:
        print(json.dumps({"exp_id": exp_id, "classification": classification, **result}))
    else:
        import rich

        if result["pass"]:
            rich.print(f"[green]REDTEAM PASS[/green] {exp_id} ({classification})")
            if result.get("log"):
                rich.print(f"[dim]{result['log']}[/dim]")
        else:
            rich.print(f"[red]REDTEAM FAIL[/red] {exp_id} ({classification})")
            if result.get("error"):
                rich.print(result["error"])

    rt_id = allocate_track_id("RT", cwd)
    if result["pass"]:
        record_chain_event(
            cwd,
            exp_id=exp_id,
            stage="RT",
            artifact_id=rt_id,
            metadata={"passed": True},
        )
        note_id = append_lab_notebook_entry(
            cwd,
            exp_id=exp_id,
            summary=f"Red-team review passed for {exp_id}",
        )
        record_chain_event(
            cwd,
            exp_id=exp_id,
            stage="LAB_NOTEBOOK",
            artifact_id=note_id,
            metadata={"summary": f"Red-team review passed for {exp_id}"},
            terminal_state="COMPLETED",
        )
        best_effort_append_command_w5(
            cwd,
            command="redteam",
            action="evaluate_red_team_gate",
            exp_id=exp_id,
            archive={"kind": "redteam_result", "classification": classification, "rt_id": rt_id},
            metadata={"passed": True},
        )
    else:
        record_chain_event(
            cwd,
            exp_id=exp_id,
            stage="RT",
            artifact_id=rt_id,
            metadata={"passed": False, "error": result.get("error")},
            terminal_state="BLOCKED",
        )
        raise typer.Exit(code=1)
