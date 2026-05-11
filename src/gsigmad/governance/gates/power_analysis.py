"""
Three-tier power analysis gate — STAT-01.

Tier 1: Formula-based (statsmodels) — t-tests, ANOVA, chi-square, proportions, correlation
Tier 2: Simulation-based (PyMC + arviz) — hierarchical designs, mixed effects, survival
Tier 3: Custom plugin — domain-specific power functions

Reference: CANON-CORE Invariant 5 (pre-registration), EXPERIMENT_STANDARDS.md §2, D-05/D-06/D-07
"""
import math
from typing import Any, Optional

# -- TRAITS pillar mapping (REP-02) --

TRAITS_PILLARS: dict[str, list[str]] = {
    "power_analysis": ["Rigorous"],
}

# Tier 2 availability guard (D-05, Pitfall 3)
try:
    import pymc as pm
    import arviz as az
    PYMC_AVAILABLE = True
except ImportError:
    PYMC_AVAILABLE = False

# Tier 1 imports (verified installed: statsmodels 0.14.5)
from statsmodels.stats.power import (
    TTestIndPower,
    TTestPower,
    FTestAnovaPower,
    GofChisquarePower,
    NormalIndPower,
)

# Survival analysis (lifelines)
try:
    from lifelines.statistics import logrank_test
    LIFELINES_AVAILABLE = True
except ImportError:
    LIFELINES_AVAILABLE = False


# ─── Tier 1: Formula-based ───────────────────────────────────────────────────

def compute_power_tier1(
    test_type: str,
    effect_size: float,
    alpha: float = 0.05,
    power_target: float = 0.80,
    n_groups: int = 2,
    alternative: str = "two-sided",
) -> dict:
    """
    Compute required N using statsmodels formula-based power analysis.

    Args:
        test_type: One of: 'ttest_ind', 'ttest_paired', 'anova', 'chi2',
                   'correlation', 'proportion', 'survival'
        effect_size: Standardized effect size (Cohen's d for t-tests,
                     Cohen's f for ANOVA, w for chi2/proportions, r for correlation)
        alpha: Type I error rate (default 0.05)
        power_target: Target power (default 0.80)
        n_groups: Number of groups for ANOVA (default 2)
        alternative: 'two-sided', 'larger', or 'smaller' (default 'two-sided')

    Returns:
        {"tier": "formula", "test_type": str, "required_n": int,
         "effect_size": float, "alpha": float, "achieved_power": float}
    """
    required_n: Optional[float] = None

    if test_type == "ttest_ind":
        analysis = TTestIndPower()
        required_n = analysis.solve_power(
            effect_size=effect_size,
            alpha=alpha,
            power=power_target,
            ratio=1.0,
            alternative=alternative,
        )

    elif test_type == "ttest_paired":
        analysis = TTestPower()
        required_n = analysis.solve_power(
            effect_size=effect_size,
            alpha=alpha,
            power=power_target,
            alternative=alternative,
        )

    elif test_type == "anova":
        analysis = FTestAnovaPower()
        required_n = analysis.solve_power(
            effect_size=effect_size,
            alpha=alpha,
            power=power_target,
            k_groups=n_groups,
        )

    elif test_type == "chi2":
        analysis = GofChisquarePower()
        required_n = analysis.solve_power(
            effect_size=effect_size,
            alpha=alpha,
            power=power_target,
            n_bins=n_groups if n_groups > 2 else 2,
        )

    elif test_type == "correlation":
        analysis = NormalIndPower()
        required_n = analysis.solve_power(
            effect_size=effect_size,
            alpha=alpha,
            power=power_target,
            alternative=alternative,
        )

    elif test_type == "proportion":
        # For proportion tests, effect_size is Cohen's h
        analysis = NormalIndPower()
        required_n = analysis.solve_power(
            effect_size=effect_size,
            alpha=alpha,
            power=power_target,
            alternative=alternative,
        )

    elif test_type == "survival":
        if not LIFELINES_AVAILABLE:
            # Fallback: use NormalIndPower approximation when lifelines is unavailable
            # This is a common approximation for log-rank test power
            analysis = NormalIndPower()
            required_n = analysis.solve_power(
                effect_size=effect_size,
                alpha=alpha,
                power=power_target,
            )
        else:
            # With lifelines available, use NormalIndPower as approximation
            # (lifelines' logrank_test is for post-hoc testing, not sample size calculation)
            analysis = NormalIndPower()
            required_n = analysis.solve_power(
                effect_size=effect_size,
                alpha=alpha,
                power=power_target,
            )

    else:
        return {
            "pass": False,
            "error": (
                f"POWER_ANALYSIS_UNSUPPORTED_TEST: test_type '{test_type}' is not supported "
                f"in Tier 1 formula-based power analysis. "
                f"Supported: ttest_ind, ttest_paired, anova, chi2, correlation, proportion, survival. "
                f"For custom tests, use Tier 3 (plugin interface)."
            ),
        }

    # ceil to whole number of subjects
    n_int = math.ceil(required_n)

    return {
        "tier": "formula",
        "test_type": test_type,
        "required_n": n_int,
        "effect_size": effect_size,
        "alpha": alpha,
        "achieved_power": power_target,
    }


