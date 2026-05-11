"""Tests for advisory pre-plan review service."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from gsigmad.governance.review import (
    ComparisonPrompt,
    ReferencePackInput,
    ReviewRequest,
    run_review,
)


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_planning_repo(
    root: Path,
    *,
    include_reviews: bool = True,
    include_verification: bool = True,
    claim_text: str | None = None,
) -> Path:
    _write_file(
        root / ".planning" / "PROJECT.md",
        "# Project\n\nGoal: Build governed execution.\n\n"
        "Boundary: Substrate implements science logic. Orchestration handles governance.\n",
    )
    _write_file(
        root / ".planning" / "ROADMAP.md",
        "# Roadmap\n\n## Phase 21\n\nGoal: Advisory review before plan files.\n",
    )
    _write_file(
        root / ".planning" / "STATE.md",
        "# State\n\nCurrent Position\n\nPhase: 21\nPlan: 0 of 2\nStatus: Planning\n",
    )

    if include_reviews:
        _write_file(
            root / ".planning" / "phases" / "21-phase" / "21-REVIEWS.md",
            "# Reviews\n\nLatest review notes.\n",
        )
    if include_verification:
        _write_file(
            root / ".planning" / "phases" / "21-phase" / "21-VERIFICATION.md",
            "# Verification\n\nVerified: CLI smoke test.\n",
        )

    if claim_text is not None:
        experiments_dir = root / ".gsigmad" / "experiments"
        experiments_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "exp_id": "EXP-1.1",
            "classification": "EXPLORATORY",
            "claims": [{"text": claim_text}],
        }
        (experiments_dir / "EXP-1.1.yaml").write_text(
            yaml.safe_dump(record, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
    return root


def test_review_service_loads_subject_and_role_scoped_reference_packs(tmp_path: Path) -> None:
    subject = _write_planning_repo(tmp_path / "subject")
    governance = _write_planning_repo(tmp_path / "governance")
    execution = _write_planning_repo(tmp_path / "execution")
    integration = _write_planning_repo(tmp_path / "integration")

    with pytest.raises(ValidationError):
        ReferencePackInput(role="invalid", path=governance)

    request = ReviewRequest(
        subject_repo=subject,
        references=[
            ReferencePackInput(role="governance", path=governance),
            ReferencePackInput(role="execution", path=execution),
            ReferencePackInput(role="integration", path=integration),
        ],
    )

    result = run_review(request)

    assert result.subject.path == subject
    assert [pack.role for pack in result.references] == [
        "governance",
        "execution",
        "integration",
    ]
    assert result.subject.documents.project.path.name == "PROJECT.md"
    assert result.references[0].documents.roadmap.path.name == "ROADMAP.md"


def test_missing_reference_pack_members_are_findings_not_failures(tmp_path: Path) -> None:
    subject = _write_planning_repo(
        tmp_path / "subject",
        include_reviews=False,
        include_verification=False,
    )
    substrate = _write_planning_repo(tmp_path / "substrate")

    result = run_review(
        ReviewRequest(
            subject_repo=subject,
            references=[ReferencePackInput(role="substrate", path=substrate)],
        )
    )

    assert result.status == "advisory"
    missing_fields = {finding.subject for finding in result.findings if finding.code == "REFERENCE_PACK_MISSING"}
    assert "subject.latest_reviews" in missing_fields
    assert "subject.latest_verification" in missing_fields


def test_review_result_is_normalized_and_comparisons_emit_required_outputs(tmp_path: Path) -> None:
    subject = _write_planning_repo(
        tmp_path / "subject",
        claim_text="The result is significant at p < 0.05 without effect size.",
    )
    governance = _write_planning_repo(tmp_path / "governance")

    result = run_review(
        ReviewRequest(
            subject_repo=subject,
            references=[ReferencePackInput(role="governance", path=governance)],
            comparisons=[
                ComparisonPrompt(
                    prompt="Compare this repo against governance reference before planning.",
                    reference_roles=["governance"],
                )
            ],
        )
    )

    assert set(result.questions) == {
        "substrate_vs_orchestration_boundary",
        "verified_vs_claimed",
        "smallest_deterministic_primitive_first",
        "what_should_be_deferred",
    }
    assert result.goal
    assert isinstance(result.risks, list)
    assert isinstance(result.blockers, list)
    assert result.next_phase
    assert isinstance(result.verification_gaps, list)
    assert isinstance(result.next_commands, list)
    assert result.comparisons
    comparison = result.comparisons[0]
    assert comparison.carry_over
    assert comparison.exclusions
    assert comparison.boundary_statement
    assert comparison.blind_copy_risks
    assert comparison.recommended_next_milestone
    claim_finding_codes = {finding.code for finding in result.findings}
    assert "CLAIM_AUDIT_FAILURE" in claim_finding_codes
