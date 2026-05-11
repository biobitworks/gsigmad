"""Phase 33 helpers for state-layer, promotion, and lease-scope authority."""
from __future__ import annotations

from enum import Enum
from pathlib import PurePath
from typing import Optional, Union

from pydantic import BaseModel, ConfigDict

from gsigmad.governance.control_plane_contract import (
    DIRECT_DURABLE_DECISION_TYPES,
    DURABLE_RECEIPT_TYPES,
    ControlPlaneOwner,
    DurableReceiptType,
    LeaseScope,
    LiveEventType,
)
from gsigmad.governance.execution_contract import StageReceipt
from gsigmad.governance.human_gates import HumanReviewGate
from gsigmad.governance.reliability import BlockedLifecycleEvent, DeadLetterReceipt
from gsigmad.governance.replay import ReplayIdentity, ReverificationReceipt


class StateLayer(str, Enum):
    RUNTIME_LOCAL_LIVE = "runtime-local-live"
    REPO_LOCAL_DURABLE_EVIDENCE = "repo-local-durable-evidence"
    PROMOTABLE_DURABLE_FACT = "promotable-durable-fact"


class ClaimAuthority(str, Enum):
    ADVISORY = "advisory"
    RECEIPT_BACKED = "receipt-backed"
    DIRECT_DURABLE = "direct-durable"


class SystemStateBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    system: ControlPlaneOwner
    state_layer: StateLayer
    bounded_live_state_only: bool
    durable_truth_owner: bool = False


