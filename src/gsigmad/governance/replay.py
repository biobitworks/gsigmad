"""Append-only replay identity, diff, and re-verification helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from gsigmad.governance.escalation_bundles import EscalationBundle, build_blocked_diagnosis_bundle
from gsigmad.governance.execution_contract import BlockedClass, StageName, StageReceipt
from gsigmad.governance.receipts import load_stage_receipt, run_receipts_dir


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _non_empty(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("value must be non-empty")
    return normalized


class ReplayIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    replay_id: str
    exp_id: str
    baseline_results_id: str
    replay_results_id: str
    baseline_receipt_run_id: Optional[str] = None
    replay_receipt_run_id: Optional[str] = None
    baseline_manifest_path: Optional[str] = None
    replay_manifest_path: Optional[str] = None
    created_at: str = Field(default_factory=_utc_now)

    @field_validator("replay_id", "exp_id", "baseline_results_id", "replay_results_id")
    @classmethod
    def _validate_non_empty(cls, value: str) -> str:
        return _non_empty(value)


class ResumeCursor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cursor_id: str
    replay_id: str
    exp_id: str
    source_receipt_id: str
    stage: StageName
    resume_point: Union[str, dict[str, Any]]
    blocked_class: Optional[BlockedClass] = None
    reverification_status: str
    created_at: str = Field(default_factory=_utc_now)

    @field_validator("cursor_id", "replay_id", "exp_id", "source_receipt_id", "reverification_status")
    @classmethod
    def _validate_non_empty(cls, value: str) -> str:
        return _non_empty(value)


class ReverificationReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    replay_id: str
    exp_id: str
    baseline_results_id: str
    replay_results_id: str
    manifest_diff_path: str
    receipt_diff_path: str
    resume_cursor_path: Optional[str] = None
    reverification_status: str
    blocked_class: Optional[str] = None
    reasons: list[dict[str, Any]]
    created_at: str = Field(default_factory=_utc_now)

    @field_validator(
        "replay_id",
        "exp_id",
        "baseline_results_id",
        "replay_results_id",
        "manifest_diff_path",
        "receipt_diff_path",
        "reverification_status",
    )
    @classmethod
    def _validate_non_empty(cls, value: str) -> str:
        return _non_empty(value)


def replay_root(project_root: Union[Path, str], exp_id: str) -> Path:
    root = Path(project_root).resolve()
    return root / ".gsigmad" / "replays" / exp_id


def build_replay_identity(
    *,
    exp_id: str,
    baseline_results_id: str,
    replay_results_id: str,
    baseline_receipt_run_id: Optional[str],
    replay_receipt_run_id: Optional[str],
    baseline_manifest_path: Optional[str],
    replay_manifest_path: Optional[str],
) -> ReplayIdentity:
    replay_id = f"REPLAY-{exp_id}-{replay_results_id}"
    return ReplayIdentity.model_validate(
        {
            "replay_id": replay_id,
            "exp_id": exp_id,
            "baseline_results_id": baseline_results_id,
            "replay_results_id": replay_results_id,
            "baseline_receipt_run_id": baseline_receipt_run_id,
            "replay_receipt_run_id": replay_receipt_run_id,
            "baseline_manifest_path": baseline_manifest_path,
            "replay_manifest_path": replay_manifest_path,
        }
    )


def build_resume_cursor(
    *,
    replay_id: str,
    exp_id: str,
    source_receipt_id: str,
    stage: StageName,
    resume_point: Union[str, dict[str, Any]],
    reverification_status: str,
    blocked_class: Optional[BlockedClass] = None,
) -> ResumeCursor:
    return ResumeCursor.model_validate(
        {
            "cursor_id": f"CURSOR-{replay_id}",
            "replay_id": replay_id,
            "exp_id": exp_id,
            "source_receipt_id": source_receipt_id,
            "stage": stage,
            "resume_point": resume_point,
            "blocked_class": blocked_class,
            "reverification_status": reverification_status,
        }
    )


def diff_receipt_runs(
    project_root: Union[Path, str],
    *,
    baseline_run_id: str,
    candidate_run_id: str,
) -> dict[str, Any]:
    """Compare two canonical receipt runs for replay-grade differences."""
    root = Path(project_root).resolve()
    baseline_dir = run_receipts_dir(root, baseline_run_id)
    candidate_dir = run_receipts_dir(root, candidate_run_id)

    baseline_receipts = _receipt_map(root, baseline_dir)
    candidate_receipts = _receipt_map(root, candidate_dir)

    reasons: list[dict[str, Any]] = []
    stages = sorted(set(baseline_receipts) | set(candidate_receipts), key=lambda item: item.value)
    for stage in stages:
        baseline = baseline_receipts.get(stage)
        candidate = candidate_receipts.get(stage)
        if baseline is None or candidate is None:
            reasons.append({"code": "MISSING_STAGE_RECEIPT", "stage": stage.value})
            continue
        if baseline.resume_point != candidate.resume_point:
            reasons.append(
                {
                    "code": "RESUME_POINT_CHANGED",
                    "stage": stage.value,
                    "baseline": baseline.resume_point,
                    "candidate": candidate.resume_point,
                }
            )
        if baseline.status != candidate.status:
            reasons.append(
                {
                    "code": "STAGE_STATUS_CHANGED",
                    "stage": stage.value,
                    "baseline": baseline.status.value,
                    "candidate": candidate.status.value,
                }
            )
        if baseline.blocked_class != candidate.blocked_class:
            reasons.append(
                {
                    "code": "BLOCKED_CLASS_CHANGED",
                    "stage": stage.value,
                    "baseline": baseline.blocked_class.value if baseline.blocked_class else None,
                    "candidate": candidate.blocked_class.value if candidate.blocked_class else None,
                }
            )

    return {
        "pass": not reasons,
        "baseline_run_id": baseline_run_id,
        "candidate_run_id": candidate_run_id,
        "reasons": reasons,
    }


def diagnose_replay_divergence(reasons: list[dict[str, Any]]) -> dict[str, Any]:
    """Normalize replay divergence into a governed re-verification status."""
    codes = {reason.get("code") for reason in reasons}
    if not reasons:
        return {"reverification_status": "replay-ok", "blocked_class": None}
    if "RESUME_POINT_CHANGED" in codes or "MISSING_STAGE_RECEIPT" in codes:
        return {
            "reverification_status": "resume-available",
            "blocked_class": BlockedClass.RETRYABLE.value,
        }
    if "STAGE_STATUS_CHANGED" in codes and any(
        reason.get("stage") == StageName.INTERPRET_ESCALATE.value for reason in reasons
    ):
        return {
            "reverification_status": "escalate-now",
            "blocked_class": BlockedClass.ESCALATE_NOW.value,
        }
    return {
        "reverification_status": "review-required",
        "blocked_class": BlockedClass.NON_RETRYABLE.value,
    }


def build_replay_escalation_bundle(
    *,
    replay_id: str,
    run_id: str,
    receipt_ids: list[str],
    evidence_paths: list[str],
    diagnosis: dict[str, Any],
    source_stage: StageName = StageName.SUMMARIZE,
    wave_id: str = "replay",
) -> EscalationBundle:
    blocked_class = diagnosis.get("blocked_class") or BlockedClass.NON_RETRYABLE.value
    reverification_status = diagnosis.get("reverification_status")
    request_summary = f"Review replay divergence for {replay_id}."
    return build_blocked_diagnosis_bundle(
        run_id=run_id,
        wave_id=wave_id,
        source_stage=source_stage,
        receipt_ids=receipt_ids,
        evidence_paths=evidence_paths,
        request_summary=request_summary,
        blocked_class=BlockedClass(blocked_class),
        reverification_status=reverification_status,
    )


def write_replay_identity(
    project_root: Union[Path, str],
    identity: Union[ReplayIdentity, dict[str, Any]],
) -> str:
    root = Path(project_root).resolve()
    model = identity if isinstance(identity, ReplayIdentity) else ReplayIdentity.model_validate(identity)
    target_dir = replay_root(root, model.exp_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{model.replay_results_id}.identity.yaml"
    with target.open("x", encoding="utf-8") as handle:
        yaml.safe_dump(model.model_dump(mode="json"), handle, sort_keys=False)
    return target.relative_to(root).as_posix()


def write_resume_cursor(
    project_root: Union[Path, str],
    cursor: Union[ResumeCursor, dict[str, Any]],
) -> str:
    root = Path(project_root).resolve()
    model = cursor if isinstance(cursor, ResumeCursor) else ResumeCursor.model_validate(cursor)
    target_dir = replay_root(root, model.exp_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{model.replay_id}.cursor.yaml"
    with target.open("x", encoding="utf-8") as handle:
        yaml.safe_dump(model.model_dump(mode="json"), handle, sort_keys=False)
    return target.relative_to(root).as_posix()


def write_manifest_diff(
    project_root: Union[Path, str],
    *,
    exp_id: str,
    replay_results_id: str,
    payload: dict[str, Any],
) -> str:
    return _write_yaml_artifact(
        project_root,
        exp_id=exp_id,
        replay_results_id=replay_results_id,
        suffix="manifest-diff",
        payload=payload,
    )


def write_receipt_diff(
    project_root: Union[Path, str],
    *,
    exp_id: str,
    replay_results_id: str,
    payload: dict[str, Any],
) -> str:
    return _write_yaml_artifact(
        project_root,
        exp_id=exp_id,
        replay_results_id=replay_results_id,
        suffix="receipt-diff",
        payload=payload,
    )


def write_reverification_receipt(
    project_root: Union[Path, str],
    receipt: Union[ReverificationReceipt, dict[str, Any]],
) -> str:
    root = Path(project_root).resolve()
    model = receipt if isinstance(receipt, ReverificationReceipt) else ReverificationReceipt.model_validate(receipt)
    target_dir = replay_root(root, model.exp_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{model.replay_results_id}.reverification.yaml"
    with target.open("x", encoding="utf-8") as handle:
        yaml.safe_dump(model.model_dump(mode="json"), handle, sort_keys=False)
    return target.relative_to(root).as_posix()


def _write_yaml_artifact(
    project_root: Union[Path, str],
    *,
    exp_id: str,
    replay_results_id: str,
    suffix: str,
    payload: dict[str, Any],
) -> str:
    root = Path(project_root).resolve()
    target_dir = replay_root(root, exp_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{replay_results_id}.{suffix}.yaml"
    with target.open("x", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False)
    return target.relative_to(root).as_posix()


def _receipt_map(project_root: Path, receipts_dir: Path) -> dict[StageName, StageReceipt]:
    if not receipts_dir.is_dir():
        return {}
    mapped: dict[StageName, StageReceipt] = {}
    for path in sorted(receipts_dir.glob("*.yaml")):
        receipt = load_stage_receipt(project_root, path)
        mapped[receipt.stage] = receipt
    return mapped
