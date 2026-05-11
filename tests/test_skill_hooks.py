"""Tests for deterministic governance trigger hooks."""
from gsigmad.governance.skill_hooks import required_governance_actions


def test_required_governance_actions_for_register() -> None:
    result = required_governance_actions("register")
    assert result["requires_project"] is True
    assert "allocate_exp_id" in result["actions"]
    assert result["closure_stage"] == "EXP"


def test_required_governance_actions_normalizes_aliases() -> None:
    result = required_governance_actions("rt")
    assert result["name"] == "redteam"
    assert result["closure_stage"] == "RT"


def test_required_governance_actions_for_skill_name() -> None:
    result = required_governance_actions("session_pause")
    assert result["name"] == "session-pause"
    assert "write_checkpoint" in result["actions"]


def test_required_governance_actions_unknown_command() -> None:
    result = required_governance_actions("totally-unknown")
    assert result["actions"] == []
    assert result["requires_project"] is False
