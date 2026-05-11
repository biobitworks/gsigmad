"""gsigmad register command -- pre-register a new experiment.

Creates a numbered EXP YAML file in .gsigmad/experiments/ with hypothesis,
power analysis, gates, and claims placeholders.
"""
from __future__ import annotations

import json
from enum import Enum
from pathlib import Path

import typer

from gsigmad.connectors import ConnectorProtocol, get_connector
from gsigmad.commands._experiment_creation import (
    PROMOTION_AUTHORITY,
    create_experiment_record,
)
from gsigmad.governance.anchors import AnchorValidationError
from gsigmad.hub import best_effort_append_command_w5


class ExperimentType(str, Enum):
    """Supported experiment classification types."""

    exploratory = "exploratory"
    confirmatory = "confirmatory"
    replication = "replication"


def register_experiment(
    ctx: typer.Context,
    exp_type: ExperimentType = typer.Option(
        ...,
        "--type",
        "-t",
        help="Experiment classification type.",
    ),
    hypothesis: str = typer.Option(
        "",
        "--hypothesis",
        "-H",
        help="Null hypothesis (H0) text.",
    ),
    title: str = typer.Option(
        "",
        "--title",
        help="Experiment title.",
    ),
    anchors_file: str = typer.Option(
        "",
        "--anchors-file",
        help="Repo-relative YAML or JSON anchor document for opted-in projects.",
    ),
    promotion_authority: str = typer.Option(
        "",
        "--promotion-authority",
        help=f"Explicit EXP-level ratification authority. Only {PROMOTION_AUTHORITY!r} is persisted.",
    ),
) -> None:
    """Pre-register a new experiment with hypothesis and analysis plan template."""
    cwd = Path.cwd()
    connector = get_connector(cwd)
    gsigmad_dir = cwd / ".gsigmad"
    json_output = getattr(ctx.obj, "json_output", False) if ctx.obj else False

    # Check project is initialized
    if not gsigmad_dir.is_dir():
        msg = "Not a gsigmad project (no .gsigmad/ directory). Run 'gsigmad init' first."
        if json_output:
            print(json.dumps({"error": msg}))
        else:
            import rich

            rich.print(f"[red]Error:[/red] {msg}")
        raise typer.Exit(code=1)

    classification = exp_type.value.upper()
    try:
        creation = create_experiment_record(
            cwd,
            connector,
            classification=classification,
            title=title,
            hypothesis=hypothesis,
            promotion_authority=promotion_authority or None,
            command_name="register",
            anchors_file=anchors_file or None,
        )
    except AnchorValidationError as exc:
        msg = f"Anchor validation failed: {exc}"
        if json_output:
            print(json.dumps({"error": msg}))
        else:
            import rich

            rich.print(f"[red]Error:[/red] {msg}")
        raise typer.Exit(code=1)
    except FileExistsError:
        msg = "Experiment file already exists (ID collision)."
        if json_output:
            print(json.dumps({"error": msg}))
        else:
            import rich

            rich.print(f"[red]Error:[/red] {msg}")
        raise typer.Exit(code=1)

    exp_id = creation["exp_id"]
    exp_path = creation["exp_path"]
    w5_payload = creation["w5_payload"]
    best_effort_append_command_w5(cwd, **w5_payload)

    # Success output
    if json_output:
        print(json.dumps({"exp_id": exp_id, "path": str(exp_path)}))
    else:
        import rich

        rich.print(
            f"[green]Registered[/green] {exp_id} ({classification}) at {exp_path}"
        )
