"""
Tests for three-tier power analysis gate (STAT-01).

TDD: These tests are written first to define the required interface.
"""
import pytest


def test_ttest_power():
    """compute_power_tier1 for ttest_ind returns required_n >= 1 and tier == formula."""
    from gsigmad.governance.gates.power_analysis import compute_power_tier1
    result = compute_power_tier1("ttest_ind", effect_size=0.4, alpha=0.05, power_target=0.80)
    assert result["required_n"] >= 1
    assert result["tier"] == "formula"
    assert result["achieved_power"] >= 0.79


def test_anova_power():
    """compute_power_tier1 for anova returns required_n >= 1."""
    from gsigmad.governance.gates.power_analysis import compute_power_tier1
    result = compute_power_tier1("anova", effect_size=0.25, alpha=0.05, power_target=0.80, n_groups=3)
    assert result["required_n"] >= 1
    assert result["tier"] == "formula"


def test_chi2_power():
    """compute_power_tier1 for chi2 returns required_n >= 1."""
    from gsigmad.governance.gates.power_analysis import compute_power_tier1
    result = compute_power_tier1("chi2", effect_size=0.3, alpha=0.05, power_target=0.80)
    assert result["required_n"] >= 1
    assert result["tier"] == "formula"


def test_correlation_power():
    """compute_power_tier1 for correlation returns required_n >= 1."""
    from gsigmad.governance.gates.power_analysis import compute_power_tier1
    result = compute_power_tier1("correlation", effect_size=0.3, alpha=0.05, power_target=0.80)
    assert result["required_n"] >= 1
    assert result["tier"] == "formula"


def test_proportion_power():
    """compute_power_tier1 for proportion returns required_n >= 1."""
    from gsigmad.governance.gates.power_analysis import compute_power_tier1
    result = compute_power_tier1("proportion", effect_size=0.3, alpha=0.05, power_target=0.80)
    assert result["required_n"] >= 1
    assert result["tier"] == "formula"


def test_missing_package_returns_actionable_error():
    """compute_power with tier=2 when pymc not installed returns actionable error (not ImportError)."""
    from gsigmad.governance.gates.power_analysis import compute_power
    # Tier 2 requires pymc — either passes if installed or returns structured error
    result = compute_power(tier=2, test_type="ttest_ind", effect_size=0.4)
    # Should not raise an exception — must return dict
    assert isinstance(result, dict)
    # Result must contain either 'pass' (error case) or 'tier' (success case)
    assert "pass" in result or "tier" in result
    # If it's an error response, must mention either UNAVAILABLE (pymc missing) or NOT_IMPLEMENTED (pymc present but no impl)
    if "pass" in result and result["pass"] is False:
        error_msg = result.get("error", "")
        assert "POWER_ANALYSIS_TIER2_UNAVAILABLE" in error_msg or "POWER_ANALYSIS_TIER2_NOT_IMPLEMENTED" in error_msg


def test_power_block_on_missing_block():
    """check_power_analysis_gate fails when power_analysis block is absent."""
    from gsigmad.governance.gates.power_analysis import check_power_analysis_gate
    exp_record = {"exp_id": "EXP-001", "hypothesis": "test hypothesis"}
    result = check_power_analysis_gate(exp_record)
    assert result["pass"] is False
    assert "power_analysis" in result["error"].lower()


def test_power_gate_passes_with_complete_block():
    """check_power_analysis_gate passes with a complete power_analysis block."""
    from gsigmad.governance.gates.power_analysis import check_power_analysis_gate
    exp_record = {
        "exp_id": "EXP-001",
        "power_analysis": {
            "tier": "formula",
            "test_type": "ttest_ind",
            "required_n": 186,
            "effect_size_mesi": 0.4,
            "alpha": 0.05,
            "achieved_power": 0.80,
        }
    }
    result = check_power_analysis_gate(exp_record)
    assert result["pass"] is True
    assert result["error"] is None


def test_power_gate_fails_on_incomplete_block():
    """check_power_analysis_gate fails when power_analysis block is missing required fields."""
    from gsigmad.governance.gates.power_analysis import check_power_analysis_gate
    exp_record = {
        "exp_id": "EXP-001",
        "power_analysis": {
            "tier": "formula",
            # missing: test_type, required_n, effect_size_mesi, alpha, achieved_power
        }
    }
    result = check_power_analysis_gate(exp_record)
    assert result["pass"] is False


def test_survival_power():
    """compute_power_tier1 for survival handles the test type (lifelines may not be installed)."""
    from gsigmad.governance.gates.power_analysis import compute_power_tier1
    result = compute_power_tier1("survival", effect_size=0.3, alpha=0.05, power_target=0.80)
    # Either returns required_n (lifelines available) or structured error (not available)
    assert isinstance(result, dict)
    assert "required_n" in result or ("pass" in result and result["pass"] is False)
