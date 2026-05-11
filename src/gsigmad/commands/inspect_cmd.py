"""Project inspection command for coexistence-aware routing."""
from __future__ import annotations

import json
from pathlib import Path

import typer

from gsigmad.governance.adapters import discover_registry_root, inspect_payload, resolve_project_target


def inspect_project(
    ctx: typer.Context,
    path: Path = typer.Argument(
        Path("."),
        help="Project directory to inspect.",
    ),
) -> None:
    """Inspect how gsigmad resolves a project target before side effects."""
    target = path.resolve()
    registry_root = discover_registry_root(Path.cwd())
    resolution = resolve_project_target(target, registry_root=registry_root)
    payload = inspect_payload(resolution)
    json_output = getattr(ctx.obj, "json_output", False) if ctx.obj else False

    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    import rich
    from rich.table import Table

    rich.print(f"Project root: {payload['project_root']}")
    rich.print(f"Resolution: {payload['runtime_mode']} via {payload['source']}")
    if payload["namespace_prefix"]:
        rich.print(f"Namespace: {payload['namespace_prefix']}")
    if payload["manifest_path"]:
        rich.print(f"Manifest: {payload['manifest_path']}")

    commands = payload["compatibility"]["commands"]
    table = Table(title="Compatibility Report")
    table.add_column("Command")
    table.add_column("Mode")
    for command, mode in commands.items():
        table.add_row(command, mode)
    rich.print(table)

    issues = payload["issues"]
    if issues:
        rich.print("[yellow]Issues:[/yellow]")
        for issue in issues:
            rich.print(f"- {issue}")
