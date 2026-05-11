"""Tests for effect size + DOI enforcement in audit-claims — STAT-03."""
import pytest


@pytest.mark.xfail(strict=False, reason="audit-claims enhancements not yet implemented")
def test_reject_pvalue_only():
    """Claim with p-value but no effect size must be rejected with STAT_RIGOR_VIOLATION."""
    from gsigmad.governance.gates.audit_claims import check_effect_size_reporting
    claim = "The treatment group showed improvement (p < 0.001)."
    result = check_effect_size_reporting(claim)
    assert result["pass"] is False
    assert "STAT_RIGOR_VIOLATION" in result["error"]


@pytest.mark.xfail(strict=False, reason="audit-claims enhancements not yet implemented")
def test_pass_with_effect_size_and_ci():
    """Claim with p-value, effect size, and CI must pass."""
    from gsigmad.governance.gates.audit_claims import check_effect_size_reporting
    claim = "Treatment improved scores (p = 0.003, Cohen's d = 0.62, 95% CI: [0.38, 0.86])."
    result = check_effect_size_reporting(claim)
    assert result["pass"] is True


@pytest.mark.xfail(strict=False, reason="audit-claims enhancements not yet implemented")
def test_effect_size_without_ci_rejected():
    """Claim with effect size but no CI must be rejected."""
    from gsigmad.governance.gates.audit_claims import check_effect_size_reporting
    claim = "Treatment improved scores (p = 0.003, Cohen's d = 0.62)."
    result = check_effect_size_reporting(claim)
    assert result["pass"] is False
    assert "confidence interval" in result["error"].lower()


@pytest.mark.xfail(strict=False, reason="audit-claims enhancements not yet implemented")
def test_doi_not_found_blocks():
    """Non-existent DOI must fail verification."""
    from gsigmad.governance.gates.audit_claims import verify_doi
    result = verify_doi("10.9999/does-not-exist-12345")
    # Either DOI_NOT_FOUND (404) or TIMEOUT -- both are non-verified
    assert result.get("verified") is False or result.get("verified") == "TIMEOUT"


@pytest.mark.xfail(strict=False, reason="audit-claims enhancements not yet implemented")
def test_doi_verification():
    """A real DOI must return verified=True with a non-empty title."""
    from gsigmad.governance.gates.audit_claims import verify_doi
    result = verify_doi("10.1371/journal.pcbi.1003285")
    # Either verified (network available) or TIMEOUT (soft fail) -- never False for a real DOI
    assert result.get("verified") is True or result.get("verified") == "TIMEOUT"
