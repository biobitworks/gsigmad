"""Tests for the Phase 35 repo adoption and certification contract."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from gsigmad.governance.repo_adoption_contract import (
    RepoAdoptionProfile,
    RepoFindingSeverity,
    RepoReadinessState,
    certify_repo_adoption,
)


def test_repo_adoption_profile_keeps_repo_classes_closed() -> None:
    profile = RepoAdoptionProfile.model_validate(
        {
            "repo_name": "gettingsciencedone",
            "repo_class": "active",
            "runtime_mode": "gsigmad",
            "namespace_prefix": "gsigmad:",
            "portfolio_owner": "gsigmad",
            "emits_canonical_receipts": True,
            "forward_contract_enabled": True,
        }
    )

    assert profile.repo_class.value == "active"

    with pytest.raises(ValidationError, match="repo_class"):
        RepoAdoptionProfile.model_validate(
            {
                "repo_name": "experimental-repo",
                "repo_class": "experimental",
                "runtime_mode": "gsigmad",
                "namespace_prefix": "exp:",
                "portfolio_owner": "gsigmad",
            }
        )


def test_frozen_repo_rejects_mutating_posture_and_active_participant_semantics() -> None:
    with pytest.raises(ValidationError, match="mutating posture"):
        RepoAdoptionProfile.model_validate(
            {
                "repo_name": "substrata",
                "repo_class": "frozen",
                "runtime_mode": "legacy",
                "namespace_prefix": "substrata:",
                "portfolio_owner": "gsigmad",
                "allows_mutation": True,
            }
        )

    with pytest.raises(ValidationError, match="emit canonical receipts"):
        RepoAdoptionProfile.model_validate(
            {
                "repo_name": "substrata",
                "repo_class": "frozen",
                "runtime_mode": "legacy",
                "namespace_prefix": "substrata:",
                "portfolio_owner": "gsigmad",
                "emits_canonical_receipts": True,
            }
        )

    with pytest.raises(ValidationError, match="mutating command 'run'"):
        RepoAdoptionProfile.model_validate(
            {
                "repo_name": "substrata",
                "repo_class": "frozen",
                "runtime_mode": "legacy",
                "namespace_prefix": "substrata:",
                "portfolio_owner": "gsigmad",
                "command_modes": {"run": "legacy"},
            }
        )


def test_active_repo_certification_can_be_eligible() -> None:
    result = certify_repo_adoption(
        RepoAdoptionProfile.model_validate(
            {
                "repo_name": "gettingsciencedone",
                "repo_class": "active",
                "runtime_mode": "gsigmad",
                "namespace_prefix": "gsigmad:",
                "portfolio_owner": "gsigmad",
                "command_modes": {
                    "status": "gsigmad",
                    "monitor": "gsigmad",
                    "run": "gsigmad",
                },
                "allows_mutation": True,
                "emits_canonical_receipts": True,
                "forward_contract_enabled": True,
            }
        )
    )

    assert result.readiness is RepoReadinessState.ELIGIBLE
    assert result.findings == []


def test_legacy_repo_certification_is_advisory_when_read_first() -> None:
    result = certify_repo_adoption(
        RepoAdoptionProfile.model_validate(
            {
                "repo_name": "legacy-proteomics",
                "repo_class": "legacy",
                "runtime_mode": "legacy",
                "namespace_prefix": "proteomics:",
                "portfolio_owner": "gsigmad",
                "command_modes": {
                    "status": "legacy",
                    "monitor": "legacy",
                    "run": "unsupported",
                },
            }
        )
    )

    assert result.readiness is RepoReadinessState.ADVISORY
    assert {finding.code for finding in result.advisory_findings} == {"legacy-compatibility-mode"}


def test_certification_blocks_namespace_shadow_queue_duplicate_owner_and_unsafe_commands() -> None:
    result = certify_repo_adoption(
        RepoAdoptionProfile.model_validate(
            {
                "repo_name": "watchtower-shadow",
                "repo_class": "legacy",
                "runtime_mode": "hybrid",
                "namespace_prefix": "watchtower:",
                "portfolio_owner": "watchtower",
                "command_modes": {
                    "status": "hybrid",
                    "run": "hybrid",
                },
                "namespace_conflict": True,
                "queue": "shadow",
                "claimed_surfaces": ["durable-truth"],
            }
        )
    )

    assert result.readiness is RepoReadinessState.BLOCKED
    blocking = {finding.code for finding in result.blocking_findings}
    assert blocking == {
        "namespace-collision",
        "shadow-queue",
        "duplicate-ownership:durable-truth",
        "unsafe-command-posture",
    }
    assert {
        finding.guardrail.value
        for finding in result.blocking_findings
        if finding.guardrail is not None
    } == {"shadow-queue", "duplicate-ownership"}
    assert all(finding.severity is RepoFindingSeverity.BLOCKING for finding in result.blocking_findings)
