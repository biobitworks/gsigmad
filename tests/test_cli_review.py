"""Tests for gsigmad review command."""
from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from gsigmad.cli import app

runner = CliRunner()


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
        "# Project\n\nCurrent Milestone: v1.8 Science Execution & Resilience\n"
        "Boundary: Substrate stays separate from governance orchestration.\n",
    )
    _write_file(root / ".planning" / "ROADMAP.md", "# Roadmap\n\nGoal: Pre-plan review.\n")
    _write_file(root / ".planning" / "STATE.md", "# State\n\nPhase: 21\nStatus: Planning\n")

    if include_reviews:
        _write_file(
            root / ".planning" / "phases" / "21-phase" / "21-REVIEWS.md",
            "# Reviews\n\nPrior advisory review.\n",
        )
    if include_verification:
        _write_file(
            root / ".planning" / "phases" / "21-phase" / "21-VERIFICATION.md",
            "# Verification\n\nVerified smoke test.\n",
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


def test_review_cli_succeeds_without_plan_files(tmp_path: Path, monkeypatch) -> None:
    subject = _write_planning_repo(tmp_path / "subject")
    monkeypatch.chdir(subject)

    result = runner.invoke(app, ["review"], catch_exceptions=False)

    assert result.exit_code == 0, result.output
    assert not list(subject.glob("**/PLAN.md"))
    assert (subject / ".planning" / "reviews" / "PRE_PLAN_REVIEW.json").is_file()
    assert (subject / ".planning" / "reviews" / "PRE_PLAN_REVIEW.md").is_file()


def test_review_cli_accepts_references_and_comparisons_and_writes_dual_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    subject = _write_planning_repo(tmp_path / "subject")
    governance = _write_planning_repo(tmp_path / "governance")
    execution = _write_planning_repo(tmp_path / "execution")
    monkeypatch.chdir(subject)

    result = runner.invoke(
        app,
        [
            "review",
            "--reference",
            f"governance={governance}",
            "--reference",
            f"execution={execution}",
            "--comparison",
            "What carries over from the governance reference?",
            "--comparison-role",
            "governance",
            "--comparison",
            "What should stay execution-specific?",
            "--comparison-role",
            "execution",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    json_artifact = subject / ".planning" / "reviews" / "PRE_PLAN_REVIEW.json"
    markdown_artifact = subject / ".planning" / "reviews" / "PRE_PLAN_REVIEW.md"
    data = json.loads(json_artifact.read_text(encoding="utf-8"))
    assert data["subject"]["path"] == str(subject.resolve())
    assert [pack["role"] for pack in data["references"]] == ["governance", "execution"]
    assert len(data["comparisons"]) == 2
    assert markdown_artifact.read_text(encoding="utf-8").startswith("# Pre-Plan Review")


def test_review_cli_stays_advisory_when_findings_exist(tmp_path: Path, monkeypatch) -> None:
    subject = _write_planning_repo(
        tmp_path / "subject",
        include_reviews=False,
        include_verification=False,
        claim_text="Significant at p < 0.05 with no effect size.",
    )
    substrate = _write_planning_repo(tmp_path / "substrate")
    monkeypatch.chdir(subject)

    result = runner.invoke(
        app,
        [
            "review",
            "--reference",
            f"substrate={substrate}",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    assert "finding" in result.output.lower()
    data = json.loads(
        (subject / ".planning" / "reviews" / "PRE_PLAN_REVIEW.json").read_text(encoding="utf-8")
    )
    finding_codes = {finding["code"] for finding in data["findings"]}
    assert "REFERENCE_PACK_MISSING" in finding_codes
    assert "CLAIM_AUDIT_FAILURE" in finding_codes
