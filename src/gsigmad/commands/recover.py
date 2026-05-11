"""Recovery diagnose and repair command surface."""
from __future__ import annotations

import json
from pathlib import Path

import typer

from gsigmad.governance.recovery import diagnose_recovery_state, repair_recovery_state, review_recovery_state

recover_app = typer.Typer(help="Diagnose and repair local governance-state corruption.")


def _json_mode(ctx: typer.Context) -> bool:
    return getattr(ctx.obj, "json_output", False) if ctx.obj else False


def _render_diagnose(payload: dict) -> None:
    import rich
    from rich.table import Table

    rich.print("[bold]Recovery Diagnose[/bold]")
    rich.print(f"Project: {payload['project_root']}")
    summary = payload["summary"]
    rich.print(
        f"Issues: {summary['issue_count']} "
        f"(errors={summary['errors']}, warnings={summary['warnings']}, auto_repairable={summary['auto_repairable']})"
    )

    if not payload["issues"]:
        rich.print("[green]No recovery issues detected[/green]")
        return

    table = Table(title="Recovery Issues")
    table.add_column("Category", style="cyan")
    table.add_column("Code")
    table.add_column("Scope")
    table.add_column("Repairable")
    table.add_column("Description")
    for issue in payload["issues"]:
        table.add_row(
            issue["category"],
            issue["code"],
            issue.get("exp_id") or "-",
            "yes" if issue["auto_repairable"] else "no",
            issue["description"],
        )
    rich.print(table)
    for issue in payload["issues"]:
        rich.print(f"[dim]{issue['code']}[/dim]: {issue['suggested_action']}")


def _render_repair(payload: dict) -> None:
    import rich
    from rich.table import Table

    rich.print("[bold]Recovery Repair[/bold]")
    rich.print(f"Project: {payload['project_root']}")
    rich.print("Mode: apply" if payload["applied"] else "Mode: dry-run")
    if payload.get("attestation"):
        rich.print(f"Attestation: {payload['attestation']}")

    if payload["actions"]:
        table = Table(title="Planned/Applied Targets")
        table.add_column("Target", style="cyan")
        table.add_column("Issue Count", justify="right")
        for action in payload["actions"]:
            table.add_row(action["target"], str(len(action["issues"])))
        rich.print(table)
    else:
        rich.print("[green]No repair actions required[/green]")

    for backup in payload["backups"]:
        rich.print(f"Backup: {backup['backup_path']}")

    for audit in payload["audit"]:
        rich.print(f"Audit target: {audit['target']}")


def _render_review(payload: dict) -> None:
    import rich
    from rich.table import Table

    rich.print("[bold]Recovery Review[/bold]")
    rich.print(f"Project: {payload['project_root']}")
    summary = payload["summary"]
    rich.print(
        f"Dead-letter={summary['dead_letter']} "
        f"Non-retryable={summary['non_retryable']} "
        f"Retry evidence={summary['retry_evidence']}"
    )

    table = Table(title="Terminal Queue Work")
    table.add_column("Bucket", style="cyan")
    table.add_column("Entry")
    table.add_column("Failure Class")
    table.add_column("Attempts", justify="right")

    for bucket in ("dead_letter", "non_retryable"):
        for entry in payload["entries"][bucket]:
            table.add_row(
                bucket,
                entry.get("entry_id") or entry.get("document", {}).get("_key") or "-",
                entry.get("failure_class") or "-",
                str(entry.get("attempts", 0)),
            )

    if table.row_count:
        rich.print(table)
    else:
        rich.print("[green]No terminal queue work detected[/green]")


@recover_app.command("diagnose")
def diagnose_cmd(
    ctx: typer.Context,
    path: Path = typer.Argument(Path("."), help="Project directory to diagnose."),
) -> None:
    """Run a read-only diagnosis over local governance state."""
    payload = diagnose_recovery_state(path)
    if _json_mode(ctx):
        print(json.dumps(payload))
        return
    _render_diagnose(payload)


@recover_app.command("repair")
def repair_cmd(
    ctx: typer.Context,
    path: Path = typer.Argument(Path("."), help="Project directory to repair."),
    target: str = typer.Option("all", "--target", help="Repair target: ledger, queue, closure, or all."),
    apply: bool = typer.Option(False, "--apply", help="Apply the repair instead of returning a dry-run preview."),
    attestation: str = typer.Option("", "--attestation", help="Operator attestation required for apply mode."),
) -> None:
    """Preview or apply governed local-state recovery."""
    json_output = _json_mode(ctx)
    try:
        payload = repair_recovery_state(
            path,
            target=target,
            apply=apply,
            attestation=attestation or None,
        )
    except ValueError as exc:
        if json_output:
            print(json.dumps({"error": str(exc)}))
        else:
            import rich

            rich.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)

    if json_output:
        print(json.dumps(payload))
        return
    _render_repair(payload)


@recover_app.command("review")
def review_cmd(
    ctx: typer.Context,
    path: Path = typer.Argument(Path("."), help="Project directory to review."),
) -> None:
    """Review dead-letter and non-retryable queue work without mutation."""
    payload = review_recovery_state(path)
    if _json_mode(ctx):
        print(json.dumps(payload))
        return
    _render_review(payload)
