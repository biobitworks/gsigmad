"""gsigmad power command -- standalone power analysis calculator.

Computes required sample size and achieved power for experiment design.
Does NOT require .gsigmad/ initialization -- works as a standalone calculator.
Uses lazy import for power_analysis module to avoid heavy statsmodels load at startup.
"""
from __future__ import annotations

import json

import typer


_SUPPORTED_TESTS = [
    "ttest_ind",
    "ttest_paired",
    "anova",
    "chi2",
    "correlation",
    "proportion",
]


def power_analysis(
    ctx: typer.Context,
    test_type: str = typer.Option(
        ...,
        "--test",
        "-t",
        help="Statistical test type: ttest_ind, ttest_paired, anova, chi2, correlation, proportion",
    ),
    effect_size: float = typer.Option(
        ...,
        "--effect-size",
        "-e",
        help="Standardized effect size (Cohen's d, f, w, or r)",
    ),
    alpha: float = typer.Option(
        0.05,
        "--alpha",
        "-a",
        help="Type I error rate",
    ),
    power_target: float = typer.Option(
        0.80,
        "--power",
        "-p",
        help="Target statistical power",
    ),
    n_groups: int = typer.Option(
        2,
        "--n-groups",
        "-g",
        help="Number of groups (ANOVA)",
    ),
    alternative: str = typer.Option(
        "two-sided",
        "--alternative",
        help="Alternative hypothesis: two-sided, larger, smaller",
    ),
) -> None:
    """Compute power analysis for experiment design (standalone calculator)."""
    json_output = getattr(ctx.obj, "json_output", False) if ctx.obj else False

    # Lazy import to avoid loading statsmodels at CLI startup
    from gsigmad.governance.gates.power_analysis import compute_power_tier1

    result = compute_power_tier1(
        test_type=test_type,
        effect_size=effect_size,
        alpha=alpha,
        power_target=power_target,
        n_groups=n_groups,
        alternative=alternative,
    )

    # Check for error (unsupported test type, computation error)
    if result.get("pass") is False or "error" in result:
        if json_output:
            print(json.dumps(result))
        else:
            import rich

            rich.print(f"[red]Error:[/red] {result.get('error', 'Unknown error')}")
        raise typer.Exit(code=1)

    # JSON output mode
    if json_output:
        print(json.dumps(result))
        return

    # Rich output mode
    import rich
    from rich.panel import Panel
    from rich.table import Table

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Field", style="dim")
    table.add_column("Value", style="bold")

    table.add_row("Test type", result.get("test_type", test_type))
    table.add_row("Effect size", str(result.get("effect_size", effect_size)))
    table.add_row("Alpha", str(result.get("alpha", alpha)))
    table.add_row("Target power", str(power_target))
    table.add_row("Required N", f"[green]{result.get('required_n', '?')}[/green]")
    table.add_row("Achieved power", str(result.get("achieved_power", "?")))
    table.add_row("Tier", result.get("tier", "formula"))

    rich.print(Panel(table, title="Power Analysis"))
