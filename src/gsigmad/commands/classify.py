"""gsigmad classify command."""
from __future__ import annotations

import json
from pathlib import Path

import typer

from gsigmad.governance.gates.audit_claims import CI_PATTERN, EFFECT_SIZE_PATTERN, PVALUE_PATTERN
from gsigmad.hub import best_effort_append_command_w5


def _classify_text(text: str) -> tuple[str, str]:
    normalized = text.lower()
    if any(token in normalized for token in ("we hypothesize", "we predict", "may ", "might ", "could ", "expected to")):
        return "HYPOTHESIS", "future-looking or explicitly speculative language detected"
    if EFFECT_SIZE_PATTERN.search(text) or CI_PATTERN.search(text):
        return "MEASURED", "direct measured-result cues (effect size or confidence interval) detected"
    if PVALUE_PATTERN.search(text) or any(token in normalized for token in ("suggests", "indicates", "consistent with", "implies")):
        return "INFERRED", "interpretive or statistical-result language detected without direct measurement details"
    return "HYPOTHESIS", "insufficient direct evidence markers; defaulting conservatively to hypothesis"


def classify_claim(
    ctx: typer.Context,
    text: str = typer.Argument("", help="Claim text to classify."),
    file: Path | None = typer.Option(None, "--file", help="Read claim text from a file."),
) -> None:
    """Classify a claim as MEASURED, INFERRED, or HYPOTHESIS."""
    json_output = getattr(ctx.obj, "json_output", False) if ctx.obj else False

    claim_text = text
    if file is not None:
        claim_text = file.read_text(encoding="utf-8")

    if not claim_text.strip():
        msg = "Provide claim text as an argument or via --file."
        if json_output:
            print(json.dumps({"error": msg}))
        else:
            import rich

            rich.print(f"[red]Error:[/red] {msg}")
        raise typer.Exit(code=1)

    classification, rationale = _classify_text(claim_text)
    if json_output:
        print(json.dumps({"classification": classification, "rationale": rationale}))
    else:
        import rich

        rich.print(f"[green]{classification}[/green]")
        rich.print(rationale)

    best_effort_append_command_w5(
        Path.cwd(),
        command="classify",
        action="classify_claim_text",
        archive={"kind": "classification", "classification": classification},
        metadata={"classification": classification},
    )
