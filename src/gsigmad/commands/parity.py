"""Operator-facing parity command surface."""
from __future__ import annotations

import json
from pathlib import Path

import typer

from gsigmad.governance.parity import (
    DEFAULT_LOCAL_MODEL,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_SCENARIO,
    TRUST_HANDOFF_ARTIFACT_ROOT,
    TRUST_HANDOFF_SCENARIO,
    run_parity,
)

parity_app = typer.Typer(help="Cross-model parity harness for bounded governance smoke checks.")


def _json_mode(ctx: typer.Context) -> bool:
    return getattr(ctx.obj, "json_output", False) if ctx.obj else False


@parity_app.command("run")
def run_parity_command(
    ctx: typer.Context,
    scenario: str = typer.Option(
        DEFAULT_SCENARIO,
        "--scenario",
        help="Parity scenario. Use 'trust-handoff' for PROVISIONAL intake, countersigned promotion, and handoff metadata validation.",
    ),
    lanes: str = typer.Option(
        "claude,codex,ollama",
        "--lanes",
        help="Comma-separated lane names to execute.",
    ),
    local_model: str = typer.Option(
        DEFAULT_LOCAL_MODEL,
        "--local-model",
        help="Pinned local model identifier for the Ollama lane.",
    ),
    native: str = typer.Option(
        "self_fixture",
        "--native",
        help="Native fixture source. Defaults to a disposable copy of the current repo.",
    ),
    routed: str = typer.Option(
        "shadow_seeds_fixture",
        "--routed",
        help="Routed fixture source. Defaults to the authoritative shadow-seeds manifest.",
    ),
    artifact_root: Path | None = typer.Option(
        None,
        "--artifact-root",
        help="Repo-local artifact directory for parity reports and sanitized raw outputs.",
    ),
    timeout_seconds: int = typer.Option(
        DEFAULT_TIMEOUT_SECONDS,
        "--timeout-seconds",
        min=10,
        help="Per-preflight and per-command timeout in seconds.",
    ),
    replay_lanes: str = typer.Option(
        "",
        "--replay-lanes",
        help="Comma-separated lane names to replay from fixtures instead of live execution.",
    ),
) -> None:
    """Run one bounded parity scenario and persist a durable report."""
    resolved_artifact_root = artifact_root
    if resolved_artifact_root is None and scenario == TRUST_HANDOFF_SCENARIO:
        resolved_artifact_root = TRUST_HANDOFF_ARTIFACT_ROOT

    parsed_replay_lanes: set[str] | None = None
    if replay_lanes.strip():
        parsed_replay_lanes = {item.strip() for item in replay_lanes.split(",") if item.strip()}

    report = run_parity(
        repo_root=Path.cwd(),
        lanes=[item.strip() for item in lanes.split(",") if item.strip()],
        local_model=local_model,
        native=native,
        routed=routed,
        scenario=scenario,
        artifact_root=resolved_artifact_root,
        timeout_seconds=timeout_seconds,
        replay_lanes=parsed_replay_lanes,
    )
    if _json_mode(ctx):
        print(json.dumps(report, indent=2, sort_keys=True))
        return

    import rich

    report_root = Path(resolved_artifact_root or Path(".artifacts") / "parity").resolve()
    rich.print(f"Parity report: {report_root / 'latest.json'}")
    rich.print(f"Scenario: {report['scenario']}")
    rich.print(f"Lanes: {', '.join(report['lanes'])}")
    rich.print(f"Degraded lanes: {', '.join(report['degraded_lanes']) or 'none'}")
    rich.print(f"Mismatches: {len(report['mismatches'])}")
