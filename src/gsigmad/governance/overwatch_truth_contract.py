"""Phase 35 Overwatch truth-ingestion and projection helpers."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import PurePath

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gsigmad.governance.control_plane_contract import (
    DIRECT_DURABLE_DECISION_TYPES,
    DURABLE_RECEIPT_TYPES,
    ControlPlaneOwner,
    LiveEventType,
    RepoClass,
    validate_control_plane_guardrails,
)
from gsigmad.governance.state_authority import is_promotable_durable

_FORBIDDEN_EVIDENCE_MARKERS = (
    "queue",
    "cursor",
    "payload",
    "packet",
    "cache",
    "retry",
    "snapshot",
    "diff",
    "manifest",
)


def _non_empty(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("value must be non-empty")
    return normalized


def _is_forbidden_evidence_ref(value: str) -> bool:
    normalized = PurePath(value).as_posix().lower()
    return any(marker in normalized for marker in _FORBIDDEN_EVIDENCE_MARKERS)


class TruthSubjectClass(str, Enum):
    DURABLE_RECEIPT = "durable-receipt"
    DIRECT_DURABLE = "direct-durable"
    PROMOTED_CLAIM = "promoted-claim"


class GraphProjectionRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    projection_kind: str
    canonical_type: str
    canonical_id: str
    artifact_ref: str

    @field_validator("projection_kind", "canonical_type", "canonical_id")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        return _non_empty(value)

    @field_validator("artifact_ref")
    @classmethod
    def _validate_artifact_ref(cls, value: str) -> str:
        normalized = _non_empty(value)
        if _is_forbidden_evidence_ref(normalized):
            raise ValueError("graph projections must not point at evidence-only artifacts")
        return normalized


def is_ingestible_truth_subject(subject: object) -> bool:
    if isinstance(subject, LiveEventType):
        return False
    if isinstance(subject, str):
        normalized = subject.strip()
        if normalized in {item.value for item in LiveEventType}:
            return False
        if _is_forbidden_evidence_ref(normalized):
            return False
    return is_promotable_durable(subject)


def validate_truth_projection_payload(payload: dict[str, object]) -> dict[str, object]:
    normalized = validate_control_plane_guardrails(payload)
    if "source_ref" in normalized and _is_forbidden_evidence_ref(str(normalized["source_ref"])):
        raise ValueError("truth-projection payloads must not promote evidence-only refs directly")
    if normalized.get("owner") == ControlPlaneOwner.WATCHTOWER.value:
        raise ValueError("Watchtower projections cannot originate durable truth")
    return normalized


class TruthProjectionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    candidate_id: str
    source_owner: ControlPlaneOwner
    source_repo_class: RepoClass
    subject_class: TruthSubjectClass
    promoted_type: str
    promoted_id: str
    source_ref: str
    graph_projection_refs: list[GraphProjectionRef] = Field(min_length=1)

    @field_validator("candidate_id", "promoted_type", "promoted_id", "source_ref")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        return _non_empty(value)

    @model_validator(mode="after")
    def _validate_surface(self) -> "TruthProjectionCandidate":
        if self.source_owner is ControlPlaneOwner.WATCHTOWER:
            raise ValueError("Watchtower projections cannot originate durable truth")
        if _is_forbidden_evidence_ref(self.source_ref):
            raise ValueError("truth projection candidates cannot promote evidence-only refs directly")
        if not is_ingestible_truth_subject(self.promoted_type):
            raise ValueError(f"unsupported truth projection subject '{self.promoted_type}'")
        if self.subject_class is TruthSubjectClass.DURABLE_RECEIPT and self.promoted_type not in DURABLE_RECEIPT_TYPES:
            raise ValueError("durable-receipt truth projection candidates must use a closed durable receipt type")
        if self.subject_class is TruthSubjectClass.DIRECT_DURABLE and self.promoted_type not in DIRECT_DURABLE_DECISION_TYPES:
            raise ValueError("direct-durable truth projection candidates must use a direct durable decision type")
        if self.subject_class is TruthSubjectClass.PROMOTED_CLAIM and self.promoted_type != "Claim":
            raise ValueError("promoted-claim truth projection candidates must promote Claim")
        return self


class KGIngestionReceiptContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    receipt_id: str
    owner: ControlPlaneOwner = ControlPlaneOwner.OVERWATCH
    source_owner: ControlPlaneOwner
    source_repo_class: RepoClass
    candidate_id: str
    promoted_type: str
    promoted_id: str
    ingested_at: datetime
    idempotency_key: str
    source_artifact_refs: list[str] = Field(min_length=1)
    graph_projection_refs: list[GraphProjectionRef] = Field(min_length=1)

    @field_validator("receipt_id", "candidate_id", "promoted_type", "promoted_id", "idempotency_key")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        return _non_empty(value)

    @field_validator("source_artifact_refs")
    @classmethod
    def _validate_artifact_refs(cls, value: list[str]) -> list[str]:
        normalized = [_non_empty(item) for item in value]
        evidence_only = [item for item in normalized if _is_forbidden_evidence_ref(item)]
        if evidence_only:
            raise ValueError("KG ingestion receipts must not use evidence-only artifacts as direct truth refs")
        return normalized

    @model_validator(mode="after")
    def _validate_surface(self) -> "KGIngestionReceiptContract":
        if self.owner is not ControlPlaneOwner.OVERWATCH:
            raise ValueError("Overwatch must own KG ingestion receipts")
        if self.source_owner is ControlPlaneOwner.WATCHTOWER:
            raise ValueError("Watchtower projections cannot originate durable truth")
        if not is_ingestible_truth_subject(self.promoted_type):
            raise ValueError(f"unsupported ingested truth subject '{self.promoted_type}'")
        return self