class LeaseScopeAuthority(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: LeaseScope
    reserves_context: bool
    may_execute: bool = False
    may_review: bool = False
    may_operator_approve: bool = False
    may_promote_truth: bool = False


PROMOTED_CLAIM_TYPE = "Claim"
PROMOTABLE_DURABLE_NAMES = frozenset(set(DURABLE_RECEIPT_TYPES) | {PROMOTED_CLAIM_TYPE})
EVIDENCE_ONLY_PATH_MARKERS = (
    "manifest",
    "diff",
    "retry",
    "queue",
    "cursor",
    "packet",
    "payload",
    "snapshot",
    "cache",
)

_SYSTEM_STATE_BINDINGS: dict[ControlPlaneOwner, SystemStateBinding] = {
    ControlPlaneOwner.GSIGMAD: SystemStateBinding(
        system=ControlPlaneOwner.GSIGMAD,
        state_layer=StateLayer.REPO_LOCAL_DURABLE_EVIDENCE,
        bounded_live_state_only=False,
    ),
    ControlPlaneOwner.WATCHTOWER: SystemStateBinding(
        system=ControlPlaneOwner.WATCHTOWER,
        state_layer=StateLayer.RUNTIME_LOCAL_LIVE,
        bounded_live_state_only=True,
    ),
    ControlPlaneOwner.OLLARMA: SystemStateBinding(
        system=ControlPlaneOwner.OLLARMA,
        state_layer=StateLayer.RUNTIME_LOCAL_LIVE,
        bounded_live_state_only=True,
    ),
    ControlPlaneOwner.ANTIGENCE: SystemStateBinding(
        system=ControlPlaneOwner.ANTIGENCE,
        state_layer=StateLayer.RUNTIME_LOCAL_LIVE,
        bounded_live_state_only=True,
    ),
    ControlPlaneOwner.OVERWATCH: SystemStateBinding(
        system=ControlPlaneOwner.OVERWATCH,
        state_layer=StateLayer.PROMOTABLE_DURABLE_FACT,
        bounded_live_state_only=False,
        durable_truth_owner=True,
    ),
    ControlPlaneOwner.SEEDGRAPH: SystemStateBinding(
        system=ControlPlaneOwner.SEEDGRAPH,
        state_layer=StateLayer.REPO_LOCAL_DURABLE_EVIDENCE,
        bounded_live_state_only=False,
    ),
    ControlPlaneOwner.HUMAN: SystemStateBinding(
        system=ControlPlaneOwner.HUMAN,
        state_layer=StateLayer.RUNTIME_LOCAL_LIVE,
        bounded_live_state_only=True,
    ),
}

_LEASE_SCOPE_AUTHORITIES: dict[LeaseScope, LeaseScopeAuthority] = {
    LeaseScope.CHAT: LeaseScopeAuthority(
        scope=LeaseScope.CHAT,
        reserves_context=True,
    ),
    LeaseScope.AGENT: LeaseScopeAuthority(
        scope=LeaseScope.AGENT,
        reserves_context=True,
    ),
    LeaseScope.EXECUTION: LeaseScopeAuthority(
        scope=LeaseScope.EXECUTION,
        reserves_context=False,
        may_execute=True,
    ),
    LeaseScope.REVIEW: LeaseScopeAuthority(
        scope=LeaseScope.REVIEW,
        reserves_context=False,
        may_review=True,
    ),
    LeaseScope.OPERATOR_APPROVAL: LeaseScopeAuthority(
        scope=LeaseScope.OPERATOR_APPROVAL,
        reserves_context=False,
        may_operator_approve=True,
        may_promote_truth=True,
    ),
}


def _normalize_owner(value: Union[ControlPlaneOwner, str]) -> ControlPlaneOwner:
    if isinstance(value, ControlPlaneOwner):
        return value
    return ControlPlaneOwner(value.strip())


def _normalize_scope(value: Union[LeaseScope, str]) -> LeaseScope:
    if isinstance(value, LeaseScope):
        return value
    return LeaseScope(value.strip())


def _normalize_durable_name(subject: object) -> Optional[str]:
    if isinstance(subject, DurableReceiptType):
        return subject.value
    if isinstance(subject, str):
        normalized = subject.strip()
        if normalized in PROMOTABLE_DURABLE_NAMES:
            return normalized
        return None
    if isinstance(subject, StageReceipt) or subject is StageReceipt:
        return DurableReceiptType.STAGE_RECEIPT.value
    if isinstance(subject, DeadLetterReceipt) or subject is DeadLetterReceipt:
        return DurableReceiptType.DEAD_LETTER_RECEIPT.value
    if isinstance(subject, ReplayIdentity) or subject is ReplayIdentity:
        return DurableReceiptType.REPLAY_IDENTITY.value
    if isinstance(subject, ReverificationReceipt) or subject is ReverificationReceipt:
        return DurableReceiptType.REVERIFICATION_RECEIPT.value
    if isinstance(subject, BlockedLifecycleEvent) or subject is BlockedLifecycleEvent:
        return DurableReceiptType.BLOCKED_LIFECYCLE_EVENT.value
    return None


def classify_live_event_type(value: Union[LiveEventType, str]) -> StateLayer:
    if isinstance(value, str):
        LiveEventType(value.strip())
    return StateLayer.RUNTIME_LOCAL_LIVE


def classify_receipt_type(value: Union[DurableReceiptType, str, object]) -> StateLayer:
    normalized = _normalize_durable_name(value)
    if normalized is None:
        raise ValueError(f"unsupported durable classification target: {value!r}")
    return StateLayer.PROMOTABLE_DURABLE_FACT


def classify_artifact_path(path: Union[str, PurePath]) -> StateLayer:
    normalized = PurePath(path).as_posix().lower()
    if any(marker in normalized for marker in EVIDENCE_ONLY_PATH_MARKERS):
        return StateLayer.REPO_LOCAL_DURABLE_EVIDENCE
    return StateLayer.REPO_LOCAL_DURABLE_EVIDENCE


def system_state_binding(owner: Union[ControlPlaneOwner, str]) -> SystemStateBinding:
    normalized = _normalize_owner(owner)
    return _SYSTEM_STATE_BINDINGS[normalized]


def is_promotable_durable(subject: object) -> bool:
    return _normalize_durable_name(subject) in PROMOTABLE_DURABLE_NAMES


def is_evidence_only_artifact(subject: object) -> bool:
    if isinstance(subject, (str, PurePath)):
        return classify_artifact_path(subject) is StateLayer.REPO_LOCAL_DURABLE_EVIDENCE
    if isinstance(subject, HumanReviewGate) or subject is HumanReviewGate:
        return True
    return False


def classify_claim_authority(
    origin: object,
    *,
    backed_by_receipt: bool = False,
) -> ClaimAuthority:
    normalized = _normalize_durable_name(origin)
    if normalized in DIRECT_DURABLE_DECISION_TYPES:
        return ClaimAuthority.DIRECT_DURABLE
    if backed_by_receipt:
        return ClaimAuthority.RECEIPT_BACKED
    return ClaimAuthority.ADVISORY


def is_advisory_intent(origin: object, *, backed_by_receipt: bool = False) -> bool:
    return classify_claim_authority(origin, backed_by_receipt=backed_by_receipt) is ClaimAuthority.ADVISORY


def lease_scope_authority(scope: Union[LeaseScope, str]) -> LeaseScopeAuthority:
    normalized = _normalize_scope(scope)
    return _LEASE_SCOPE_AUTHORITIES[normalized]
