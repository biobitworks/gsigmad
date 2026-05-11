"""Tests for mandatory red team gate for CONFIRMATORY experiments — GOV-03."""
import pytest


@pytest.mark.xfail(strict=False, reason="red team gate not yet implemented")
def test_confirmatory_blocked(sample_exp_record):
    """CONFIRMATORY experiment with red_team_status != PASS must be blocked."""
    from gsigmad.governance.gates.red_team import check_red_team_gate
    prompt_fields = {
        "risk_tier": "P1",
        "red_team_status": "PENDING",
        "remediation_constraints": [],
        "execution_decision": "GO",
    }
    result = check_red_team_gate(
        classification="CONFIRMATORY",
        prompt_fields=prompt_fields
    )
    assert result["pass"] is False
    assert "RED TEAM GATE FAILED" in result["error"]


@pytest.mark.xfail(strict=False, reason="red team gate not yet implemented")
def test_confirmatory_passes_with_complete_red_team(sample_exp_record):
    """CONFIRMATORY experiment with complete red team must pass."""
    from gsigmad.governance.gates.red_team import check_red_team_gate
    prompt_fields = {
        "risk_tier": "P1",
        "red_team_status": "PASS",
        "remediation_constraints": ["Use independent validation set only"],
        "execution_decision": "GO",
    }
    result = check_red_team_gate(
        classification="CONFIRMATORY",
        prompt_fields=prompt_fields
    )
    assert result["pass"] is True


@pytest.mark.xfail(strict=False, reason="red team gate not yet implemented")
def test_exploratory_not_blocked():
    """EXPLORATORY experiments must NOT be blocked by red team gate (recommended but not required)."""
    from gsigmad.governance.gates.red_team import check_red_team_gate
    result = check_red_team_gate(
        classification="EXPLORATORY",
        prompt_fields={}
    )
    assert result["pass"] is True
    assert "not required for EXPLORATORY" in result.get("log", "")


# -- Plan 02: challenge_target field support --

def test_challenge_target_accepted_in_prompt_fields():
    """prompt_fields with challenge_target='fdr_chain.method' passes red team gate normally."""
    from gsigmad.governance.gates.red_team import check_red_team_gate

    prompt_fields = {
        "risk_tier": "P1",
        "red_team_status": "PASS",
        "remediation_constraints": ["Use independent validation set only"],
        "execution_decision": "GO",
        "challenge_target": "fdr_chain.method",
    }
    result = check_red_team_gate(
        classification="CONFIRMATORY",
        prompt_fields=prompt_fields,
    )
    assert result["pass"] is True


def test_challenge_target_field_not_in_required():
    """challenge_target is NOT in the _REQUIRED_CONFIRMATORY_FIELDS list (metadata only)."""
    from gsigmad.governance.gates.red_team import _REQUIRED_CONFIRMATORY_FIELDS

    assert "challenge_target" not in _REQUIRED_CONFIRMATORY_FIELDS
