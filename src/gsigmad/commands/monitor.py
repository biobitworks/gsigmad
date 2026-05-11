"""Operational monitoring command surface."""
from __future__ import annotations

import json
from pathlib import Path

import typer

from gsigmad.governance.adapters import discover_registry_root, ensure_command_supported, resolve_project_target
from gsigmad.governance.monitoring import (
    collect_monitoring_scan,
    install_monitoring_schedule,
    monitoring_history,
    monitoring_summary,
    set_monitoring_baseline,
    uninstall_monitoring_schedule,
)

monitor_app = typer.Typer(help="Operational monitoring and scheduling.")


def _json_mode(ctx: typer.Context) -> bool:
    return getattr(ctx.obj, "json_output", False) if ctx.obj else False


def _ensure_monitorable(target: Path) -> None:
    registry_root = discover_registry_root(Path.cwd())
    resolution = resolve_project_target(target.resolve(), registry_root=registry_root)
    ensure_command_supported(resolution, "monitor")


@monitor_app.command("scan")
def scan_monitoring(
    ctx: typer.Context,
    path: Path = typer.Argument(Path("."), help="Project directory to monitor."),
    write_artifacts: bool = typer.Option(True, "--write/--no-write", help="Persist scan artifacts locally."),
) -> None:
    """Run the adapter-aware monitoring scan."""
    target = path.resolve()
    json_output = _json_mode(ctx)
    try:
        _ensure_monitorable(target)
        result = collect_monitoring_scan(target, write_artifacts=write_artifacts)
    except ValueError as exc:
        if json_output:
            print(json.dumps({"error": str(exc)}))
        else:
            import rich

            rich.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)

    if json_output:
        print(json.dumps(result, default=str))
        return

    import rich

    summary = result["summary"]
    rich.print(f"Project: {result['project_name']}")
    rich.print(f"Mode: {result['routing']['runtime_mode']} via {result['routing']['source']}")
    rich.print(f"KG available: {result['kg']['available']}")
    rich.print(
        "Queue: "
        f"pending={result['queue']['pending_count']} "
        f"failed={result['queue']['failed_count']} "
        f"expired={result['queue']['expired_count']}"
    )
    rich.print(f"Changes detected: {summary['change_count']}")
    if summary["has_alert"]:
        rich.print("[yellow]Alert active[/yellow] — run `gsigmad monitor baseline` to accept the current state after expected rollout changes.")


@monitor_app.command("install")
def install_monitor(
    ctx: typer.Context,
    path: Path = typer.Argument(Path("."), help="Project directory to monitor."),
    scheduler: str = typer.Option("launchd", "--scheduler", help="Scheduler type: launchd or cron."),
    interval_minutes: int = typer.Option(60, "--interval-minutes", help="Schedule interval in minutes."),
) -> None:
    """Install local scheduler artifacts for monitoring."""
    target = path.resolve()
    json_output = _json_mode(ctx)
    try:
        _ensure_monitorable(target)
        result = install_monitoring_schedule(target, scheduler=scheduler, interval_minutes=interval_minutes)
    except ValueError as exc:
        if json_output:
            print(json.dumps({"error": str(exc)}))
        else:
            import rich

            rich.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)

    if json_output:
        print(json.dumps(result, default=str))
        return

    import rich

    install = result["install"]
    rich.print(f"[green]Installed[/green] {install['scheduler']} schedule for {Path(install['project_root']).name}")
    rich.print(f"Artifact: {install['artifact_path']}")


@monitor_app.command("uninstall")
def uninstall_monitor(
    ctx: typer.Context,
    path: Path = typer.Argument(Path("."), help="Project directory to monitor."),
    scheduler: str | None = typer.Option(None, "--scheduler", help="Optional scheduler to remove; removes all by default."),
) -> None:
    """Remove monitoring scheduler artifacts."""
    target = path.resolve()
    json_output = _json_mode(ctx)
    try:
        _ensure_monitorable(target)
        result = uninstall_monitoring_schedule(target, scheduler=scheduler)
    except ValueError as exc:
        if json_output:
            print(json.dumps({"error": str(exc)}))
        else:
            import rich

            rich.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)

    if json_output:
        print(json.dumps(result, default=str))
        return

    import rich

    removed = ", ".join(result["removed"]) if result["removed"] else "nothing"
    rich.print(f"Removed: {removed}")


@monitor_app.command("baseline")
def baseline_monitor(
    ctx: typer.Context,
    path: Path = typer.Argument(Path("."), help="Project directory to monitor."),
) -> None:
    """Accept the current monitoring signature as the baseline."""
    target = path.resolve()
    json_output = _json_mode(ctx)
    try:
        _ensure_monitorable(target)
        result = set_monitoring_baseline(target)
    except ValueError as exc:
        if json_output:
            print(json.dumps({"error": str(exc)}))
        else:
            import rich

            rich.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)

    if json_output:
        print(json.dumps(result, default=str))
        return

    import rich

    rich.print(f"[green]Baseline updated[/green] for {result['baseline']['project_name']}")


@monitor_app.command("history")
def history_monitor(
    ctx: typer.Context,
    path: Path = typer.Argument(Path("."), help="Project directory to monitor."),
    limit: int = typer.Option(10, "--limit", help="Maximum number of scans to return."),
) -> None:
    """Show local monitoring history."""
    target = path.resolve()
    json_output = _json_mode(ctx)
    try:
        _ensure_monitorable(target)
        result = monitoring_history(target, limit=limit)
    except ValueError as exc:
        if json_output:
            print(json.dumps({"error": str(exc)}))
        else:
            import rich

            rich.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)

    if json_output:
        print(json.dumps(result, default=str))
        return

    import rich
    from rich.table import Table

    table = Table(title="Monitoring History")
    table.add_column("Generated")
    table.add_column("Mode")
    table.add_column("Changes")
    table.add_column("Pass")
    for scan in result["scans"]:
        table.add_row(
            scan["generated_at"],
            scan["routing"]["runtime_mode"],
            str(len(scan.get("changes", []))),
            "yes" if scan.get("summary", {}).get("pass") else "no",
        )
    rich.print(table)


@monitor_app.command("summary")
def summary_monitor(
    ctx: typer.Context,
    path: Path = typer.Argument(Path("."), help="Project directory to monitor."),
    limit: int = typer.Option(10, "--limit", help="Maximum history entries to include."),
) -> None:
    """Show the current machine-readable monitoring summary."""
    target = path.resolve()
    json_output = _json_mode(ctx)
    try:
        _ensure_monitorable(target)
        result = monitoring_summary(target, limit=limit)
    except ValueError as exc:
        if json_output:
            print(json.dumps({"error": str(exc)}))
        else:
            import rich

            rich.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)

    if json_output:
        print(json.dumps(result, default=str))
        return

    import rich

    current = result["current"]
    rich.print(f"Project: {result['project_name']}")
    rich.print(f"Last scan: {current['generated_at']}")
    rich.print(f"Mode: {current['routing']['runtime_mode']} via {current['routing']['source']}")
    rich.print(f"Recent history entries: {result['history']['count']}")
    rich.print(f"Last successful scan: {result['history']['last_successful_scan'] or 'none'}")
    if result["open_alert"]:
        rich.print("[yellow]Open alert present[/yellow]")

