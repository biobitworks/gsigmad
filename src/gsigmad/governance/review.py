"""Advisory pre-plan review service for Phase 21."""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from gsigmad.governance.gates.audit_claims import audit_claims_gate

ReferenceRole = Literal["substrate", "governance", "execution", "integration"]
PackRole = Literal["subject", "substrate", "governance", "execution", "integration"]

OPERATING_QUESTION_KEYS = {
    "substrate_vs_orchestration_boundary": "What is the substrate vs orchestration boundary?",
    "verified_vs_claimed": "What is actually verified vs only claimed?",
    "smallest_deterministic_primitive_first": "What is the smallest deterministic primitive first?",
    "what_should_be_deferred": "What should be deferred?",
}


class ReferencePackInput(BaseModel):
    """User-provided role-scoped reference pack."""

    role: ReferenceRole
    path: Path


class ComparisonPrompt(BaseModel):
    """Cross-project comparison request."""

    prompt: str
    reference_roles: list[ReferenceRole] = Field(default_factory=list)


class ReviewRequest(BaseModel):
    """Inputs for an advisory review."""

    subject_repo: Path
    references: list[ReferencePackInput] = Field(default_factory=list)
    comparisons: list[ComparisonPrompt] = Field(default_factory=list)


class PackDocument(BaseModel):
    """Resolved document in a review pack."""

    name: str
    path: Path | None = None
    exists: bool
    content: str | None = None


class ReferencePackDocuments(BaseModel):
    """Required files for a review pack."""

    project: PackDocument
    roadmap: PackDocument
    state: PackDocument
    latest_reviews: PackDocument
    latest_verification: PackDocument


class ReviewFinding(BaseModel):
    """Advisory review finding."""

    code: str
    severity: Literal["info", "warning", "advisory"] = "advisory"
    subject: str
    message: str
    pack_role: PackRole
    path: Path | None = None


class LoadedReferencePack(BaseModel):
    """Loaded subject or reference pack."""

    role: PackRole
    path: Path
    documents: ReferencePackDocuments


class ComparisonOutcome(BaseModel):
    """Normalized comparison result."""

    prompt: str
    reference_roles: list[ReferenceRole]
    carry_over: list[str]
    exclusions: list[str]
    boundary_statement: str
    blind_copy_risks: list[str]
    recommended_next_milestone: str


class ReviewResult(BaseModel):
    """Normalized review output."""

    status: Literal["advisory"] = "advisory"
    created_at: str
    subject: LoadedReferencePack
    references: list[LoadedReferencePack]
    findings: list[ReviewFinding]
    questions: dict[str, str]
    goal: str
    risks: list[str]
    blockers: list[str]
    next_phase: str
    verification_gaps: list[str]
    next_commands: list[str]
    comparisons: list[ComparisonOutcome] = Field(default_factory=list)


def run_review(request: ReviewRequest) -> ReviewResult:
    """Run advisory review for a subject repo and optional references."""
    findings: list[ReviewFinding] = []
    subject = _load_reference_pack(request.subject_repo, "subject", findings)
    references = [
        _load_reference_pack(reference.path, reference.role, findings)
        for reference in request.references
    ]

    findings.extend(_audit_local_claims(subject.path))
    comparisons = [_build_comparison(prompt, subject, references) for prompt in request.comparisons]
    questions = _build_questions(subject, findings)
    verification_gaps = _collect_verification_gaps(findings)

    return ReviewResult(
        created_at=datetime.now(UTC).isoformat(),
        subject=subject,
        references=references,
        findings=findings,
        questions=questions,
        goal=_derive_goal(subject),
        risks=_derive_risks(findings, comparisons),
        blockers=_derive_blockers(findings),
        next_phase=_derive_next_phase(subject, comparisons),
        verification_gaps=verification_gaps,
        next_commands=_derive_next_commands(subject.path, request.references, verification_gaps),
        comparisons=comparisons,
    )


def render_review_json(review: ReviewResult) -> str:
    """Render the authoritative machine artifact."""
    return json.dumps(review.model_dump(mode="json"), indent=2)


