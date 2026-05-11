"""gsigmad CLI -- Science governance CLI."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer

from gsigmad import __version__
from gsigmad.commands import (
    audit,
    classify,
    drift,
    export_cmd,
    inspect_cmd,
    fair,
    init_cmd,
    kg,
    monitor,
    parity,
    pause,
    power,
    redteam,
    register,
    recover,
    review,
    resume,
    report,
    run,
    scaffold,
    serve_cmd,
    status,
)
from gsigmad.governance.degradation import compute_degradation_state, emit_degraded_banner, write_degradation_state
from gsigmad.governance.versioning import resolve_coordinate

app = typer.Typer(
    name="gsigmad",
    help="Science governance CLI -- deterministic guardrails for probabilistic AI",
    no_args_is_help=True,
)


@dataclass
class AppState:
    """Global CLI state passed via typer context."""

    json_output: bool = False
    degradation_state: dict[str, Any] | None = None


def _version_callback(value: bool) -> None:
    """Print version and exit when --version flag is passed."""
    if value:
        import rich

        rich.print(f"gsigmad {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output JSON instead of formatted text.",
    ),
) -> None:
    """Science governance CLI -- deterministic guardrails for probabilistic AI."""
    ctx.ensure_object(dict)
    state = AppState(json_output=json_output)
    project_root = Path.cwd()
    if (project_root / ".gsigmad").is_dir():
        try:
            degradation_state = compute_degradation_state(project_root)
            state.degradation_state = degradation_state
            if not (
                ctx.invoked_subcommand == "recover"
                and ctx.args
                and ctx.args[0] == "diagnose"
            ):
                write_degradation_state(project_root, degradation_state)
            emit_degraded_banner(degradation_state, json_output=json_output)
        except Exception:
            state.degradation_state = None
    ctx.obj = state


@app.command()
def version() -> None:
    """Display package version and coordinate version."""
    import rich

    rich.print(f"gsigmad {__version__}")
    coordinate = resolve_coordinate(Path.cwd())
    if coordinate is None:
        rich.print("coordinate: unavailable (not in gsigmad project)")
    else:
        rich.print(f"coordinate: {coordinate}")


# Register commands from submodules
app.command(name="init")(init_cmd.init_project)
app.command(name="register")(register.register_experiment)
app.command(name="scaffold")(scaffold.scaffold_experiment)
app.command(name="run")(run.run_experiment)
app.command(name="audit")(audit.audit_experiment)
app.add_typer(recover.recover_app, name="recover")
app.command(name="review")(review.review_project)
app.command(name="power")(power.power_analysis)
app.command(name="status")(status.show_status)
app.command(name="inspect")(inspect_cmd.inspect_project)
app.command(name="pause")(pause.pause_session)
app.command(name="resume")(resume.resume_session)
app.command(name="redteam")(redteam.redteam_experiment)
app.command(name="classify")(classify.classify_claim)
app.command(name="drift")(drift.scan_drift)
app.command(name="fair")(fair.fair_check)
app.command(name="export")(export_cmd.export_bundle)
app.add_typer(kg.kg_app, name="kg")
app.add_typer(monitor.monitor_app, name="monitor")
app.add_typer(parity.parity_app, name="parity")
app.add_typer(report.report_app, name="report")
app.command(name="serve")(serve_cmd.serve)

# Short aliases
app.command(name="a")(audit.audit_experiment)
app.command(name="r")(run.run_experiment)
app.command(name="s")(status.show_status)
app.command(name="rt")(redteam.redteam_experiment)
app.add_typer(report.report_app, name="rr")
