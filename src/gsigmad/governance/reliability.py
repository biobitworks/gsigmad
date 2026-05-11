"""Append-only blocked-lifecycle and dead-letter helpers."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gsigmad.governance.execution_contract import BlockedClass, RetryPolicy, StageName, StageReceipt, StageStatus


class BlockedRouteAction(str, Enum):
    RETRY_WAVE = "retry-wave"
    REQUIRE_HUMAN_REVIEW = "require-human-review"
    FRONTIER_HANDOFF = "frontier-handoff"


ROUTE_ACTION_BY_BLOCKED_CLASS: dict[BlockedClass, BlockedRouteAction] = {
    BlockedClass.RETRYABLE: BlockedRouteAction.RETRY_WAVE,
    BlockedClass.NON_RETRYABLE: BlockedRouteAction.REQUIRE_HUMAN_REVIEW,
    BlockedClass.ESCALATE_NOW: BlockedRouteAction.FRONTIER_HANDOFF,
}


class BlockedLifecycleEventKind(str, Enum):
    BLOCKED = "blocked"
    RETRY_SCHEDULED = "retry-scheduled"
    DEAD_LETTERED = "dead-lettered"
    REVIEWED = "reviewed"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _non_empty(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("value must be non-empty")
    return normalized


class BlockedLifecycleEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    source_receipt_id: str
    run_id: str
    phase: str
    wave: str
    stage: StageName
    blocked_class: BlockedClass
    route_action: BlockedRouteAction
    event_kind: BlockedLifecycleEventKind
    reason: str
    created_at: str = Field(default_factory=_utc_now)

    @field_validator("event_id", "source_receipt_id", "run_id", "phase", "wave", "reason")
    @classmethod
    def _validate_non_empty(cls, value: str) -> str:
        return _non_empty(value)

    @model_validator(mode="after")
    def _validate_route(self) -> "BlockedLifecycleEvent":
        expected = ROUTE_ACTION_BY_BLOCKED_CLASS[self.blocked_class]
        if self.route_action != expected:
            raise ValueError(
                f"{self.blocked_class.value} blocked events must route via {expected.value}"
            )
        return self


class DeadLetterReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dead_letter_id: str
    source_receipt_id: str
    run_id: str
    phase: str
    wave: str
    stage: StageName
    blocked_class: BlockedClass
    route_action: BlockedRouteAction
    retry_policy: RetryPolicy
    reason: str
    evidence_paths: list[str] = Field(min_length=1)
    queue_entry_id: Optional[str] = None
    created_at: str = Field(default_factory=_utc_now)

    @field_validator(
        "dead_letter_id",
        "source_receipt_id",
        "run_id",
        "phase",
        "wave",
        "reason",
    )
    @classmethod
    def _validate_non_empty(cls, value: str) -> str:
        return _non_empty(value)

    @field_validator("evidence_paths")
    @classmethod
    def _validate_paths(cls, values: list[str]) -> list[str]:
        normalized = [_non_empty(value) for value in values]
        return normalized

    @model_validator(mode="after")
    def _validate_route(self) -> "DeadLetterReceipt":
        expected = ROUTE_ACTION_BY_BLOCKED_CLASS[self.blocked_class]
        if self.route_action != expected:
            raise ValueError(
                f"{self.blocked_class.value} dead-letter receipts must route via {expected.value}"
            )
        return self


def build_dead_letter_receipt(
    receipt: Union[StageReceipt, dict[str, Any]],
    *,
    reason: str,
    evidence_paths: list[str],
    queue_entry_id: Optional[str] = None,
) -> DeadLetterReceipt:
    """Build a dead-letter receipt from one blocked canonical stage receipt."""
    model = receipt if isinstance(receipt, StageReceipt) else StageReceipt.model_validate(receipt)
    if model.status != StageStatus.BLOCKED or model.blocked_class is None:
        raise ValueError("dead-letter receipts require a blocked StageReceipt with blocked_class")

    source_receipt_id = model.receipt_id or f"RECEIPT-{model.run_id}"
    dead_letter_id = f"DEADLETTER-{source_receipt_id}"
    return DeadLetterReceipt.model_validate(
        {
            "dead_letter_id": dead_letter_id,
            "source_receipt_id": source_receipt_id,
            "run_id": model.run_id,
            "phase": model.phase,
            "wave": model.wave,
            "stage": model.stage,
            "blocked_class": model.blocked_class,
            "route_action": ROUTE_ACTION_BY_BLOCKED_CLASS[model.blocked_class],
            "retry_policy": model.retry_policy,
            "reason": reason,
            "evidence_paths": evidence_paths,
            "queue_entry_id": queue_entry_id,
        }
    )


def write_blocked_lifecycle_event(
    project_root: Union[Path, str],
    event: Union[BlockedLifecycleEvent, dict[str, Any]],
) -> str:
    """Append one blocked-lifecycle event under `.gsigmad/queue/blocked-lifecycle.jsonl`."""
    root = Path(project_root).resolve()
    model = event if isinstance(event, BlockedLifecycleEvent) else BlockedLifecycleEvent.model_validate(event)
    target = root / ".gsigmad" / "queue" / "blocked-lifecycle.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(model.model_dump(mode="json"), ensure_ascii=False) + "\n")
    return target.relative_to(root).as_posix()


def write_dead_letter_receipt(
    project_root: Union[Path, str],
    receipt: Union[DeadLetterReceipt, dict[str, Any]],
) -> str:
    """Write one append-only dead-letter receipt under `.gsigmad/dead_letters/<run_id>/`."""
    root = Path(project_root).resolve()
    model = receipt if isinstance(receipt, DeadLetterReceipt) else DeadLetterReceipt.model_validate(receipt)
    target_dir = root / ".gsigmad" / "dead_letters" / model.run_id
    target_dir.mkdir(parents=True, exist_ok=True)
    next_index = len(sorted(target_dir.glob("*.yaml"))) + 1
    target = target_dir / f"{next_index:03d}-dead-letter.yaml"
    with target.open("x", encoding="utf-8") as handle:
        yaml.safe_dump(model.model_dump(mode="json"), handle, sort_keys=False)
    return target.relative_to(root).as_posix()