# ─── Tier 2: Simulation-based ────────────────────────────────────────────────

def compute_power_tier2(
    generative_model_fn: Any = None,
    n_simulations: int = 1000,
    power_target: float = 0.80,
    **model_kwargs: Any,
) -> dict:
    """
    Compute power via PyMC simulation (Monte Carlo).

    Args:
        generative_model_fn: Callable that returns a PyMC model. Signature:
                             fn(n_per_group: int, **model_kwargs) -> pm.Model
        n_simulations: Number of Monte Carlo simulations (default 1000)
        power_target: Target power (default 0.80)
        **model_kwargs: Passed to generative_model_fn

    Returns:
        {"tier": "simulation", "required_n": int, "power_curve": list, ...}
        OR {"pass": False, "error": "POWER_ANALYSIS_TIER2_UNAVAILABLE: ..."}
    """
    if not PYMC_AVAILABLE:
        return {
            "pass": False,
            "error": (
                "POWER_ANALYSIS_TIER2_UNAVAILABLE: PyMC not installed. "
                "Install with: pip install pymc arviz. "
                "Alternatively, use tier=1 (formula-based) if the design supports it."
            ),
        }

    # Simulation implementation deferred — PyMC simulation is complex and
    # domain-specific. The gate script documents the interface and graceful
    # fallback. Full simulation implementation is added per-project in Phase 5.
    return {
        "pass": False,
        "error": (
            "POWER_ANALYSIS_TIER2_NOT_IMPLEMENTED: PyMC is installed but Tier 2 simulation "
            "implementation is domain-specific. Use Tier 3 (custom plugin) with a domain-specific "
            "generative model, or use Tier 1 (formula-based) if the design is standard enough. "
            "See gsigmad.governance.gates.power_analysis:compute_power_tier2 for the implementation contract."
        ),
    }


# ─── Tier 3: Custom plugin ───────────────────────────────────────────────────

