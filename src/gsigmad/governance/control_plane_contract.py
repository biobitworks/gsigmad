"""Phase 32 control-plane contract helpers and closed schema surfaces."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Iterable, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TruthLayer(str, Enum):
    LIVE = "live"
    DURABLE = "durable"


class ControlPlaneDecision(str, Enum):
    ADOPT = "adopt"
    ADAPT = "adapt"
    REJECT = "reject"


class RepoClass(str, Enum):
    ACTIVE = "active"
    LEGACY = "legacy"
    FROZEN = "frozen"


class ControlPlaneOwner(str, Enum):
    GSIGMAD = "gsigmad"
    WATCHTOWER = "watchtower"
    OLLARMA = "ollarma"
    ANTIGENCE = "antigence"
    OVERWATCH = "overwatch"
    SEEDGRAPH = "seedgraph"
    HUMAN = "human"


class OwnershipSurface(str, Enum):
    PLANNING_ONTOLOGY = "planning-ontology"
    OPERATOR_VIEW = "operator-view"
    SWARM_BROKER = "swarm-broker"
    REVIEW_ESCALATION = "review-escalation"
    DURABLE_TRUTH = "durable-truth"
    CONTENT_IDENTITY = "content-identity"


class CanonicalEntityType(str, Enum):
    PROJECT = "Project"
    MILESTONE = "Milestone"
    PHASE = "Phase"
    PLAN = "Plan"
    WAVE = "Wave"
    TASK = "Task"
    NEXT_STEP = "NextStep"
    WORK_LEASE = "WorkLease"
    SWARM_RUN = "SwarmRun"
    LANE_RUN = "LaneRun"
    RUN = "Run"
    STAGE_RECEIPT = "StageReceipt"
    OFFLOAD_REQUEST = "OffloadRequest"
    OFFLOAD_RECEIPT = "OffloadReceipt"
    SIDECAR_REVIEW_BUNDLE = "SidecarReviewBundle"
    ESCALATION_BUNDLE = "EscalationBundle"
    REVIEW_VERDICT = "ReviewVerdict"
    HUMAN_DECISION = "HumanDecision"
    REPLAY_RUN = "ReplayRun"
    RESUME_CURSOR = "ResumeCursor"
    REVERIFICATION_RECEIPT = "ReverificationReceipt"
    BLOCKED_LIFECYCLE_EVENT = "BlockedLifecycleEvent"
    DEAD_LETTER_RECEIPT = "DeadLetterReceipt"
    ARTIFACT = "Artifact"
    CLAIM = "Claim"
    RESOURCE = "Resource"
    DEPENDENCY = "Dependency"
    ACTOR = "Actor"
    BOUNDARY_SURFACE = "BoundarySurface"
    KG_INGESTION_RECEIPT = "KGIngestionReceipt"


CANONICAL_ENTITY_TYPES = {item.value for item in CanonicalEntityType}


class CanonicalEdgeType(str, Enum):
    CONTAINS = "contains"
    PLANNED_BY = "planned_by"
    DEPENDS_ON = "depends_on"
    REQUIRES_RECEIPT = "requires_receipt"
    EXECUTED_IN = "executed_in"
    HAS_LANE = "has_lane"
    PRODUCED = "produced"
    GENERATED_BY = "generated_by"
    DERIVED_FROM = "derived_from"
    REVIEWED_BY = "reviewed_by"
    ESCALATED_TO = "escalated_to"
    APPROVED_BY = "approved_by"
    GATES = "gates"
    BLOCKS = "blocks"
    RESOLVES = "resolves"
    SUPERSEDES = "supersedes"
    CORRECTS = "corrects"
    REPLAYS = "replays"
    RESUMES_FROM = "resumes_from"
    CLAIMS_ABOUT = "claims_about"
    CITES = "cites"
    ATTACHED_TO = "attached_to"
    SURFACED_IN = "surfaced_in"
    LEASED_BY = "leased_by"
    OWNED_BY = "owned_by"
    INGESTED_AS = "ingested_as"


CANONICAL_EDGE_TYPES = {item.value for item in CanonicalEdgeType}


class DurableReceiptType(str, Enum):
    STAGE_RECEIPT = "StageReceipt"
    LEASE_RECEIPT = "LeaseReceipt"
    SWARM_RUN_RECEIPT = "SwarmRunReceipt"
    LANE_RUN_RECEIPT = "LaneRunReceipt"
    REVIEW_VERDICT = "ReviewVerdict"
    HUMAN_DECISION = "HumanDecision"
    REPLAY_IDENTITY = "ReplayIdentity"
    REVERIFICATION_RECEIPT = "ReverificationReceipt"
    BLOCKED_LIFECYCLE_EVENT = "BlockedLifecycleEvent"
    DEAD_LETTER_RECEIPT = "DeadLetterReceipt"
    KG_INGESTION_RECEIPT = "KGIngestionReceipt"


DURABLE_RECEIPT_TYPES = {item.value for item in DurableReceiptType}


class LiveEventType(str, Enum):
    HEARTBEAT = "heartbeat"
    PROGRESS_TICK = "progress-tick"
    UI_CACHE_UPDATE = "ui-cache-update"
    HEALTH_POLL = "health-poll"
    PROVIDER_STREAM_EVENT = "provider-stream-event"
    QUEUE_INTERNAL = "queue-internal"


class LeaseScope(str, Enum):
    CHAT = "chat"
    AGENT = "agent"
    EXECUTION = "execution"
    REVIEW = "review"
    OPERATOR_APPROVAL = "operator-approval"


class LeaseReleaseReason(str, Enum):
    COMPLETED = "completed"
    BLOCKED = "blocked"
    ESCALATED = "escalated"
    ABANDONED = "abandoned"
    TIMEOUT = "timeout"
    SUPERSEDED = "superseded"


class OwnershipBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    surface: OwnershipSurface
    owner: ControlPlaneOwner
    truth_layer: TruthLayer
    notes: Optional[str] = None


_DEFAULT_OWNERSHIP_BINDINGS = (
    OwnershipBinding(
        surface=OwnershipSurface.PLANNING_ONTOLOGY,
        owner=ControlPlaneOwner.GSIGMAD,
        truth_layer=TruthLayer.DURABLE,
        notes="gsigmad owns the one planning ontology and workflow vocabulary.",
    ),
    OwnershipBinding(
        surface=OwnershipSurface.OPERATOR_VIEW,
        owner=ControlPlaneOwner.WATCHTOWER,
        truth_layer=TruthLayer.LIVE,
        notes="Watchtower renders operator projections and approved intents only.",
    ),
    OwnershipBinding(
        surface=OwnershipSurface.SWARM_BROKER,
        owner=ControlPlaneOwner.OLLARMA,
        truth_layer=TruthLayer.LIVE,
        notes="Ollarma owns swarm brokering and bounded execution under leases.",
    ),
    OwnershipBinding(
        surface=OwnershipSurface.REVIEW_ESCALATION,
        owner=ControlPlaneOwner.ANTIGENCE,
        truth_layer=TruthLayer.DURABLE,
        notes="Antigence owns structured review verdicts and escalation outputs.",
    ),
    OwnershipBinding(
        surface=OwnershipSurface.DURABLE_TRUTH,
        owner=ControlPlaneOwner.OVERWATCH,
        truth_layer=TruthLayer.DURABLE,
        notes="Overwatch is the sole durable portfolio truth and lease authority.",
    ),
    OwnershipBinding(
        surface=OwnershipSurface.CONTENT_IDENTITY,
        owner=ControlPlaneOwner.SEEDGRAPH,
        truth_layer=TruthLayer.DURABLE,
        notes="SeedGraph may harden content identity without replacing Overwatch truth.",
    ),
)


def _get_surface_owner(
    surface: OwnershipSurface,
    *,
    bindings: Iterable[OwnershipBinding],
) -> ControlPlaneOwner:
    """Return the canonical owner for one contract surface."""
    for binding in bindings:
        if binding.surface is surface:
            return binding.owner
    raise KeyError(surface.value)


def validate_ownership_matrix(bindings: Iterable[OwnershipBinding]) -> tuple[OwnershipBinding, ...]:
    """Validate the closed ownership matrix."""
    ordered = tuple(bindings)
    seen: set[OwnershipSurface] = set()
    for binding in ordered:
        if binding.surface in seen:
            raise ValueError(f"duplicate durable owner declared for surface '{binding.surface.value}'")
        seen.add(binding.surface)

    missing = {surface for surface in OwnershipSurface if surface not in seen}
    if missing:
        missing_names = ", ".join(sorted(surface.value for surface in missing))
        raise ValueError(f"ownership matrix missing surfaces: {missing_names}")

    if (
        _get_surface_owner(OwnershipSurface.DURABLE_TRUTH, bindings=ordered)
        is not ControlPlaneOwner.OVERWATCH
    ):
        raise ValueError("Overwatch must remain the sole durable portfolio truth owner")
    return ordered


OWNERSHIP_MATRIX = validate_ownership_matrix(_DEFAULT_OWNERSHIP_BINDINGS)


def get_surface_owner(surface: OwnershipSurface) -> ControlPlaneOwner:
    """Return the canonical owner from the default matrix."""
    return _get_surface_owner(surface, bindings=OWNERSHIP_MATRIX)


class LiveEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    truth_layer: TruthLayer = TruthLayer.LIVE
    event_id: str
    event_type: LiveEventType
    owner: ControlPlaneOwner
    subject_type: str
    subject_id: str
    occurred_at: datetime

    @field_validator("event_id", "event_type", "subject_type", "subject_id")
    @classmethod
    def _validate_non_empty(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must be non-empty")
        return normalized

    @field_validator("truth_layer")
    @classmethod
    def _validate_truth_layer(cls, value: TruthLayer) -> TruthLayer:
        if value is not TruthLayer.LIVE:
            raise ValueError("truth_layer must be 'live' for LiveEvent")
        return value


class DurableReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    truth_layer: TruthLayer = TruthLayer.DURABLE
    receipt_id: str
    receipt_type: DurableReceiptType
    portfolio_entity_id: str
    owner: ControlPlaneOwner
    actor: str
    subject_type: str
    subject_id: str
    event_time: datetime
    status: str
    reason_code: str
    idempotency_key: str
    parent_receipt_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    content_hash: str
    signature: Optional[str] = None
    lease_id: Optional[str] = None
    fencing_token: Optional[str] = None

    @field_validator(
        "receipt_id",
        "portfolio_entity_id",
        "actor",
        "subject_type",
        "subject_id",
        "status",
        "reason_code",
        "idempotency_key",
    )
    @classmethod
    def _validate_non_empty(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must be non-empty")
        return normalized

    @field_validator("content_hash")
    @classmethod
    def _validate_hash(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.startswith("sha256:"):
            raise ValueError("content_hash must start with 'sha256:'")
        if len(normalized.removeprefix("sha256:")) < 6:
            raise ValueError("content_hash digest is too short")
        return normalized

    @field_validator("truth_layer")
    @classmethod
    def _validate_truth_layer(cls, value: TruthLayer) -> TruthLayer:
        if value is not TruthLayer.DURABLE:
            raise ValueError("truth_layer must be 'durable' for DurableReceipt")
        return value

    @model_validator(mode="after")
    def _validate_lease_pairing(self) -> "DurableReceipt":
        if bool(self.lease_id) != bool(self.fencing_token):
            raise ValueError("lease_id and fencing_token must be supplied together")
        return self


class WorkLease(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    lease_id: str
    task_id: str
    lease_scope: LeaseScope
    holder_system: str
    holder_id: str
    fencing_token: str
    acquired_at: datetime
    expires_at: datetime
    heartbeat_at: datetime
    intent_summary: str
    allowed_outputs: list[str] = Field(default_factory=list)
    release_policy: LeaseReleaseReason

    @field_validator(
        "lease_id",
        "task_id",
        "holder_system",
        "holder_id",
        "fencing_token",
        "intent_summary",
        "release_policy",
    )
    @classmethod
    def _validate_non_empty(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must be non-empty")
        return normalized

    @model_validator(mode="after")
    def _validate_temporal_bounds(self) -> "WorkLease":
        if self.expires_at <= self.acquired_at:
            raise ValueError("expires_at must be later than acquired_at")
        if self.heartbeat_at < self.acquired_at:
            raise ValueError("heartbeat_at cannot precede acquired_at")
        return self


class ControlPlaneGuardrail(str, Enum):
    SECOND_PLANNER = "second-planner"
    SHADOW_QUEUE = "shadow-queue"
    DUPLICATE_OWNERSHIP = "duplicate-ownership"
    WATCHTOWER_WRITEBACK = "watchtower-writeback"
    FROZEN_MUTATION = "frozen-repo-mutation"


CONTROL_PLANE_DECISIONS = {item.value for item in ControlPlaneDecision}
CONTROL_PLANE_GUARDRAILS = {item.value for item in ControlPlaneGuardrail}
CONTROL_PLANE_LIVE_STATE_OWNERS = frozenset(
    {
        ControlPlaneOwner.WATCHTOWER,
        ControlPlaneOwner.OLLARMA,
        ControlPlaneOwner.ANTIGENCE,
    }
)
DIRECT_DURABLE_DECISION_TYPES = frozenset({DurableReceiptType.HUMAN_DECISION.value})


MUTATING_COMMANDS = frozenset(
    {
        "register",
        "run",
        "redteam",
        "classify",
        "drift",
        "fair",
        "export",
        "report",
        "pause",
        "resume",
    }
)


def validate_control_plane_guardrails(payload: dict[str, object]) -> dict[str, object]:
    """Reject second-planner, shadow-queue, and writeback drift payloads."""
    normalized = dict(payload)
    if normalized.get("planner") not in (None, "gsigmad"):
        raise ValueError("control-plane payloads must not introduce a second planner")
    if normalized.get("queue") not in (None, "repo-local", "none"):
        raise ValueError("control-plane payloads must not introduce a shadow queue")
    if normalized.get("watchtower_writeback") is True:
        raise ValueError("Watchtower writeback is outside the control-plane contract")
    if normalized.get("duplicate_owner") is True:
        raise ValueError("control-plane payloads must not express duplicate ownership")
    return normalized


def validate_work_lease_payload(payload: dict[str, object]) -> dict[str, object]:
    """Reject lease payloads that reintroduce queue or owner duplication."""
    normalized = dict(payload)
    forbidden = sorted(
        key
        for key in (
            "queue",
            "queue_id",
            "owner",
            "owner_id",
            "shadow_queue",
            "secondary_owner",
            "queue_position",
            "inbox_rank",
            "chat_claim",
        )
        if key in normalized
    )
    if forbidden:
        raise ValueError(
            "lease authority must not be expressed through queue or duplicate ownership fields: "
            + ", ".join(forbidden)
        )
    return validate_control_plane_guardrails(normalized)


def validate_repo_class(value: Union[str, RepoClass, None]) -> Optional[str]:
    """Validate one repo adoption class."""
    if value is None:
        return None
    if isinstance(value, RepoClass):
        return value.value
    normalized = value.strip()
    if normalized not in {item.value for item in RepoClass}:
        raise ValueError(f"unsupported repo_class '{value}'")
    return normalized


def infer_repo_class(
    source: str,
    runtime_mode: str,
    explicit: Optional[str] = None,
) -> Optional[str]:
    """Infer a repo class when a manifest does not declare one."""
    normalized = validate_repo_class(explicit)
    if normalized is not None:
        return normalized
    if source == "native_gsigmad" or runtime_mode == "gsigmad":
        return RepoClass.ACTIVE.value
    if runtime_mode in {"legacy", "hybrid"}:
        return RepoClass.LEGACY.value
    return None
