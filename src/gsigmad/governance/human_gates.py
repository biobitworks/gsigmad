"""Shared human review gate helpers for promotions, overrides, and exceptions."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _non_empty(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("value must be non-empty")
    return normalized


class HumanGateKind(str, Enum):
    PROMOTION = "promotion"
    CANON_OVERRIDE = "canon-override"
    POLICY_EXCEPTION = "policy-exception"


class HumanReviewGate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate_id: str
    gate_kind: HumanGateKind
    subject: str
    authority: Optional[str] = None
    approved: bool
    justification: Optional[str] = None
    evidence_paths: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_utc_now)

    @field_validator("gate_id", "subject")
    @classmethod
    def _validate_non_empty_fields(cls, value: str) -> str:
        return _non_empty(value)

    @field_validator("evidence_paths")
    @classmethod
    def _validate_evidence_paths(cls, value: list[str]) -> list[str]:
        return [_non_empty(item) for item in value]

    @model_validator(mode="after")
    def _validate_requirements(self) -> "HumanReviewGate":
        if self.gate_kind in {HumanGateKind.CANON_OVERRIDE, HumanGateKind.POLICY_EXCEPTION} and not (
            self.justification and self.justification.strip()
        ):
            raise ValueError("justification is required for override and policy-exception gates")
        if self.gate_kind == HumanGateKind.POLICY_EXCEPTION and not self.evidence_paths:
            raise ValueError("policy-exception gates require evidence_paths")
        return self


def build_promotion_gate(authority: Optional[str], *, subject: str = "hypothesis-promotion") -> HumanReviewGate:
    normalized = authority.strip() if authority else None
    approved = normalized == "phase20-local-text-classifier-v1"
    return HumanReviewGate.model_validate(
        {
            "gate_id": f"GATE-PROMOTION-{normalized or 'UNRATIFIED'}",
            "gate_kind": HumanGateKind.PROMOTION,
            "subject": subject,
            "authority": normalized,
            "approved": approved,
        }
    )


def build_canon_override_gate(
    *,
    subject: str,
    justification: str,
    authority: Optional[str] = None,
) -> HumanReviewGate:
    return HumanReviewGate.model_validate(
        {
            "gate_id": f"GATE-OVERRIDE-{subject}",
            "gate_kind": HumanGateKind.CANON_OVERRIDE,
            "subject": subject,
            "authority": authority,
            "approved": True,
            "justification": justification,
        }
    )


def build_policy_exception_gate(
    *,
    subject: str,
    justification: str,
    evidence_paths: list[str],
    authority: Optional[str] = None,
) -> HumanReviewGate:
    return HumanReviewGate.model_validate(
        {
            "gate_id": f"GATE-EXCEPTION-{subject}",
            "gate_kind": HumanGateKind.POLICY_EXCEPTION,
            "subject": subject,
            "authority": authority,
            "approved": True,
            "justification": justification,
            "evidence_paths": evidence_paths,
        }
    )


def resolve_promotion_gate(
    exp_record: dict,
    *,
    ratified_authority: str,
) -> dict[str, Union[str, bool, None]]:
    for raw_gate in exp_record.get("human_review_gates", []):
        gate = HumanReviewGate.model_validate(raw_gate)
        if gate.gate_kind != HumanGateKind.PROMOTION:
            continue
        return {
            "approved": gate.approved and gate.authority == ratified_authority,
            "authority": gate.authority,
        }

    authority = exp_record.get("promotion_authority")
    return {
        "approved": authority == ratified_authority,
        "authority": authority,
    }
