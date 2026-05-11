"""Canonical execution-contract types for portfolio stage receipts."""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gsigmad.hub.ledger import hash_payload

DEFAULT_EXECUTION_CONTRACT_VERSION = "1.0"
SUPPORTED_CONTRACT_VERSIONS = {DEFAULT_EXECUTION_CONTRACT_VERSION}
SUPPORTED_PORTFOLIO_ROLES = {
    "contract-owner",
    "executor-offload",
    "observer-control-plane",
    "provenance-trace",
    "safety-sidecar",
    "project-execution",
}
_BULKY_MUTABLE_HASH_KEYS = {
    "artifact_payload",
    "artifacts_inline",
    "chunks",
    "outputs",
    "raw_outputs",
    "runtime_logs",
    "runtime_state",
}
_RUNTIME_HOST_CONTROL_KEYS = {
    "worker_routing",
    "gpu_schedule",
    "frontier_execution_defaults",
}


class StageName(str, Enum):
    PREFLIGHT = "preflight"
    SCAFFOLD_MATERIALIZE = "scaffold/materialize"
    EXECUTE = "execute"
    VALIDATE = "validate"
    SUMMARIZE = "summarize"
    INTERPRET_ESCALATE = "interpret/escalate"


STAGE_ORDER: tuple[StageName, ...] = (
    StageName.PREFLIGHT,
    StageName.SCAFFOLD_MATERIALIZE,
    StageName.EXECUTE,
    StageName.VALIDATE,
    StageName.SUMMARIZE,
    StageName.INTERPRET_ESCALATE,
)


class LaneName(str, Enum):
    OLLARMA_DEFAULT = "ollarma-default"
    SIDECAR_PARALLEL = "sidecar-parallel"
    FRONTIER_ONLY = "frontier-only"
    HUMAN_REVIEW_REQUIRED = "human-review-required"


class StageStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    BLOCKED = "blocked"


class BlockedClass(str, Enum):
    RETRYABLE = "retryable"
    NON_RETRYABLE = "non-retryable"
    ESCALATE_NOW = "escalate-now"


class RetryPolicy(str, Enum):
    NONE = "none"
    BOUNDED_LOCAL = "bounded-local"
    QUEUE_REPLAY = "queue-replay"
    HUMAN_RESET = "human-reset"


class ReceiptOutputKind(str, Enum):
    MANIFEST = "manifest"
    RESULTS = "results"
    REPORT = "report"
    CHECKPOINT = "checkpoint"
    BUNDLE = "bundle"
    NOTE = "note"


class ReceiptOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    kind: ReceiptOutputKind

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("output path must be non-empty")
        return normalized


class StageReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    receipt_id: Optional[str] = None
    contract_version: str = DEFAULT_EXECUTION_CONTRACT_VERSION
    run_id: str
    stage: StageName
    phase: str
    wave: str
    lane: LaneName
    required_inputs: list[str] = Field(min_length=1)
    immutable_inputs_hash: str
    outputs: list[ReceiptOutput]
    status: StageStatus
    blocked_class: Optional[BlockedClass] = None
    resume_point: Union[str, dict[str, Any]]
    retry_policy: RetryPolicy
    escalation_trigger: Optional[str]
    upstream_receipts: list[str]

    @field_validator("contract_version")
    @classmethod
    def _validate_contract_version(cls, value: str) -> str:
        normalized = value.strip()
        if normalized not in SUPPORTED_CONTRACT_VERSIONS:
            raise ValueError(f"unsupported contract_version '{value}'")
        return normalized

    @field_validator("run_id", "phase", "wave")
    @classmethod
    def _validate_non_empty(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must be non-empty")
        return normalized

    @field_validator("required_inputs", "upstream_receipts")
    @classmethod
    def _validate_relpaths(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item for item in normalized):
            raise ValueError("list entries must be non-empty strings")
        return normalized

    @field_validator("immutable_inputs_hash")
    @classmethod
    def _validate_hash(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.startswith("sha256:"):
            raise ValueError("immutable_inputs_hash must start with 'sha256:'")
        digest = normalized.removeprefix("sha256:")
        if len(digest) < 6:
            raise ValueError("immutable_inputs_hash digest is too short")
        return normalized

    @model_validator(mode="after")
    def _validate_blocked_state(self) -> "StageReceipt":
        if self.status == StageStatus.BLOCKED and self.blocked_class is None:
            raise ValueError("blocked_class is required when status is 'blocked'")
        if self.status != StageStatus.BLOCKED and self.blocked_class is not None:
            raise ValueError("blocked_class is only allowed when status is 'blocked'")
        return self


def validate_portfolio_role(value: Optional[str]) -> Optional[str]:
    """Validate one adapter portfolio role."""
    if value is None:
        return None
    normalized = value.strip()
    if normalized not in SUPPORTED_PORTFOLIO_ROLES:
        raise ValueError(f"unsupported portfolio_role '{value}'")
    return normalized


def normalize_immutable_hash_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize immutable-hash payloads and reject bulky mutable runtime state."""
    if not isinstance(payload, dict):
        raise ValueError("immutable hash payload must be a mapping")

    def _normalize(value: Any) -> Any:
        if isinstance(value, dict):
            normalized: dict[str, Any] = {}
            for key, item in value.items():
                normalized_key = str(key).strip()
                if normalized_key in _BULKY_MUTABLE_HASH_KEYS:
                    raise ValueError(
                        f"bulky or mutable runtime field '{normalized_key}' is not allowed in immutable hash payload"
                    )
                if normalized_key in _RUNTIME_HOST_CONTROL_KEYS:
                    raise ValueError(
                        f"runtime host control field '{normalized_key}' is outside the execution contract boundary"
                    )
                normalized[normalized_key] = _normalize(item)
            return normalized
        if isinstance(value, list):
            return [_normalize(item) for item in value]
        return value

    return _normalize(payload)


def build_immutable_inputs_hash(payload: dict[str, Any]) -> str:
    """Return the canonical immutable input hash for a receipt payload fragment."""
    normalized = normalize_immutable_hash_payload(payload)
    return f"sha256:{hash_payload(normalized)}"
