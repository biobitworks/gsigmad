"""gsigmad report subcommands."""
from __future__ import annotations

import getpass
import json
from pathlib import Path

import typer
import yaml

from gsigmad.governance.closure_chain import (
    append_lab_notebook_entry,
    record_chain_event,
)
from gsigmad.governance.versioning import allocate_track_id
from gsigmad.hub import best_effort_append_command_w5

report_app = typer.Typer(help="Registered report workflows.")


def _json_mode(ctx: typer.Context) -> bool:
    return getattr(ctx.obj, "json_output", False) if ctx.obj else False


def _project_guard(cwd: Path, json_output: bool) -> None:
    if not (cwd / ".gsigmad").is_dir():
        msg = "Not a gsigmad project (no .gsigmad/ directory). Run 'gsigmad init' first."
        if json_output:
            print(json.dumps({"error": msg}))
        else:
            import rich

            rich.print(f"[red]Error:[/red] {msg}")
        raise typer.Exit(code=1)


@report_app.command("lock")
def lock_registered_report(
    ctx: typer.Context,
    exp_id: str = typer.Argument(..., help="Experiment ID (e.g., EXP-1.1)"),
    file: Path | None = typer.Option(None, "--file", help="Pre-registration file to lock."),
    locked_by: str = typer.Option("", "--locked-by", help="Actor/SIG identity for the lock."),
) -> None:
    """Lock an experiment's pre-registration artifact."""
    cwd = Path.cwd()
    json_output = _json_mode(ctx)
    _project_guard(cwd, json_output)

    pre_reg = file or (cwd / ".gsigmad" / "experiments" / f"{exp_id}.yaml")
    if not pre_reg.exists():
        msg = f"Pre-registration file not found: {pre_reg}"
        if json_output:
            print(json.dumps({"error": msg}))
        else:
            import rich

            rich.print(f"[red]Error:[/red] {msg}")
        raise typer.Exit(code=1)

    from gsigmad.governance.reports.registered_report import lock_report

    actor = locked_by or getpass.getuser()
    result = lock_report(exp_id, str(pre_reg.relative_to(cwd)), actor, str(cwd))
    if json_output:
        print(json.dumps(result))
    else:
        import rich

        if result.get("pass"):
            rich.print(f"[green]Locked[/green] {exp_id}")
        else:
            rich.print(f"[red]Error:[/red] {result.get('error')}")

    if result.get("pass"):
        best_effort_append_command_w5(
            cwd,
            command="report lock",
            action="lock_registered_report",
            exp_id=exp_id,
            archive={"kind": "report_lock", "pre_reg_file": str(pre_reg.relative_to(cwd))},
            metadata={"locked_by": actor},
        )
    else:
        raise typer.Exit(code=1)


@report_app.command("amend")
def amend_registered_report(
    ctx: typer.Context,
    exp_id: str = typer.Argument(..., help="Experiment ID (e.g., EXP-1.1)"),
    json_file: Path = typer.Option(..., "--json-file", help="JSON or YAML amendment payload file."),
    created_by: str = typer.Option("", "--created-by", help="Actor identity for the amendment."),
) -> None:
    """Create a governed amendment from a payload file."""
    cwd = Path.cwd()
    json_output = _json_mode(ctx)
    _project_guard(cwd, json_output)

    text = json_file.read_text(encoding="utf-8")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = yaml.safe_load(text)

    if not isinstance(payload, dict):
        msg = f"Amendment payload must be a JSON/YAML object: {json_file}"
        if json_output:
            print(json.dumps({"error": msg}))
        else:
            import rich

            rich.print(f"[red]Error:[/red] {msg}")
        raise typer.Exit(code=1)

    payload["exp_id"] = exp_id
    if created_by:
        payload["created_by"] = created_by

    from gsigmad.governance.reports.amendment import create_amendment

    result = create_amendment(payload, str(cwd))
    if json_output:
        print(json.dumps(result))
    else:
        import rich

        if result.get("pass"):
            rich.print(f"[green]Amendment created[/green] {result.get('amendment_file')}")
        else:
            rich.print(f"[red]Error:[/red] {result.get('error')}")

    if result.get("pass"):
        rem_id = allocate_track_id("REM", cwd)
        record_chain_event(
            cwd,
            exp_id=exp_id,
            stage="REM",
            artifact_id=rem_id,
            metadata={"amendment_file": result.get("amendment_file")},
        )
        note_id = append_lab_notebook_entry(
            cwd,
            exp_id=exp_id,
            summary=f"Amendment recorded for {exp_id}: {result.get('amendment_file')}",
        )
        record_chain_event(
            cwd,
            exp_id=exp_id,
            stage="LAB_NOTEBOOK",
            artifact_id=note_id,
            metadata={"summary": f"Amendment recorded for {exp_id}"},
            terminal_state="COMPLETED",
        )
        best_effort_append_command_w5(
            cwd,
            command="report amend",
            action="create_report_amendment",
            exp_id=exp_id,
            archive={
                "kind": "report_amendment",
                "amendment_file": result.get("amendment_file"),
                "rem_id": rem_id,
            },
            metadata={"amendment_n": result.get("amendment_n")},
        )
    else:
        raise typer.Exit(code=1)
