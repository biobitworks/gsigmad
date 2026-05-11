"""Advisory pre-plan review command."""
from __future__ import annotations

import json
from pathlib import Path

import typer

from gsigmad.governance.review import (
    ComparisonPrompt,
    ReferencePackInput,
    ReviewRequest,
    run_review,
    write_review_artifacts,
)


def review_project(
    ctx: typer.Context,
    reference: list[str] = typer.Option(
        None,
        "--reference",
        help="Role-scoped reference pack in role=PATH form. Repeat to add more packs.",
    ),
    comparison: list[str] = typer.Option(
        None,
        "--comparison",
        help="Comparison prompt to include in the advisory review. Repeat to add more prompts.",
    ),
    comparison_role: list[str] = typer.Option(
        None,
        "--comparison-role",
        help="Comma-separated reference roles for the matching comparison prompt.",
    ),
) -> None:
    """Run advisory governance review before any PLAN.md exists."""
    subject_repo = Path.cwd()
    references = [_parse_reference_item(item) for item in (reference or [])]
    comparisons = _build_comparisons(comparison or [], comparison_role or [])
    review = run_review(
        ReviewRequest(
            subject_repo=subject_repo,
            references=references,
            comparisons=comparisons,
        )
    )
    output_dir = subject_repo / ".planning" / "reviews"
    json_path, markdown_path = write_review_artifacts(review, output_dir)

    json_output = getattr(ctx.obj, "json_output", False) if ctx.obj else False
    if json_output:
        payload = review.model_dump(mode="json")
        payload["artifact_paths"] = {
            "json": str(json_path),
            "markdown": str(markdown_path),
        }
        print(json.dumps(payload, indent=2))
        raise typer.Exit(code=0)

    import rich

    rich.print("[bold]Pre-plan review[/bold]")
    rich.print(f"Status: {review.status}")
    rich.print(f"Findings: {len(review.findings)}")
    rich.print(f"JSON: {json_path}")
    rich.print(f"Markdown: {markdown_path}")
    if review.findings:
        rich.print("[yellow]Advisory findings surfaced; command remains non-blocking.[/yellow]")
        for finding in review.findings[:5]:
            rich.print(f"- [{finding.code}] {finding.message}")
    else:
        rich.print("[green]No advisory findings surfaced.[/green]")
    raise typer.Exit(code=0)


def _parse_reference_item(raw: str) -> ReferencePackInput:
    if "=" not in raw:
        raise typer.BadParameter("Reference must use role=PATH syntax.")
    role, raw_path = raw.split("=", 1)
    role = role.strip()
    raw_path = raw_path.strip()
    if not role or not raw_path:
        raise typer.BadParameter("Reference must include both role and path.")
    return ReferencePackInput(role=role, path=Path(raw_path))


def _build_comparisons(prompts: list[str], role_specs: list[str]) -> list[ComparisonPrompt]:
    if len(role_specs) > len(prompts):
        raise typer.BadParameter("Received more --comparison-role values than --comparison prompts.")
    comparisons: list[ComparisonPrompt] = []
    for index, prompt in enumerate(prompts):
        roles: list[str] = []
        if index < len(role_specs):
            roles = [part.strip() for part in role_specs[index].split(",") if part.strip()]
        comparisons.append(ComparisonPrompt(prompt=prompt, reference_roles=roles))
    return comparisons
