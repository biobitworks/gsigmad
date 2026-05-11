"""Write-once run manifest helpers for immutable artifact integrity."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError
import yaml

from gsigmad.governance.export.exporter import _compute_sha256
from gsigmad.hub.ledger import hash_payload
from gsigmad.scaffold.templates import REPLICATION_ARTIFACT_TYPES

_ALLOWED_IMMUTABLE_ARTIFACT_TYPES = REPLICATION_ARTIFACT_TYPES - {"notebook"}
_PLACEHOLDER_NAME = "MANIFEST.placeholder.yaml"


class ImmutableInputModel(BaseModel):
    """One immutable input entry recorded inside a run manifest."""

    path: str
    sha256: str


class RunManifestModel(BaseModel):
    """Typed Phase 22 run manifest payload."""

    schema_version: int = 1
    exp_id: str
    results_id: str
    created_at: str
    frozen_governance_sha256: str
    frozen_governance: dict[str, Any]
    immutable_inputs: list[ImmutableInputModel]


def build_frozen_governance_payload(exp_record: dict[str, Any]) -> dict[str, Any]:
    """Return the immutable governance subset that participates in manifest hashing."""
    payload: dict[str, Any] = {
        "exp_id": exp_record["exp_id"],
        "classification": exp_record["classification"],
        "hypothesis": dict(exp_record.get("hypothesis") or {}),
    }
    _copy_if_present(
        payload,
        exp_record,
        [
            "promotion_authority",
            "decision_tree",
            "data_file",
            "anchor_schema_name",
            "anchor_schema_version",
            "anchors_file",
        ],
    )

    replication_artifacts = []
    for artifact in exp_record.get("replication_artifacts") or []:
        if not isinstance(artifact, dict):
            continue
        if artifact.get("type") not in _ALLOWED_IMMUTABLE_ARTIFACT_TYPES:
            continue
        replication_artifacts.append(dict(artifact))
    if replication_artifacts:
        payload["replication_artifacts"] = replication_artifacts

    return payload


def collect_immutable_inputs(project_root: Path | str, exp_record: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect and hash immutable input files declared by the EXP record."""
    root = Path(project_root).resolve()
    exp_id = str(exp_record["exp_id"])
    candidates: list[str] = []

    script_relpath = f"scripts/{exp_id}_analysis.py"
    if (root / script_relpath).is_file():
        candidates.append(script_relpath)

    for key in ("data_file", "decision_tree", "anchors_file"):
        value = exp_record.get(key)
        if isinstance(value, str) and value.strip():
            candidates.append(value)

    for artifact in exp_record.get("replication_artifacts") or []:
        if not isinstance(artifact, dict):
            continue
        if artifact.get("type") not in _ALLOWED_IMMUTABLE_ARTIFACT_TYPES:
            continue
        path_value = artifact.get("path")
        if not isinstance(path_value, str) or not path_value.strip():
            continue
        normalized = path_value.strip()
        if normalized.startswith("results/"):
            continue
        candidates.append(normalized)

    seen: set[str] = set()
    entries: list[dict[str, Any]] = []
    for candidate in candidates:
        normalized = _normalize_project_relpath(root, candidate)
        relpath = normalized.as_posix()
        if relpath in seen:
            continue
        seen.add(relpath)

        full_path = root / normalized
        if not full_path.is_file():
            raise FileNotFoundError(f"Immutable input not found: {relpath}")
        entries.append({"path": relpath, "sha256": _compute_sha256(full_path)})

    return entries


def write_run_manifest(
    project_root: Path | str,
    *,
    exp_record: dict[str, Any],
    results_id: str,
) -> dict[str, Any]:
    """Persist one write-once manifest for a completed run."""
    root = Path(project_root).resolve()
    exp_id = str(exp_record["exp_id"])
    manifest_path = find_run_manifest(root, exp_id, results_id)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    frozen_governance = build_frozen_governance_payload(exp_record)
    manifest = RunManifestModel(
        exp_id=exp_id,
        results_id=results_id,
        created_at=_utc_now(),
        frozen_governance_sha256=hash_payload(frozen_governance),
        frozen_governance=frozen_governance,
        immutable_inputs=[
            ImmutableInputModel.model_validate(entry)
            for entry in collect_immutable_inputs(root, exp_record)
        ],
    )

    with manifest_path.open("x", encoding="utf-8") as handle:
        yaml.safe_dump(manifest.model_dump(mode="python"), handle, sort_keys=False)

    return {
        "manifest_relpath": manifest_path.relative_to(root).as_posix(),
        "frozen_governance_sha256": manifest.frozen_governance_sha256,
    }


