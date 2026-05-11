"""gsigmad export command."""
from __future__ import annotations

import json
from pathlib import Path

import typer

from gsigmad.hub import best_effort_append_command_w5


def export_bundle(
    ctx: typer.Context,
    exp_id: str = typer.Argument(..., help="Experiment ID (e.g., EXP-1.1)"),
    target: str = typer.Option("", "--target", help="Optional upload target: osf or zenodo."),
) -> None:
    """Create an export bundle and optionally upload/deposit it."""
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

    from gsigmad.governance.export.exporter import create_bundle

    bundle_path, manifest = create_bundle(exp_id=exp_id, gsd_root=str(cwd))
    upload_result: dict | None = None
    target = target.strip().lower()
    if target == "osf":
        from gsigmad.governance.export.osf_client import upload_to_osf

        upload_result = upload_to_osf(bundle_path)
    elif target == "zenodo":
        from gsigmad.governance.export.zenodo_client import deposit_to_zenodo

        upload_result = deposit_to_zenodo(bundle_path)
    elif target:
        msg = f"Unknown export target '{target}'. Use osf or zenodo."
        if json_output:
            print(json.dumps({"error": msg}))
        else:
            import rich

            rich.print(f"[red]Error:[/red] {msg}")
        raise typer.Exit(code=1)

    payload = {"bundle_path": bundle_path, "manifest": manifest, "upload": upload_result}
    if json_output:
        print(json.dumps(payload, default=str))
    else:
        import rich

        rich.print(f"[green]Bundle created[/green] {bundle_path}")
        rich.print(f"Artifacts: {len(manifest.get('artifacts', []))}")
        if upload_result:
            if upload_result.get("pass"):
                rich.print(f"[green]Upload complete[/green] {upload_result}")
            else:
                rich.print(f"[red]Upload failed[/red] {upload_result.get('error')}")

    if upload_result and not upload_result.get("pass"):
        raise typer.Exit(code=1)

    best_effort_append_command_w5(
        cwd,
        command="export",
        action="create_export_bundle" if not target else f"export_to_{target}",
        exp_id=exp_id,
        archive={"kind": "export_bundle", "bundle_path": bundle_path, "target": target or None},
        metadata={"artifact_count": len(manifest.get("artifacts", []))},
    )