def render_review_markdown(review: ReviewResult) -> str:
    """Render the human-readable companion review."""
    lines = [
        "# Pre-Plan Review",
        "",
        f"- Status: {review.status}",
        f"- Created: {review.created_at}",
        f"- Subject: {review.subject.path}",
        "",
        "## Operating Questions",
        "",
    ]
    for key, prompt in OPERATING_QUESTION_KEYS.items():
        lines.append(f"### {prompt}")
        lines.append(review.questions[key])
        lines.append("")

    lines.extend(
        [
            "## Outcome",
            "",
            f"- Goal: {review.goal}",
            f"- Next phase: {review.next_phase}",
            "",
            "## Risks",
            "",
        ]
    )
    for risk in review.risks or ["No material risks surfaced."]:
        lines.append(f"- {risk}")

    lines.extend(["", "## Verification Gaps", ""])
    for gap in review.verification_gaps or ["No verification gaps recorded."]:
        lines.append(f"- {gap}")

    lines.extend(["", "## Findings", ""])
    for finding in review.findings or []:
        location = f" ({finding.path})" if finding.path else ""
        lines.append(f"- [{finding.code}] {finding.subject}: {finding.message}{location}")
    if not review.findings:
        lines.append("- No findings.")

    if review.comparisons:
        lines.extend(["", "## Comparisons", ""])
        for comparison in review.comparisons:
            lines.append(f"### {comparison.prompt}")
            lines.append("")
            lines.append("Carry-over:")
            for item in comparison.carry_over:
                lines.append(f"- {item}")
            lines.append("Exclusions:")
            for item in comparison.exclusions:
                lines.append(f"- {item}")
            lines.append(f"Boundary: {comparison.boundary_statement}")
            lines.append("Blind-copy risks:")
            for item in comparison.blind_copy_risks:
                lines.append(f"- {item}")
            lines.append(f"Recommended next milestone: {comparison.recommended_next_milestone}")
            lines.append("")

    lines.extend(["## Next Commands", ""])
    for command in review.next_commands:
        lines.append(f"- `{command}`")
    lines.append("")
    return "\n".join(lines)


