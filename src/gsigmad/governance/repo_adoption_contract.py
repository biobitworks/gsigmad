"""Phase 35 repo adoption and certification contract helpers."""
from __future__ import annotations

from enum import Enum
from typing import Literal, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gsigmad.governance.control_plane_contract import (
    MUTATING_COMMANDS,
    ControlPlaneGuardrail,
    ControlPlaneOwner,
    OwnershipSurface,
    RepoClass,
    get_surface_owner,
    validate_control_plane_guardrails,
)
from gsigmad.governance.adapters.runtime import RuntimeAdapterManifest

CommandMode = Literal["legacy", "gsigmad", "hybrid", "unsupported"]
RuntimeMode = Literal["legacy", "gsigmad", "hybrid"]


class RepoReadinessState(str, Enum):
    ELIGIBLE = "eligible"
    ADVISORY = "advisory"
    BLOCKED = "blocked"


class RepoFindingSeverity(str, Enum):
    BLOCKING = "blocking"
    ADVISORY = "advisory"


class RepoCertificationFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    severity: RepoFindingSeverity
    summary: str
    field: Optional[str] = None
    guardrail: Optional[ControlPlaneGuardrail] = None

    @field_validator("code", "summary", "field")
    @classmethod
    def _validate_non_empty(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must be non-empty")
        return normalized


class RepoAdoptionProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    repo_name: str
    repo_class: RepoClass
    runtime_mode: RuntimeMode
    namespace_prefix: str
    portfolio_owner: ControlPlaneOwner
    command_modes: dict[str, CommandMode] = Field(default_factory=dict)
    claimed_surfaces: tuple[OwnershipSurface, ...] = ()
    planner: str = "gsigmad"
    queue: str = "repo-local"
    allows_mutation: bool = False
    emits_canonical_receipts: bool = False
    consumes_canonical_receipts: bool = True
    namespace_conflict: bool = False
    forward_contract_enabled: bool = False
    advisory_gaps: tuple[str, ...] = ()

    @field_validator("repo_name")
    @classmethod
    def _validate_repo_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("repo_name must be non-empty")
        return normalized

    @field_validator("namespace_prefix")
    @classmethod
    def _validate_namespace_prefix(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.endswith(":"):
            raise ValueError("namespace_prefix must end with ':'")
        return normalized

    @field_validator("planner", "queue")
    @classmethod
    def _validate_surface_values(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must be non-empty")
        return normalized

    @field_validator("command_modes")
    @classmethod
    def _validate_command_modes(cls, value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for key, mode in value.items():
            command = str(key).strip()
            if not command:
                raise ValueError("command_modes keys must be non-empty")
            normalized[command] = mode
        return normalized

    @field_validator("advisory_gaps")
    @classmethod
    def _validate_advisories(cls, value: Sequence[str]) -> tuple[str, ...]:
        normalized: list[str] = []
        for item in value:
            gap = item.strip()
            if not gap:
                raise ValueError("advisory gaps must be non-empty")
            normalized.append(gap)
        return tuple(normalized)

    @model_validator(mode="after")
    def _validate_repo_class_posture(self) -> "RepoAdoptionProfile":
        mutating_modes = {
            command: mode
            for command, mode in self.command_modes.items()
            if command in MUTATING_COMMANDS and mode != "unsupported"
        }
        if self.repo_class is RepoClass.FROZEN:
            if self.allows_mutation:
                raise ValueError("frozen repos cannot allow mutating posture")
            if self.emits_canonical_receipts:
                raise ValueError("frozen repos cannot emit canonical receipts")
            if mutating_modes:
                first_command = sorted(mutating_modes)[0]
                raise ValueError(f"frozen repos cannot opt into mutating command '{first_command}'")
        return self

    @classmethod
    def from_runtime_manifest(
        cls,
        manifest: RuntimeAdapterManifest,
        *,
        portfolio_owner: ControlPlaneOwner,
        claimed_surfaces: Sequence[OwnershipSurface] = (),
        emits_canonical_receipts: bool = False,
        consumes_canonical_receipts: bool = True,
        allows_mutation: Optional[bool] = None,
        planner: str = "gsigmad",
        queue: str = "repo-local",
        namespace_conflict: bool = False,
        forward_contract_enabled: bool = False,
        advisory_gaps: Sequence[str] = (),
    ) -> "RepoAdoptionProfile":
        command_modes = dict(manifest.command_modes)
        if allows_mutation is None:
            allows_mutation = any(
                command in MUTATING_COMMANDS and mode != "unsupported"
                for command, mode in command_modes.items()
            )
        return cls.model_validate(
            {
                "repo_name": manifest.project_name,
                "repo_class": manifest.repo_class,
                "runtime_mode": manifest.runtime_mode,
                "namespace_prefix": manifest.namespace_prefix,
                "portfolio_owner": portfolio_owner,
                "command_modes": command_modes,
                "claimed_surfaces": list(claimed_surfaces),
                "planner": planner,
                "queue": queue,
                "allows_mutation": allows_mutation,
                "emits_canonical_receipts": emits_canonical_receipts,
                "consumes_canonical_receipts": consumes_canonical_receipts,
                "namespace_conflict": namespace_conflict,
                "forward_contract_enabled": forward_contract_enabled,
                "advisory_gaps": list(advisory_gaps),
            }
        )


class RepoCertificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    repo_name: str
    repo_class: RepoClass
    readiness: RepoReadinessState
    findings: list[RepoCertificationFinding] = Field(default_factory=list)

    @property
    def blocking_findings(self) -> tuple[RepoCertificationFinding, ...]:
        return tuple(
            finding for finding in self.findings if finding.severity is RepoFindingSeverity.BLOCKING
        )

    @property
    def advisory_findings(self) -> tuple[RepoCertificationFinding, ...]:
        return tuple(
            finding for finding in self.findings if finding.severity is RepoFindingSeverity.ADVISORY
        )


def certify_repo_adoption(profile: RepoAdoptionProfile) -> RepoCertificationResult:
    """Classify one repo's retrofit readiness without creating a second planner."""
    findings: list[RepoCertificationFinding] = []

    if profile.namespace_conflict:
        findings.append(
            RepoCertificationFinding(
                code="namespace-collision",
                severity=RepoFindingSeverity.BLOCKING,
                summary="Namespace prefix collides with another repo and must be resolved before certification.",
                field="namespace_prefix",
            )
        )

    try:
        validate_control_plane_guardrails(
            {
                "planner": profile.planner,
                "queue": profile.queue,
            }
        )
    except ValueError as exc:
        message = str(exc)
        if "second planner" in message:
            findings.append(
                RepoCertificationFinding(
                    code="second-planner",
                    severity=RepoFindingSeverity.BLOCKING,
                    summary=message,
                    field="planner",
                    guardrail=ControlPlaneGuardrail.SECOND_PLANNER,
                )
            )
        elif "shadow queue" in message:
            findings.append(
                RepoCertificationFinding(
                    code="shadow-queue",
                    severity=RepoFindingSeverity.BLOCKING,
                    summary=message,
                    field="queue",
                    guardrail=ControlPlaneGuardrail.SHADOW_QUEUE,
                )
            )
        else:
            findings.append(
                RepoCertificationFinding(
                    code="control-plane-guardrail",
                    severity=RepoFindingSeverity.BLOCKING,
                    summary=message,
                )
            )

    for surface in profile.claimed_surfaces:
        if get_surface_owner(surface) is not profile.portfolio_owner:
            findings.append(
                RepoCertificationFinding(
                    code=f"duplicate-ownership:{surface.value}",
                    severity=RepoFindingSeverity.BLOCKING,
                    summary=(
                        f"{profile.portfolio_owner.value} cannot claim '{surface.value}'; "
                        f"canonical owner is {get_surface_owner(surface).value}."
                    ),
                    field="claimed_surfaces",
                    guardrail=ControlPlaneGuardrail.DUPLICATE_OWNERSHIP,
                )
            )

    mutating_modes = sorted(
        command
        for command, mode in profile.command_modes.items()
        if command in MUTATING_COMMANDS and mode != "unsupported"
    )
    if profile.repo_class is RepoClass.LEGACY and mutating_modes and not profile.forward_contract_enabled:
        findings.append(
            RepoCertificationFinding(
                code="unsafe-command-posture",
                severity=RepoFindingSeverity.BLOCKING,
                summary=(
                    "Legacy repos must stay read-first until they explicitly opt into forward contract gates; "
                    f"mutating commands enabled: {', '.join(mutating_modes)}."
                ),
                field="command_modes",
            )
        )

    if profile.repo_class is RepoClass.ACTIVE and not profile.emits_canonical_receipts:
        findings.append(
            RepoCertificationFinding(
                code="missing-forward-receipts",
                severity=RepoFindingSeverity.ADVISORY,
                summary="Active repos should emit or reference canonical receipts for new v2.1 work.",
                field="emits_canonical_receipts",
            )
        )

    if profile.repo_class is RepoClass.LEGACY:
        findings.append(
            RepoCertificationFinding(
                code="legacy-compatibility-mode",
                severity=RepoFindingSeverity.ADVISORY,
                summary="Legacy repos remain compatibility participants until stronger forward gates are enabled.",
                field="runtime_mode",
            )
        )

    if profile.repo_class is RepoClass.FROZEN:
        findings.append(
            RepoCertificationFinding(
                code="frozen-read-only",
                severity=RepoFindingSeverity.ADVISORY,
                summary="Frozen repos stay read-only exemplar inputs and certify through snapshots, not mutation.",
                field="repo_class",
            )
        )

    for index, gap in enumerate(profile.advisory_gaps, start=1):
        findings.append(
            RepoCertificationFinding(
                code=f"advisory-gap-{index}",
                severity=RepoFindingSeverity.ADVISORY,
                summary=gap,
            )
        )

    readiness = RepoReadinessState.ELIGIBLE
    if any(finding.severity is RepoFindingSeverity.BLOCKING for finding in findings):
        readiness = RepoReadinessState.BLOCKED
    elif findings:
        readiness = RepoReadinessState.ADVISORY

    return RepoCertificationResult(
        repo_name=profile.repo_name,
        repo_class=profile.repo_class,
        readiness=readiness,
        findings=findings,
    )
