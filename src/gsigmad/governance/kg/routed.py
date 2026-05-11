"""Adapter-aware KG resolution, query routing, and live validation helpers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from gsigmad.governance.adapters.runtime import resolve_project_target
from gsigmad.governance.kg.citations import create_citation_edge
from gsigmad.governance.kg.query import find_experiments
from gsigmad.governance.kg.writer import (
    KGWriteConflict,
    TrustTierError,
    make_provenance_block,
    make_sig_id,
    replay_queue,
    write_document,
)
from gsigmad.governance import kg as kg_pkg
from gsigmad.governance.kg import writer as writer_mod

DEFAULT_VALIDATION_DOI = "10.1001/jamainternmed.2013.13563"


@dataclass
class KGProjectContext:
    """Resolved KG routing context for a target project."""

    target_path: Path
    project_root: Path
    project_name: str
    namespace_prefix: str | None
    runtime_mode: str
    resolution_source: str
    manifest_path: Path | None


def resolve_kg_project_context(target_path: Path | str | None = None) -> KGProjectContext:
    """Resolve a project path into KG routing metadata."""
    resolution = resolve_project_target(target_path)
    return KGProjectContext(
        target_path=resolution.target_path,
        project_root=resolution.project_root,
        project_name=resolution.project_name,
        namespace_prefix=resolution.namespace_prefix,
        runtime_mode=resolution.runtime_mode,
        resolution_source=resolution.source,
        manifest_path=resolution.manifest_path,
    )


def routed_find_experiments(
    *,
    target_path: Path | str | None = None,
    project: str | None = None,
    classification: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    protein: str | None = None,
    doi: str | None = None,
    pmid: str | None = None,
    limit: int = 100,
) -> list[dict] | dict:
    """Run a KG experiment query scoped through adapter-aware project resolution."""
    context = resolve_kg_project_context(target_path)
    effective_project = project or context.project_name
    return find_experiments(
        project=effective_project,
        classification=classification,
        status=status,
        date_from=date_from,
        date_to=date_to,
        protein=protein,
        doi=doi,
        pmid=pmid,
        limit=limit,
    )


def validate_live_kg(
    target_path: Path | str | None = None,
    *,
    doi: str = DEFAULT_VALIDATION_DOI,
    cleanup: bool = True,
    simulate_queue: bool = True,
) -> dict[str, object]:
    """Exercise live KG write/query behavior for one resolved project target."""
    context = resolve_kg_project_context(target_path)
    db = writer_mod._get_db()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    primary_key = f"gsigmad_validation_{context.project_name.replace('-', '_')}_{timestamp.lower()}"
    queued_key = f"{primary_key}_queue"
    exp_id = f"EXP-KGVAL-{timestamp}"
    queued_exp_id = f"{exp_id}-QUEUE"
    run_id = f"RUN-KGVAL-{timestamp}"

    created: dict[str, str] = {"experiment_key": primary_key}
    checks: dict[str, bool] = {}
    errors: list[str] = []

    primary_doc = _validation_doc(context, primary_key, exp_id, run_id)
    write_result = write_document(
        "experiments",
        primary_doc,
        agent="gsigmad-live-validation",
        activity_id=exp_id,
        activity_type="experiment",
        entity_id=exp_id,
        entity_type="experiment",
        evidence_class="MEASURED",
    )
    checks["write_inserted"] = bool(write_result.get("pass"))

    stored_doc = db.collection("experiments").get(primary_key)
    checks["provenance_present"] = bool(stored_doc and stored_doc.get("_provenance"))
    checks["project_scoped"] = bool(stored_doc and stored_doc.get("project") == context.project_name)

    try:
        write_document(
            "experiments",
            dict(primary_doc, title="stale-rev-check"),
            old_rev="_stale_rev_001",
            agent="gsigmad-live-validation",
            activity_id=exp_id,
            activity_type="experiment",
            entity_id=exp_id,
            entity_type="experiment",
            evidence_class="MEASURED",
        )
        checks["stale_rev_blocked"] = False
    except KGWriteConflict:
        checks["stale_rev_blocked"] = True

    provisional_doc = dict(primary_doc)
    provisional_doc["_key"] = f"{primary_key}_provisional"
    provisional_doc["_provenance"] = make_provenance_block(
        sig_id=make_sig_id("gsigmad-live-validation"),
        agent_name="gsigmad-live-validation",
        trust_tier="PROVISIONAL",
        activity_id=exp_id,
        activity_type="experiment",
        entity_id=exp_id,
        entity_type="experiment",
        evidence_class="MEASURED",
    )
    try:
        write_document("experiments", provisional_doc)
        checks["provisional_blocked"] = False
    except TrustTierError:
        checks["provisional_blocked"] = True

    if simulate_queue:
        with TemporaryDirectory() as tmp_dir:
            queue_path = Path(tmp_dir) / "kg_queue.jsonl"
            original_host = writer_mod._ARANGO_HOST
            original_queue = writer_mod._QUEUE_PATH
            try:
                writer_mod._ARANGO_HOST = "localhost:1"
                writer_mod._QUEUE_PATH = queue_path
                queued_doc = _validation_doc(context, queued_key, queued_exp_id, f"{run_id}-QUEUE")
                queue_result = write_document(
                    "experiments",
                    queued_doc,
                    agent="gsigmad-live-validation",
                    activity_id=queued_exp_id,
                    activity_type="experiment",
                    entity_id=queued_exp_id,
                    entity_type="experiment",
                    evidence_class="MEASURED",
                )
                checks["queue_fallback"] = bool(queue_result.get("queued") and queue_path.exists())
            finally:
                writer_mod._ARANGO_HOST = original_host
                writer_mod._QUEUE_PATH = original_queue

            if checks["queue_fallback"]:
                created["queued_experiment_key"] = queued_key
                try:
                    writer_mod._QUEUE_PATH = queue_path
                    replay_result = replay_queue()
                    checks["queue_replay"] = replay_result.get("processed", 0) >= 1
                finally:
                    writer_mod._QUEUE_PATH = original_queue

    citation_result = create_citation_edge(
        exp_key=primary_key,
        doi=doi,
        citation_type="supports",
        agent="gsigmad-live-validation",
    )
    checks["citation_edge_created"] = bool(citation_result.get("pass"))
    if citation_result.get("pass"):
        citation_meta = citation_result.get("result", {}) if isinstance(citation_result.get("result"), dict) else {}
        citation_key = citation_meta.get("_key") or citation_meta.get("new", {}).get("_key")
        if citation_key:
            created["citation_edge_key"] = citation_key

    project_results = routed_find_experiments(target_path=context.project_root, limit=20)
    if isinstance(project_results, list):
        checks["project_query_visible"] = any(item.get("exp_id", "").endswith(exp_id) for item in project_results)
    else:
        checks["project_query_visible"] = False
        errors.append(str(project_results.get("error")))

    cross_project_results = find_experiments(limit=20)
    if isinstance(cross_project_results, list):
        checks["cross_project_query_visible"] = any(item.get("exp_id", "").endswith(exp_id) for item in cross_project_results)
    else:
        checks["cross_project_query_visible"] = False
        errors.append(str(cross_project_results.get("error")))

    citation_query_results = find_experiments(project=context.project_name, doi=doi, limit=20)
    if isinstance(citation_query_results, list):
        checks["citation_query_visible"] = any(item.get("exp_id", "").endswith(exp_id) for item in citation_query_results)
    else:
        checks["citation_query_visible"] = False
        errors.append(str(citation_query_results.get("error")))

    if cleanup:
        _cleanup_validation_artifacts(db, created)

    passed = all(checks.values())
    return {
        "pass": passed,
        "context": {
            "project_name": context.project_name,
            "project_root": str(context.project_root),
            "runtime_mode": context.runtime_mode,
            "resolution_source": context.resolution_source,
            "namespace_prefix": context.namespace_prefix,
        },
        "created": created,
        "checks": checks,
        "errors": errors,
        "cleanup": cleanup,
    }


def _validation_doc(context: KGProjectContext, key: str, exp_id: str, run_id: str) -> dict[str, object]:
    return {
        "_key": key,
        "exp_id": exp_id,
        "project": context.project_name,
        "classification": "EXPLORATORY",
        "status": "completed",
        "start_date": datetime.now(timezone.utc).date().isoformat(),
        "run_ids": [run_id],
        "title": f"Live KG validation for {context.project_name}",
        "source_system": "gsigmad_live_validation",
        "runtime_mode": context.runtime_mode,
        "namespace_prefix": context.namespace_prefix,
        "project_root": str(context.project_root),
        "validation_tag": "v1.4-live-kg",
    }


def _cleanup_validation_artifacts(db, created: dict[str, str]) -> None:
    for key_name in ("citation_edge_key",):
        key = created.get(key_name)
        if key:
            db.collection("rels").delete(key, ignore_missing=True)

    for key_name in ("experiment_key", "queued_experiment_key"):
        key = created.get(key_name)
        if key:
            db.collection("experiments").delete(key, ignore_missing=True)
