"""gsigmad init command -- initialize a governed science project.

Creates the .gsigmad/ directory structure with config.yaml, experiments/,
ledger/, LAB_NOTEBOOK.md, and a root CANON.md template.  Also scaffolds
the full working tree (prompts/, .agent/, etc.) and installs bundled skills.

Supports idempotent upgrade: re-running on an existing project upgrades
schema_version and scaffolds missing files without overwriting user data.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
import yaml

from gsigmad.bundled_skills import install_bundled_skills
from gsigmad.connectors import get_connector
from gsigmad.governance.versioning import bootstrap_coordination_state
from gsigmad.hub import best_effort_append_command_w5
from gsigmad.scaffold.templates import canon_template, default_config, lab_notebook_template
from gsigmad.scaffold.working_tree import scaffold_working_tree

# Current schema version -- bump when scaffold layout changes.
CURRENT_SCHEMA_VERSION = 3


def _load_schema_version(gsigmad_dir: Path) -> int:
    """Read schema_version from config.yaml, defaulting to 1 for pre-v1.7 projects."""
    config_path = gsigmad_dir / "config.yaml"
    if not config_path.is_file():
        return 1
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    sv = config.get("schema_version", 1)
    if not isinstance(sv, int) or sv < 1:
        raise typer.BadParameter(
            f"Invalid schema_version in config.yaml: {sv!r} (must be integer >= 1)"
        )
    return sv


def _update_schema_version(gsigmad_dir: Path, version: int) -> None:
    """Write schema_version into the existing config.yaml."""
    config_path = gsigmad_dir / "config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    config["schema_version"] = version
    config_path.write_text(
        yaml.safe_dump(config, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def init_project(
    ctx: typer.Context,
    path: Path = typer.Argument(
        Path("."),
        help="Project directory to initialize.",
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip interactive confirmation."
    ),
) -> None:
    """Initialize a gsigmad-governed science project."""
    target = path.resolve()
    gsigmad_dir = target / ".gsigmad"
    json_output = getattr(ctx.obj, "json_output", False) if ctx.obj else False

    # --- Path B: Upgrade existing project ---
    if gsigmad_dir.exists():
        sv = _load_schema_version(gsigmad_dir)

        # Already current
        if sv >= CURRENT_SCHEMA_VERSION:
            if json_output:
                print(json.dumps({"already_current": True, "schema_version": sv}))
            else:
                import rich

                rich.print(
                    f"[green]Already at current schema version[/green] ({sv})"
                )
            raise typer.Exit(code=0)

        # Prompt for confirmation in interactive mode
        interactive = sys.stdin.isatty() and not yes
        if interactive:
            confirm = typer.confirm(
                f"Upgrade schema {sv} -> {CURRENT_SCHEMA_VERSION}?"
            )
            if not confirm:
                raise typer.Exit(code=0)

        # Upgrade banner
        if json_output:
            pass  # JSON summary at end
        else:
            import rich

            rich.print(
                f"[yellow]Upgrading existing project[/yellow] (schema {sv} -> {CURRENT_SCHEMA_VERSION})"
            )

        # Idempotent scaffold + skill install
        scaffold_result = scaffold_working_tree(target)
        skill_install = install_bundled_skills(target, overwrite=True)

        # Update config
        _update_schema_version(gsigmad_dir, CURRENT_SCHEMA_VERSION)

        # Ledger entry
        best_effort_append_command_w5(
            target,
            command="init",
            action="upgrade_project",
            archive={
                "kind": "schema_upgrade",
                "from_version": sv,
                "to_version": CURRENT_SCHEMA_VERSION,
                "created": scaffold_result["created"],
                "skipped": scaffold_result["skipped"],
            },
            metadata={
                "schema_from": sv,
                "schema_to": CURRENT_SCHEMA_VERSION,
            },
        )

        if json_output:
            print(
                json.dumps(
                    {
                        "upgraded": True,
                        "schema_version": CURRENT_SCHEMA_VERSION,
                        "created": scaffold_result["created"],
                        "skipped": scaffold_result["skipped"],
                    }
                )
            )
        else:
            import rich

            rich.print(
                f"[green]Upgraded[/green] to schema version {CURRENT_SCHEMA_VERSION}"
            )
        return

    # --- Path A: Fresh init ---
    if json_output:
        pass  # JSON summary at end
    else:
        import rich

        rich.print("[cyan]Initializing new project[/cyan]")

    connector = get_connector(target)
    config = default_config()
    config["project_name"] = target.name
    connector.initialize(target, config)
    config_path = gsigmad_dir / "config.yaml"
    notebook_path = gsigmad_dir / "LAB_NOTEBOOK.md"
    coordination_file = bootstrap_coordination_state(target)

    # Write CANON.md in project root
    canon_path = target / "CANON.md"
    if not canon_path.exists():
        canon_path.write_text(canon_template())

    skill_install = install_bundled_skills(target)

    # Scaffold the full working tree (idempotent)
    scaffold_result = scaffold_working_tree(target)

    created = [
        str(gsigmad_dir),
        str(config_path),
        str(notebook_path),
        str(canon_path),
        str(coordination_file),
    ]
    created.extend(skill_install["installed"])
    created.extend(scaffold_result["created"])

    best_effort_append_command_w5(
        target,
        command="init",
        action="initialize_project",
        archive={
            "kind": "project_scaffold",
            "created": created,
            "skills_skipped": skill_install["skipped"],
        },
        metadata={
            "created_count": len(created),
            "skill_count": len(skill_install["installed"]),
        },
    )

    # Success output
    if json_output:
        print(
            json.dumps(
                {
                    "initialized": True,
                    "path": str(target),
                    "created": created,
                    "scaffold": scaffold_result,
                }
            )
        )
    else:
        import rich

        rich.print(f"[green]Initialized[/green] gsigmad project at {target}")
