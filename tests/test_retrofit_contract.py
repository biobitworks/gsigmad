"""Tests for the Phase 35 retrofit and rollout contract."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from gsigmad.governance.repo_adoption_contract import RepoCertificationResult
from gsigmad.governance.retrofit_contract import (
    CertificationBundle,
    HistoricalArtifactPolicy,
    RetrofitAction,
    RetrofitDecision,
)


def _certification(
    readiness: str = "eligible",
    repo_class: str = "active",
    repo_name: str = "gettingsciencedone",
) -> RepoCertificationResult:
    return RepoCertificationResult.model_validate(
        {
            "repo_name": repo_name,
            "repo_class": repo_class,
            "readiness": readiness,
            "findings": [],
        }
    )


def test_retrofit_decision_stays_append_only_and_evidence_preserving() -> None:
    decision = RetrofitDecision.model_validate(
        {
            "repo_name": "gettingsciencedone",
            "repo_class": "active",
            "readiness": "eligible",
            "action": "supersede",
            "evidence_refs": ["reports/certification/v2.1.json"],
            "recorded_at": datetime.now(tz=timezone.utc).isoformat(),
        }
    )

    assert decision.action is RetrofitAction.SUPERSEDE
    assert decision.preserve_history is True
    assert decision.allow_source_mutation is False


def test_retrofit_decision_rejects_source_rewrite_or_mutation() -> None:
    with pytest.raises(ValidationError, match="append-only"):
        RetrofitDecision.model_validate(
            {
                "repo_name": "gettingsciencedone",
                "repo_class": "active",
                "readiness": "eligible",
                "action": "append-compat-manifest",
                "evidence_refs": ["reports/certification/v2.1.json"],
                "recorded_at": datetime.now(tz=timezone.utc).isoformat(),
                "allow_source_mutation": True,
            }
        )

    with pytest.raises(ValidationError, match="append-only"):
        HistoricalArtifactPolicy.model_validate(
            {
                "repo_class": "legacy",
                "allow_rewrite": True,
            }
        )


def test_frozen_repo_requires_projection_only_posture() -> None:
    policy = HistoricalArtifactPolicy.model_validate(
        {
            "repo_class": "frozen",
            "pointer_only": True,
        }
    )
    assert policy.pointer_only is True

    with pytest.raises(ValidationError, match="projection-only"):
        HistoricalArtifactPolicy.model_validate(
            {
                "repo_class": "frozen",
                "pointer_only": False,
            }
        )

    with pytest.raises(ValidationError, match="projection-only"):
        RetrofitDecision.model_validate(
            {
                "repo_name": "substrata",
                "repo_class": "frozen",
                "readiness": "advisory",
                "action": "append-compat-manifest",
                "evidence_refs": ["adapters/substrata.md"],
                "recorded_at": datetime.now(tz=timezone.utc).isoformat(),
            }
        )


def test_blocked_certification_bundle_must_quarantine_supersede_deactivate_or_mark_advisory() -> None:
    with pytest.raises(ValidationError, match="blocked retrofit bundles"):
        CertificationBundle.model_validate(
            {
                "bundle_id": "bundle-35-1",
                "repo_name": "watchtower-shadow",
                "repo_class": "legacy",
                "certification": _certification(
                    readiness="blocked",
                    repo_class="legacy",
                    repo_name="watchtower-shadow",
                ).model_dump(mode="json"),
                "decision": {
                    "repo_name": "watchtower-shadow",
                    "repo_class": "legacy",
                    "readiness": "blocked",
                    "action": "append-compat-manifest",
                    "evidence_refs": ["reports/certification/watchtower-shadow.json"],
                    "recorded_at": datetime.now(tz=timezone.utc).isoformat(),
                },
                "receipt_refs": ["reports/certification/watchtower-shadow.json"],
            }
        )