def write_review_artifacts(review: ReviewResult, output_dir: Path, stem: str = "PRE_PLAN_REVIEW") -> tuple[Path, Path]:
    """Persist authoritative JSON and companion Markdown artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{stem}.json"
    markdown_path = output_dir / f"{stem}.md"
    json_path.write_text(render_review_json(review), encoding="utf-8")
    markdown_path.write_text(render_review_markdown(review), encoding="utf-8")
    return json_path, markdown_path


def _load_reference_pack(path: Path, role: PackRole, findings: list[ReviewFinding]) -> LoadedReferencePack:
    repo_path = path.resolve()
    planning_dir = repo_path / ".planning"
    documents = ReferencePackDocuments(
        project=_load_required_document(planning_dir / "PROJECT.md", role, "project", findings),
        roadmap=_load_required_document(planning_dir / "ROADMAP.md", role, "roadmap", findings),
        state=_load_required_document(planning_dir / "STATE.md", role, "state", findings),
        latest_reviews=_load_latest_phase_document(
            planning_dir,
            "*REVIEWS.md",
            "latest_reviews",
            role,
            findings,
        ),
        latest_verification=_load_latest_phase_document(
            planning_dir,
            "*VERIFICATION.md",
            "latest_verification",
            role,
            findings,
        ),
    )
    return LoadedReferencePack(role=role, path=repo_path, documents=documents)


def _load_required_document(
    path: Path,
    role: PackRole,
    name: str,
    findings: list[ReviewFinding],
) -> PackDocument:
    if path.is_file():
        return PackDocument(
            name=name,
            path=path,
            exists=True,
            content=path.read_text(encoding="utf-8"),
        )

    findings.append(
        ReviewFinding(
            code="REFERENCE_PACK_MISSING",
            subject=f"{role}.{name}",
            message=f"Required reference-pack member is missing: {path.name}.",
            pack_role=role,
            path=path,
        )
    )
    return PackDocument(name=name, path=path, exists=False, content=None)


def _load_latest_phase_document(
    planning_dir: Path,
    pattern: str,
    name: str,
    role: PackRole,
    findings: list[ReviewFinding],
) -> PackDocument:
    matches = sorted((planning_dir / "phases").glob(f"**/{pattern}")) if (planning_dir / "phases").exists() else []
    if matches:
        latest = matches[-1]
        return PackDocument(
            name=name,
            path=latest,
            exists=True,
            content=latest.read_text(encoding="utf-8"),
        )

    findings.append(
        ReviewFinding(
            code="REFERENCE_PACK_MISSING",
            subject=f"{role}.{name}",
            message=f"Required reference-pack member is missing: {pattern}.",
            pack_role=role,
            path=planning_dir / "phases",
        )
    )
    return PackDocument(name=name, path=None, exists=False, content=None)


def _audit_local_claims(repo_path: Path) -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []
    experiments_dir = repo_path / ".gsigmad" / "experiments"
    if not experiments_dir.is_dir():
        return findings

    claims: list[dict] = []
    for experiment_path in sorted(experiments_dir.glob("*.yaml")):
        payload = yaml.safe_load(experiment_path.read_text(encoding="utf-8")) or {}
        for claim in payload.get("claims", []):
            normalized = dict(claim)
            normalized.setdefault("_source_path", experiment_path)
            claims.append(normalized)

    if not claims:
        return findings

    result = audit_claims_gate(claims, verify_citations=False)
    for failure in result.get("failures", []):
        claim_index = failure.get("claim_index", 0)
        claim = claims[claim_index] if claim_index < len(claims) else {}
        findings.append(
            ReviewFinding(
                code="CLAIM_AUDIT_FAILURE",
                subject=f"subject.claims[{claim_index}]",
                message=str(failure.get("error", "Claim audit failure.")),
                pack_role="subject",
                path=claim.get("_source_path"),
            )
        )
    for warning in result.get("warnings", []):
        findings.append(
            ReviewFinding(
                code="CLAIM_AUDIT_WARNING",
                severity="warning",
                subject="subject.claims",
                message=str(warning),
                pack_role="subject",
            )
        )
    return findings


def _build_questions(subject: LoadedReferencePack, findings: list[ReviewFinding]) -> dict[str, str]:
    project_text = subject.documents.project.content or ""
    verification_text = subject.documents.latest_verification.content or ""
    review_text = subject.documents.latest_reviews.content or ""
    boundary = _extract_line(project_text, r"(?im)^boundary:\s*(.+)$")
    if not boundary:
        layer_lines = [line.strip() for line in project_text.splitlines() if "Layer " in line]
        boundary = " ".join(layer_lines[:2]).strip()
    if not boundary:
        boundary = "Subject repo should keep substrate logic separate from governance orchestration."

    verified = []
    if verification_text:
        verified.append("Verification artifact present in latest VERIFICATION.md.")
    if review_text:
        verified.append("Review history exists in latest REVIEWS.md.")
    if not verified:
        verified.append("No review or verification artifact found; treat planning claims as unverified.")

    gaps = _collect_verification_gaps(findings)
    deterministic = (
        "Start with the typed local review contract and file-backed artifacts before transport or automation layers."
    )
    deferred = (
        "Defer transport parity, writeback, manifests, replay, and recovery work until the advisory review contract is stable."
    )
    if gaps:
        deferred += f" Current gaps: {', '.join(gaps[:2])}."

    return {
        "substrate_vs_orchestration_boundary": boundary,
        "verified_vs_claimed": " ".join(verified),
        "smallest_deterministic_primitive_first": deterministic,
        "what_should_be_deferred": deferred,
    }


def _build_comparison(
    prompt: ComparisonPrompt,
    subject: LoadedReferencePack,
    references: list[LoadedReferencePack],
) -> ComparisonOutcome:
    selected = [reference for reference in references if reference.role in prompt.reference_roles]
    role_names = [reference.role for reference in selected]
    carry_over = [
        f"Reuse the {reference.role} reference-pack shape from {reference.path}."
        for reference in selected
    ] or ["No reference roles selected; compare against the subject repo's own planning pack."]
    exclusions = [
        "Do not copy external repo plans or mutate reference repositories.",
        "Do not treat advisory findings as new gate-chain requirements.",
    ]
    boundary_statement = (
        f"Comparison stays advisory: subject repo {subject.path} may learn from {', '.join(role_names) or 'itself'} "
        "without importing source truth or writeback behavior."
    )
    blind_copy_risks = [
        "Reference repos may encode assumptions that are not verified in the subject repo.",
        "Copying commands or milestones blindly can collapse the substrate vs orchestration boundary.",
    ]
    recommended_next_milestone = _extract_milestone(subject.documents.project.content or "")
    return ComparisonOutcome(
        prompt=prompt.prompt,
        reference_roles=prompt.reference_roles,
        carry_over=carry_over,
        exclusions=exclusions,
        boundary_statement=boundary_statement,
        blind_copy_risks=blind_copy_risks,
        recommended_next_milestone=recommended_next_milestone,
    )


def _derive_goal(subject: LoadedReferencePack) -> str:
    project_text = subject.documents.project.content or ""
    roadmap_text = subject.documents.roadmap.content or ""
    goal = _extract_line(project_text, r"(?im)^\*\*Goal:\*\*\s*(.+)$")
    if not goal:
        goal = _extract_line(project_text, r"(?im)^goal:\s*(.+)$")
    if not goal:
        goal = _extract_line(roadmap_text, r"(?im)^goal:\s*(.+)$")
    return goal or "Establish the next deterministic planning step before plan files exist."


def _derive_risks(findings: list[ReviewFinding], comparisons: list[ComparisonOutcome]) -> list[str]:
    risks = [finding.message for finding in findings[:4]]
    if comparisons:
        risks.append("Cross-project comparison can leak assumptions if role boundaries are ignored.")
    return risks or ["No immediate risks surfaced."]


def _derive_blockers(findings: list[ReviewFinding]) -> list[str]:
    blockers = [
        finding.message
        for finding in findings
        if finding.code == "REFERENCE_PACK_MISSING"
        and any(token in finding.subject for token in ("project", "roadmap", "state"))
    ]
    return blockers


def _derive_next_phase(subject: LoadedReferencePack, comparisons: list[ComparisonOutcome]) -> str:
    milestone = _extract_milestone(subject.documents.project.content or "")
    if comparisons:
        return f"Plan the next phase for {milestone} with comparison findings folded into scope."
    return f"Plan the next phase for {milestone}."


def _derive_next_commands(
    subject_repo: Path,
    references: list[ReferencePackInput],
    verification_gaps: list[str],
) -> list[str]:
    command = ["gsigmad review"]
    for reference in references:
        command.append(f"--reference {reference.role}={reference.path}")
    commands = [" ".join(command)]
    if verification_gaps:
        commands.append("/gsd:plan-phase 21 --auto")
    else:
        commands.append("/gsd:execute-phase 21")
    commands.append(f"cd {subject_repo}")
    return commands


def _collect_verification_gaps(findings: list[ReviewFinding]) -> list[str]:
    gaps = []
    for finding in findings:
        if finding.code in {"REFERENCE_PACK_MISSING", "CLAIM_AUDIT_FAILURE", "CLAIM_AUDIT_WARNING"}:
            gaps.append(finding.message)
    return gaps


def _extract_line(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text)
    if match:
        return match.group(1).strip()
    return None


def _extract_milestone(text: str) -> str:
    for pattern in (
        r"(?im)^\*\*Current Milestone:\*\*\s*(.+)$",
        r"(?im)^milestone:\s*(.+)$",
        r"(?im)^#\s+(.+)$",
    ):
        value = _extract_line(text, pattern)
        if value:
            return value
    return "the active milestone"