def compute_power_tier3(plugin_path: str, plugin_params: dict) -> dict:
    """
    Invoke a domain-specific power analysis plugin.

    Args:
        plugin_path: Importable Python module path. Module must export:
                     power_analysis(params: dict) -> dict
                     where dict contains at minimum: required_n, achieved_power
        plugin_params: Parameters passed to the plugin.

    Returns:
        Plugin's return dict, validated to contain required_n and achieved_power.
        OR {"pass": False, "error": "..."} on failure.
    """
    import importlib
    try:
        module = importlib.import_module(plugin_path)
    except ImportError as e:
        return {
            "pass": False,
            "error": (
                f"POWER_ANALYSIS_PLUGIN_NOT_FOUND: Cannot import plugin '{plugin_path}'. "
                f"Error: {e}. "
                "Ensure the plugin module is on sys.path and exports power_analysis(params: dict) -> dict."
            ),
        }

    if not hasattr(module, "power_analysis"):
        return {
            "pass": False,
            "error": (
                f"POWER_ANALYSIS_PLUGIN_INVALID: Plugin '{plugin_path}' does not export "
                "'power_analysis' function. "
                "Required signature: power_analysis(params: dict) -> dict with required_n, achieved_power."
            ),
        }

    result = module.power_analysis(plugin_params)

    # Validate required output fields
    if "required_n" not in result or "achieved_power" not in result:
        return {
            "pass": False,
            "error": (
                f"POWER_ANALYSIS_PLUGIN_INVALID_OUTPUT: Plugin '{plugin_path}' did not return "
                "required keys: required_n, achieved_power. "
                f"Got: {list(result.keys())}"
            ),
        }

    result["tier"] = "plugin"
    result["plugin"] = plugin_path
    return result


# ─── Unified entry point ─────────────────────────────────────────────────────

def compute_power(tier: int, test_type: str, effect_size: float, **kwargs: Any) -> dict:
    """
    Unified power computation entry point. Dispatches to the appropriate tier.

    Args:
        tier: 1 (formula), 2 (simulation), or 3 (plugin)
        test_type: Test type string (passed to tier 1/2) or plugin path (tier 3)
        effect_size: Standardized effect size

    Returns:
        Power analysis result dict or error dict.
    """
    if tier == 1:
        return compute_power_tier1(test_type=test_type, effect_size=effect_size, **kwargs)
    elif tier == 2:
        return compute_power_tier2(**kwargs)
    elif tier == 3:
        return compute_power_tier3(plugin_path=test_type, plugin_params=kwargs)
    else:
        return {
            "pass": False,
            "error": f"POWER_ANALYSIS_INVALID_TIER: tier must be 1, 2, or 3. Got: {tier}",
        }


# ─── Pre-flight gate check ───────────────────────────────────────────────────

_REQUIRED_POWER_FIELDS = {"tier", "test_type", "required_n", "effect_size_mesi", "alpha", "achieved_power"}


def check_power_analysis_gate(exp_record: dict) -> dict:
    """
    Verify that an EXP pre-registration record has a complete power_analysis block.
    Blocks execution if power_analysis block is absent or incomplete.

    Args:
        exp_record: The EXP pre-registration dict (loaded from YAML).

    Returns:
        {"pass": bool, "error": Optional[str]}
    """
    if "power_analysis" not in exp_record:
        return {
            "pass": False,
            "error": (
                "POWER_ANALYSIS_GATE_FAILED: EXP record is missing required 'power_analysis' block. "
                "CONFIRMATORY experiments must include a power analysis before execution. "
                "Add a 'power_analysis:' block to the EXP pre-registration YAML with: "
                "tier, test_type, required_n, effect_size_mesi, alpha, achieved_power, "
                "computed_at, tool_version. "
                "Reference: EXPERIMENT_STANDARDS.md §2, STAT-01."
            ),
        }

    pa = exp_record["power_analysis"]
    missing_fields = _REQUIRED_POWER_FIELDS - set(pa.keys())
    if missing_fields:
        return {
            "pass": False,
            "error": (
                f"POWER_ANALYSIS_GATE_FAILED: power_analysis block is incomplete. "
                f"Missing required fields: {sorted(missing_fields)}. "
                "Required fields: tier, test_type, required_n, effect_size_mesi, alpha, achieved_power."
            ),
        }

    # Sanity check: required_n must be positive integer
    required_n = pa.get("required_n")
    if not isinstance(required_n, (int, float)) or required_n < 1:
        return {
            "pass": False,
            "error": (
                f"POWER_ANALYSIS_GATE_FAILED: required_n is '{required_n}' — must be a positive integer >= 1. "
                "Re-run power analysis to get a valid sample size."
            ),
        }

    return {"pass": True, "error": None}
