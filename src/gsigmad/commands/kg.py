"""gsigmad kg subcommands."""
from __future__ import annotations

import json
from pathlib import Path

import typer

from gsigmad.governance.kg.queue_ops import inspect_queue_state
from gsigmad.governance.kg.query import format_results_table
from gsigmad.governance.kg.routed import routed_find_experiments, validate_live_kg

kg_app = typer.Typer(help="Knowledge graph live operations.")
queue_app = typer.Typer(help="Inspect local KG fallback queue state.")


def _json_mode(ctx: typer.Context) -> bool:
    return getattr(ctx.obj, "json_output", False) if ctx.obj else False


def _render_queue_inspect(payload: dict) -> None:
    import rich
    from rich.table import Table

    counts = payload["counts"]
    rich.print(f"[bold]Queue Inspect[/bold] {payload['project_root']}")
    summary = Table(title="Queue Health")
    summary.add_column("State", style="cyan")
    summary.add_column("Count", justify="right")
    summary.add_row("Pending", str(counts["pending"]))
    summary.add_row("Failed", str(counts["failed"]))
    summary.add_row("Expired", str(counts["expired"]))
    summary.add_row("Quarantine", str(counts["quarantine"]))
    summary.add_row("Retry Scheduled", str(counts["retry_scheduled"]))
    rich.print(summary)

    detail = Table(title="Queue Entries")
    detail.add_column("State", style="cyan")
    detail.add_column("Entry")
    detail.add_column("Attempts", justify="right")
    detail.add_column("Failure Class")
    detail.add_column("Next Retry")
    detail.add_column("Error")

    for state in ("pending", "failed", "expired"):
        for entry in payload["entries"][state]:
            detail.add_row(
                state,
                entry.get("entry_id") or entry.get("document", {}).get("_key") or "-",
                str(entry.get("attempts", 0)),
                entry.get("failure_class") or "-",
                entry.get("next_retry_after") or "-",
                "-",
            )
    for entry in payload["entries"]["quarantine"]:
        detail.add_row(
            "quarantine",
            entry.get("entry_id") or Path(entry.get("source_path", "-")).name,
            "-",
            "-",
            "-",
            entry.get("error") or "-",
        )

    if detail.row_count:
        rich.print(detail)
    else:
        rich.print("No queue entries found.")


@kg_app.command("find")
def find_experiments_cmd(
    ctx: typer.Context,
    path: Path = typer.Option(Path("."), "--path", help="Project directory to resolve for adapter-aware scoping."),
    project: str = typer.Option("", "--project", help="Optional explicit project name override."),
    classification: str = typer.Option("", "--classification", help="Optional experiment classification filter."),
    status: str = typer.Option("", "--status", help="Optional experiment status filter."),
    protein: str = typer.Option("", "--protein", help="Optional protein/gene symbol filter."),
    doi: str = typer.Option("", "--doi", help="Optional publication DOI filter."),
    pmid: str = typer.Option("", "--pmid", help="Optional publication PMID filter."),
    limit: int = typer.Option(100, "--limit", min=1, help="Maximum results to return."),
) -> None:
    """Run an adapter-aware KG experiment query."""
    result = routed_find_experiments(
        target_path=path,
        project=project or None,
        classification=classification or None,
        status=status or None,
        protein=protein or None,
        doi=doi or None,
        pmid=pmid or None,
        limit=limit,
    )
    json_output = _json_mode(ctx)

    if isinstance(result, dict):
        if json_output:
            print(json.dumps(result))
        else:
            import rich

            rich.print(f"[red]Error:[/red] {result.get('error')}")
        raise typer.Exit(code=1)

    if json_output:
        print(json.dumps({"results": result, "count": len(result)}))
    else:
        import rich

        rich.print(format_results_table(result))


@kg_app.command("validate")
def validate_live_kg_cmd(
    ctx: typer.Context,
    path: Path = typer.Argument(Path("."), help="Project directory to validate against."),
    doi: str = typer.Option("", "--doi", help="Optional DOI for citation-linked query validation."),
    cleanup: bool = typer.Option(True, "--cleanup/--no-cleanup", help="Remove validation artifacts after the run."),
    simulate_queue: bool = typer.Option(True, "--simulate-queue/--no-simulate-queue", help="Exercise queue fallback and replay during validation."),
) -> None:
    """Run live KG write/query validation for a resolved project target."""
    result = validate_live_kg(
        target_path=path,
        doi=doi or "10.1001/jamainternmed.2013.13563",
        cleanup=cleanup,
        simulate_queue=simulate_queue,
    )
    json_output = _json_mode(ctx)

    if json_output:
        print(json.dumps(result))
    else:
        import rich
        from rich.table import Table

        rich.print(
            f"[bold]{result['context']['project_name']}[/bold] "
            f"({result['context']['runtime_mode']}, {result['context']['resolution_source']})"
        )
        table = Table(title="KG Live Validation")
        table.add_column("Check", style="cyan")
        table.add_column("Status")
        for name, passed in result.get("checks", {}).items():
            table.add_row(name, "PASS" if passed else "FAIL")
        rich.print(table)
        if result.get("errors"):
            for error in result["errors"]:
                rich.print(f"[yellow]Note:[/yellow] {error}")

    if not result.get("pass"):
        raise typer.Exit(code=1)


@queue_app.command("inspect")
def inspect_queue_cmd(
    ctx: typer.Context,
    path: Path = typer.Argument(Path("."), help="Project directory to inspect for local queue state."),
) -> None:
    """Inspect pending, failed, expired, and quarantine queue state."""
    payload = inspect_queue_state(path)
    if _json_mode(ctx):
        print(json.dumps(payload))
        return
    _render_queue_inspect(payload)


kg_app.add_typer(queue_app, name="queue")
