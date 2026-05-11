"""Phase 35 retrofit, downgrade, and certification bundle helpers."""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gsigmad.governance.control_plane_contract import RepoClass
from gsigmad.governance.repo_adoption_contract import RepoCertificationResult, RepoReadinessState
from gsigmad.governance.overwatch_truth_contract import TruthProjectionCandidate


def _non_empty(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("value must be non-empty")
    return normalized


class RetrofitAction(str, Enum):
    APPEND_COMPAT_MANIFEST = "append-compat-manifest"
    ADD_PROJECTION = "add-projection"
    QUARANTINE = "quarantine"
    SUPERSEDE = "supersede"
    DEACTIVATE = "deactivate"
    MARK_ADVISORY = "mark-advisory"


class HistoricalArtifactPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    repo_class: RepoClass
    preserve_history: bool = True
    pointer_only: bool = False
    allow_source_mutation: bool = False
    allow_rewrite: bool = False

    @model_validator(mode="after")
    def _validate_policy(self) -> "HistoricalArtifactPolicy":
        if not self.preserve_history or self.allow_source_mutation or self.allow_rewrite:
            raise ValueError("historical artifact policy must remain append-only and evidence-preserving")
        if self.repo_class is RepoClass.FROZEN and not self.pointer_only:
            raise ValueError("frozen repos require projection-only historical policy")
        return self


class RetrofitDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    repo_name: str
    repo_class: RepoClass
    readiness: RepoReadinessState
    action: RetrofitAction
    evidence_refs: list[str] = Field(min_length=1)
    recorded_at: datetime
    preserve_history: bool = True
    allow_source_mutation: bool = False

    @field_validator("repo_name")
    @classmethod
    def _validate_repo_name(cls, value: str) -> str:
        return _non_empty(value)

    @field_validator("evidence_refs")
    @classmethod
    def _validate_evidence_refs(cls, value: list[str]) -> list[str]:
        return [_non_empty(item) for item in value]

    @model_validator(mode="after")
    def _validate_decision(self) -> "RetrofitDecision":
        if not self.preserve_history or self.allow_source_mutation:
            raise ValueError("retrofit decisions must remain append-only and evidence-preserving")
        if self.repo_class is RepoClass.FROZEN and self.action is RetrofitAction.APPEND_COMPAT_MANIFEST:
            raise ValueError("frozen repos require projection-only retrofit posture")
        return self


class CertificationBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    bundle_id: str
    repo_name: str
    repo_class: RepoClass
    certification: RepoCertificationResult
    decision: RetrofitDecision
    receipt_refs: list[str] = Field(default_factory=list)
    truth_candidates: list[TruthProjectionCandidate] = Field(default_factory=list)

    @field_validator("bundle_id", "repo_name")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        return _non_empty(value)

    @field_validator("receipt_refs")
    @classmethod
    def _validate_receipt_refs(cls, value: list[str]) -> list[str]:
        return [_non_empty(item) for item in value]

    @model_validator(mode="after")
    def _validate_bundle(self) -> "CertificationBundle":
        if self.repo_name != self.certification.repo_name or self.repo_name != self.decision.repo_name:
            raise ValueError("certification bundles must use one repo identity")
        if self.repo_class is not self.certification.repo_class or self.repo_class is not self.decision.repo_class:
            raise ValueError("certification bundles must use one repo class")
        if (
            self.certification.readiness is RepoReadinessState.BLOCKED
            and self.decision.action is RetrofitAction.APPEND_COMPAT_MANIFEST
        ):
            raise ValueError(
                "blocked retrofit bundles must quarantine, supersede, deactivate, or mark advisory"
            )
        if self.repo_class is RepoClass.FROZEN and self.decision.action is RetrofitAction.APPEND_COMPAT_MANIFEST:
            raise ValueError("frozen retrofit bundles require projection-only posture")
        return self