def verify_run_manifest(
    project_root: Path | str,
    *,
    exp_record: dict[str, Any],
    manifest_path: Path | str,
) -> dict[str, Any]:
    """Verify one run manifest against the current immutable-input state."""
    root = Path(project_root).resolve()
    path = Path(manifest_path)
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
    manifest_relpath = _relative_path_or_none(root, resolved)

    if resolved.name == _PLACEHOLDER_NAME:
        return _verification_result(
            True,
            "unavailable",
            advisory=True,
            manifest_path=manifest_relpath,
        )
    if not resolved.is_file():
        return _verification_result(
            False,
            "missing",
            manifest_path=manifest_relpath,
            errors=[{"code": "MANIFEST_MISSING", "path": manifest_relpath}],
        )

    try:
        payload = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
        manifest = RunManifestModel.model_validate(payload)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        return _verification_result(
            False,
            "corrupt",
            manifest_path=manifest_relpath,
            errors=[{"code": "MANIFEST_CORRUPT", "detail": str(exc)}],
        )

    stored_payload_hash = hash_payload(manifest.frozen_governance)
    if stored_payload_hash != manifest.frozen_governance_sha256:
        return _verification_result(
            False,
            "corrupt",
            manifest_path=manifest_relpath,
            errors=[{"code": "FROZEN_GOVERNANCE_HASH_MISMATCH"}],
        )

    current_payload_hash = hash_payload(build_frozen_governance_payload(exp_record))
    if current_payload_hash != manifest.frozen_governance_sha256:
        return _verification_result(
            False,
            "mismatch",
            manifest_path=manifest_relpath,
            errors=[{"code": "FROZEN_GOVERNANCE_MISMATCH"}],
        )

    mismatches: list[dict[str, Any]] = []
    for entry in manifest.immutable_inputs:
        full_path = root / _normalize_project_relpath(root, entry.path)
        if not full_path.is_file():
            mismatches.append({"code": "INPUT_MISSING", "path": entry.path})
            continue
        actual_sha = _compute_sha256(full_path)
        if actual_sha != entry.sha256:
            mismatches.append(
                {
                    "code": "SHA_MISMATCH",
                    "path": entry.path,
                    "expected_sha256": entry.sha256,
                    "actual_sha256": actual_sha,
                }
            )

    if mismatches:
        return _verification_result(
            False,
            "mismatch",
            manifest_path=manifest_relpath,
            errors=mismatches,
        )

    return _verification_result(
        True,
        "verified",
        manifest_path=manifest_relpath,
        frozen_governance_sha256=manifest.frozen_governance_sha256,
    )


def load_run_manifest(project_root: Path | str, manifest_path: Path | str) -> RunManifestModel:
    """Load one authoritative run manifest as a validated typed model."""
    root = Path(project_root).resolve()
    path = Path(manifest_path)
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
    payload = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
    return RunManifestModel.model_validate(payload)


def compare_run_manifests(
    project_root: Path | str,
    *,
    baseline_manifest_path: Path | str,
    candidate_manifest_path: Path | str,
) -> dict[str, Any]:
    """Compare two authoritative manifests for replay-grade governance drift."""
    root = Path(project_root).resolve()
    baseline = load_run_manifest(root, baseline_manifest_path)
    candidate = load_run_manifest(root, candidate_manifest_path)

    reasons: list[dict[str, Any]] = []
    if baseline.frozen_governance_sha256 != candidate.frozen_governance_sha256:
        reasons.append({"code": "FROZEN_GOVERNANCE_DRIFT"})

    baseline_inputs = {entry.path: entry.sha256 for entry in baseline.immutable_inputs}
    candidate_inputs = {entry.path: entry.sha256 for entry in candidate.immutable_inputs}
    all_paths = sorted(set(baseline_inputs) | set(candidate_inputs))
    for path in all_paths:
        baseline_sha = baseline_inputs.get(path)
        candidate_sha = candidate_inputs.get(path)
        if baseline_sha != candidate_sha:
            reasons.append(
                {
                    "code": "IMMUTABLE_INPUT_DRIFT",
                    "path": path,
                    "baseline_sha256": baseline_sha,
                    "candidate_sha256": candidate_sha,
                }
            )

    return {
        "pass": not reasons,
        "reasons": reasons,
        "baseline_manifest_path": _relative_path_or_none(root, Path(baseline_manifest_path).resolve() if Path(baseline_manifest_path).is_absolute() else (root / Path(baseline_manifest_path)).resolve()),
        "candidate_manifest_path": _relative_path_or_none(root, Path(candidate_manifest_path).resolve() if Path(candidate_manifest_path).is_absolute() else (root / Path(candidate_manifest_path)).resolve()),
    }


def find_run_manifest(project_root: Path | str, exp_id: str, results_id: str) -> Path:
    """Return the authoritative manifest path for one results artifact."""
    root = Path(project_root).resolve()
    return root / ".gsigmad" / "manifests" / exp_id / f"{results_id}.manifest.yaml"


def _copy_if_present(target: dict[str, Any], source: dict[str, Any], keys: list[str]) -> None:
    for key in keys:
        value = source.get(key)
        if value is not None:
            target[key] = value


def _normalize_project_relpath(project_root: Path, candidate: str | Path) -> Path:
    raw_path = Path(candidate)
    full_path = raw_path if raw_path.is_absolute() else (project_root / raw_path)
    resolved = full_path.resolve()
    try:
        return resolved.relative_to(project_root)
    except ValueError as exc:
        raise ValueError(f"Path must stay within project root: {candidate}") from exc


def _relative_path_or_none(project_root: Path, path: Path) -> str | None:
    try:
        return path.relative_to(project_root).as_posix()
    except ValueError:
        return None


def _verification_result(
    passed: bool,
    status: str,
    *,
    advisory: bool = False,
    manifest_path: str | None = None,
    errors: list[dict[str, Any]] | None = None,
    frozen_governance_sha256: str | None = None,
) -> dict[str, Any]:
    result = {
        "pass": passed,
        "status": status,
        "advisory": advisory,
        "errors": errors or [],
    }
    if manifest_path is not None:
        result["manifest_path"] = manifest_path
    if frozen_governance_sha256 is not None:
        result["frozen_governance_sha256"] = frozen_governance_sha256
    return result


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
