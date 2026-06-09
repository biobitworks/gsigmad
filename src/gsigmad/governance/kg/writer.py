"""
governance/kg/writer.py — Single governed KG write interface.

Enforces:
- _rev-pinned optimistic locking (CANON-CORE Invariant 1)
- W3C PROV-JSON _provenance injection on every write (CANON-CORE Invariant 9)
- PROVISIONAL trust tier block before ArangoDB write (CANON-CORE Invariant 3)
- JSONL queue fallback when ArangoDB is unreachable

Public API:
    write_document(collection, doc, old_rev, agent, ...) -> dict
    replay_queue(max_entries, max_attempts) -> dict
    auto_promote(doc, schema_path) -> dict
    make_provenance_block(sig_id, agent_name, trust_tier, ...) -> dict
    make_sig_id(agent) -> str
    KGWriteConflict (Exception)
    TrustTierError (Exception)

Reference: governance/CANON-CORE.md Invariants 1, 3, 9
           auto_promote() takes an EXPLICIT KG-document schema; the CANON-CORE
           header schema must NOT be used to promote KG docs
           DATA_CONTRACTS.md §6 (namespace / timestamp conventions)
"""
from __future__ import annotations

import hashlib
import json
import os
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from gsigmad.governance.kg.queue_ops import (
    append_queue_cursor,
    append_retry_state,
    classify_queue_failure,
    project_root_from_queue_path,
    next_retry_after,
    quarantine_queue_line,
)

# ---------------------------------------------------------------------------
# Optional dependencies
# ---------------------------------------------------------------------------

try:
    from arango import ArangoClient
    from arango.exceptions import DocumentRevisionError
    ARANGO_AVAILABLE = True
except ImportError:
    ARANGO_AVAILABLE = False
    ArangoClient = None  # type: ignore[assignment]
    DocumentRevisionError = None  # type: ignore[assignment,misc]

try:
    import jsonschema
    from jsonschema import FormatChecker
    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False
    jsonschema = None  # type: ignore[assignment]
    FormatChecker = None  # type: ignore[assignment,misc]

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class KGWriteConflict(Exception):
    """Raised when a KG write fails due to a stale _rev (optimistic locking).

    Message format: "KG_WRITE_CONFLICT: stale _rev {old} vs current {new}"
    """


class TrustTierError(Exception):
    """Raised when a PROVISIONAL artifact attempts a KG write without a
    VERIFIED countersignature.

    Message format: "TRUST_TIER_ERROR: PROVISIONAL artifacts require VERIFIED
    countersignature before KG write"
    """


# ---------------------------------------------------------------------------
# Module-level configuration
# ---------------------------------------------------------------------------

_ARANGO_HOST: str = os.environ.get("ARANGO_HOST", "localhost:8531")
_ARANGO_DB: str = os.environ.get("ARANGO_DB", "overwatch")

# Queue paths — patched in tests; kept as module-level Path objects so tests
# can override via patch("governance.kg.writer._QUEUE_PATH", ...).
_QUEUE_PATH: Path = Path(".agent/kg_queue.jsonl")
_QUEUE_FAILED_PATH: Path = Path(".agent/kg_queue_failed.jsonl")
_QUEUE_EXPIRED_PATH: Path = Path(".agent/kg_queue_expired.jsonl")
_QUEUE_QUARANTINE_PATH: Path = Path(".agent/kg_queue_quarantine.jsonl")

_QUEUE_MAX_ENTRIES: int = 500
_QUEUE_EXPIRY_DAYS: int = 7

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def make_sig_id(agent: str) -> str:
    """Return a SIG-ID per CANON-CORE Invariant 9.

    Format: SIG-YYYYMMDDTHHMMSSZ-{agent}-{hash4}

    Args:
        agent: Agent identifier string (e.g., "claude-sonnet-4-6").

    Returns:
        SIG-ID string.
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    h4 = hashlib.md5(f"{ts}-{agent}".encode()).hexdigest()[:4]
    return f"SIG-{ts}-{agent}-{h4}"


def make_provenance_block(
    sig_id: str,
    agent_name: str,
    trust_tier: str,
    activity_id: str,
    activity_type: str,
    entity_id: str,
    entity_type: str,
    evidence_class: str,
) -> dict:
    """Return a W3C PROV-DM subset block for injection as _provenance.

    Field name is _provenance (not provenance) per D-04 to avoid collision
    with the existing Overwatch provenance field on shared collections.

    Args:
        sig_id: SIG-ID from make_sig_id().
        agent_name: Human-readable agent label (e.g., "claude-sonnet-4-6").
        trust_tier: "VERIFIED" or "PROVISIONAL".
        activity_id: Activity identifier (e.g., experiment ID, prompt ID).
        activity_type: Activity category (e.g., "experiment", "prompt_execution").
        entity_id: Entity identifier (e.g., "claim/001").
        entity_type: Entity category (e.g., "claim", "artifact", "run").
        evidence_class: CANON evidence class: "MEASURED" | "INFERRED" | "HYPOTHESIS".

    Returns:
        _provenance dict conforming to W3C PROV-DM subset.
    """
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "prov:type": "prov:Collection",
        "prov:Agent": {
            "prov:id": sig_id,
            "prov:label": agent_name,
            "trust_tier": trust_tier,
        },
        "prov:Activity": {
            "prov:id": activity_id,
            "prov:type": activity_type,
            "prov:startTime": now_iso,
        },
        "prov:Entity": {
            "prov:id": entity_id,
            "prov:type": entity_type,
            "evidence_class": evidence_class,
        },
        "timestamp": now_iso,
    }


# ---------------------------------------------------------------------------
# Trust tier enforcement (internal)
# ---------------------------------------------------------------------------


def _enforce_trust_tier(doc: dict) -> None:
    """Raise TrustTierError if doc has trust_tier=PROVISIONAL in _provenance.

    PROVISIONAL artifacts cannot write to the shared KG without a VERIFIED
    countersignature. This is the enforcement boundary per CANON-CORE Invariant 3.

    Args:
        doc: Document dict to inspect.

    Raises:
        TrustTierError: If trust_tier is PROVISIONAL.
    """
    trust = (
        doc.get("_provenance", {})
        .get("prov:Agent", {})
        .get("trust_tier")
    )
    if trust == "PROVISIONAL":
        raise TrustTierError(
            "TRUST_TIER_ERROR: PROVISIONAL artifacts require VERIFIED "
            "countersignature before KG write"
        )


# ---------------------------------------------------------------------------
# ArangoDB connection helper (internal)
# ---------------------------------------------------------------------------


def _get_db():
    """Return an authenticated ArangoDB database handle.

    Uses verify=True for writes (unlike session_status.py which uses
    verify=False for read-only status display).

    Raises:
        ImportError: If python-arango is not installed (ARANGO_AVAILABLE=False).
        arango.exceptions.*: On connection or auth failure.
    """
    if not ARANGO_AVAILABLE:
        raise ImportError("python-arango not installed; KG writes unavailable")
    client = ArangoClient(hosts=f"http://{_ARANGO_HOST}")
    password = os.environ.get("ARANGO_ROOT_PASSWORD", "")
    db = client.db(_ARANGO_DB, username="root", password=password, verify=True)
    return db


# ---------------------------------------------------------------------------
# JSONL queue helpers (internal)
# ---------------------------------------------------------------------------


def _queue_write(
    collection: str,
    doc: dict,
    old_rev: Optional[str],
    queue_path: Path,
) -> None:
    """Append a write operation to the JSONL queue.

    Enforces queue cap of _QUEUE_MAX_ENTRIES lines.

    Args:
        collection: ArangoDB collection name.
        doc: Document to queue.
        old_rev: Previous _rev for replace operations; None for inserts.
        queue_path: Path to the .jsonl queue file.

    Raises:
        RuntimeError: If queue is at capacity.
    """
    queue_path.parent.mkdir(parents=True, exist_ok=True)

    # Check capacity before appending
    if queue_path.exists():
        current_count = sum(1 for _ in queue_path.open())
        if current_count >= _QUEUE_MAX_ENTRIES:
            raise RuntimeError(
                f"KG queue full ({_QUEUE_MAX_ENTRIES} entries); "
                "replay or clear before writing"
            )

    operation = "replace" if old_rev is not None else "insert"
    entry = {
        "queued_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "operation": operation,
        "collection": collection,
        "document": doc,
        "old_rev": old_rev,
        "attempts": 0,
        "idempotency_key": _queue_idempotency_key(collection, operation, doc, old_rev),
        "failure_class": None,
        "next_retry_after": None,
    }
    with queue_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _queue_idempotency_key(
    collection: str,
    operation: str,
    doc: dict,
    old_rev: Optional[str],
) -> str:
    """Return a deterministic key for one logical queued write."""
    payload = {
        "collection": collection,
        "operation": operation,
        "document": doc,
        "old_rev": old_rev,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalize_queue_entry(entry: dict) -> dict:
    """Backfill additive queue metadata for legacy JSONL entries."""
    normalized = dict(entry)
    operation = normalized.get("operation")
    old_rev = normalized.get("old_rev")
    if not operation:
        operation = "replace" if old_rev is not None else "insert"
    normalized["queued_at"] = normalized.get("queued_at") or datetime.now(
        timezone.utc
    ).isoformat().replace("+00:00", "Z")
    normalized["operation"] = operation
    normalized["attempts"] = int(normalized.get("attempts", 0) or 0)
    normalized["failure_class"] = normalized.get("failure_class")
    normalized["next_retry_after"] = normalized.get("next_retry_after")
    normalized["idempotency_key"] = normalized.get("idempotency_key") or _queue_idempotency_key(
        normalized["collection"],
        operation,
        normalized["document"],
        old_rev,
    )
    return normalized


def _rewrite_queue_atomically(queue_path: Path, entries: list[dict]) -> None:
    """Rewrite the queue via a temp sibling file to avoid clear-then-process loss."""
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = queue_path.with_suffix(".jsonl.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry) + "\n")
    temp_path.replace(queue_path)


# ---------------------------------------------------------------------------
# Public write interface
# ---------------------------------------------------------------------------


def write_document(
    collection: str,
    doc: dict,
    old_rev: Optional[str] = None,
    agent: str = "claude-sonnet-4-6",
    activity_id: str = "",
    activity_type: str = "experiment",
    entity_id: str = "",
    entity_type: str = "artifact",
    evidence_class: str = "MEASURED",
) -> dict:
    """Governed KG write: injects _provenance, enforces trust tier, writes or queues.

    This is the single entry point for all KG mutations. It:
    1. Enforces trust tier (PROVISIONAL -> TrustTierError before DB contact)
    2. Injects _provenance block if not already present
    3. Writes to ArangoDB with _rev-pinned optimistic locking
    4. Falls back to .agent/kg_queue.jsonl on any DB connectivity failure

    _rev conflict is never silently retried (CANON-CORE Invariant 1).

    Args:
        collection: ArangoDB collection name (e.g., "experiments").
        doc: Document dict. If it already has _provenance, it is kept as-is.
             If old_rev is given, doc["_rev"] is set to old_rev before replace().
        old_rev: Expected current _rev. None -> insert. Non-None -> replace
                 with check_rev=True (raises KGWriteConflict on mismatch).
        agent: Agent identifier for SIG-ID generation.
        activity_id: Activity identifier for _provenance.prov:Activity.
        activity_type: Activity type ("experiment", "prompt_execution", etc.).
        entity_id: Entity identifier for _provenance.prov:Entity.
        entity_type: Entity type ("claim", "artifact", "run").
        evidence_class: "MEASURED" | "INFERRED" | "HYPOTHESIS".

    Returns:
        On success:  {"pass": True, "result": <arango result dict>}
        On queued:   {"pass": True, "queued": True, "warning": "KG_UNAVAILABLE: ..."}

    Raises:
        TrustTierError: If doc has trust_tier=PROVISIONAL in _provenance.
        KGWriteConflict: If old_rev does not match current _rev in ArangoDB.
        RuntimeError: If queue is at capacity (500 entries).
    """
    # Step 1: Enforce trust tier BEFORE any DB contact
    _enforce_trust_tier(doc)

    # Step 2: Inject _provenance if not already present
    if "_provenance" not in doc:
        sig_id = make_sig_id(agent)
        doc["_provenance"] = make_provenance_block(
            sig_id=sig_id,
            agent_name=agent,
            trust_tier="VERIFIED",
            activity_id=activity_id,
            activity_type=activity_type,
            entity_id=entity_id,
            entity_type=entity_type,
            evidence_class=evidence_class,
        )

    # Step 3: Attempt ArangoDB write
    queue_path = _QUEUE_PATH  # resolved here to allow test patching
    try:
        db = _get_db()
        col = db.collection(collection)

        if old_rev is not None:
            # Replace with optimistic locking — check_rev=True uses doc["_rev"]
            doc["_rev"] = old_rev
            try:
                result = col.replace(doc, check_rev=True, return_new=True)
            except Exception as exc:
                # Re-raise as KGWriteConflict if it was a revision conflict;
                # re-raise as-is for other arango exceptions to fall through
                # to the queue fallback at the outer level.
                if DocumentRevisionError is not None and isinstance(
                    exc, DocumentRevisionError
                ):
                    current = col.get(doc["_key"])
                    new_rev = current["_rev"] if current else "<unknown>"
                    raise KGWriteConflict(
                        f"KG_WRITE_CONFLICT: stale _rev {old_rev} vs current {new_rev}"
                    ) from exc
                raise  # other arango exceptions -> outer except -> queue
        else:
            result = col.insert(doc, return_new=True)

        return {"pass": True, "result": result}

    except (KGWriteConflict, TrustTierError, RuntimeError):
        # These are deliberate governance errors — never queue, always propagate
        raise
    except Exception as exc:
        # Connectivity failure: queue and warn
        warning = "KG_UNAVAILABLE: write queued to .agent/kg_queue.jsonl"
        warnings.warn(warning, RuntimeWarning, stacklevel=2)
        _queue_write(collection, doc, old_rev, queue_path)
        return {"pass": True, "queued": True, "warning": warning}


# ---------------------------------------------------------------------------
# Queue replay
# ---------------------------------------------------------------------------


def replay_queue(
    max_entries: int = 500,
    max_attempts: int = 3,
) -> dict:
    """Replay pending entries from .agent/kg_queue.jsonl.

    Processes up to max_entries entries. Each entry is retried up to
    max_attempts times before being moved to .agent/kg_queue_failed.jsonl.
    Entries older than _QUEUE_EXPIRY_DAYS days are moved to
    .agent/kg_queue_expired.jsonl.

    Requires ArangoDB to be reachable. Falls back to writing all entries back
    to queue if DB is unavailable during replay.

    Args:
        max_entries: Maximum queue entries to process in this call (default 500).
        max_attempts: Max retries per entry before moving to failed queue.

    Returns:
        {
          "processed": int,   # entries successfully written to ArangoDB
          "failed": int,      # entries moved to kg_queue_failed.jsonl
          "expired": int,     # entries moved to kg_queue_expired.jsonl
          "requeued": int,    # entries put back (attempts < max_attempts)
          "pass": True
        }
    """
    queue_path = _QUEUE_PATH
    failed_path = _QUEUE_FAILED_PATH
    expired_path = _QUEUE_EXPIRED_PATH
    quarantine_path = _QUEUE_QUARANTINE_PATH
    project_root = project_root_from_queue_path(queue_path)

    if not queue_path.exists():
        return {
            "pass": True,
            "processed": 0,
            "failed": 0,
            "expired": 0,
            "requeued": 0,
            "quarantined": 0,
        }

    entries = []
    quarantined = 0
    for raw_line in queue_path.open(encoding="utf-8"):
        line = raw_line.strip()
        if line:
            try:
                entries.append(_normalize_queue_entry(json.loads(line)))
            except json.JSONDecodeError as exc:
                quarantine_queue_line(
                    quarantine_path,
                    source_path=queue_path,
                    raw_line=raw_line,
                    error=str(exc),
                )
                quarantined += 1

    processed = 0
    failed = 0
    expired = 0
    requeued_entries = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=_QUEUE_EXPIRY_DAYS)

    # Try to get DB once; if unavailable, put everything back
    try:
        db = _get_db()
    except Exception:
        _rewrite_queue_atomically(queue_path, entries)
        append_queue_cursor(
            project_root,
            queue_name=queue_path.name,
            cursor="db-unavailable",
            event="db-unavailable",
            details={"entry_count": len(entries)},
        )
        return {
            "pass": True,
            "processed": 0,
            "failed": 0,
            "expired": 0,
            "requeued": len(entries),
            "quarantined": quarantined,
        }

    grouped_entries = []
    seen_keys = set()
    for entry in entries:
        if entry["idempotency_key"] in seen_keys:
            continue
        grouped_entries.append(entry)
        seen_keys.add(entry["idempotency_key"])

    for index, entry in enumerate(grouped_entries[:max_entries], start=1):
        # Check expiry
        try:
            queued_at = datetime.fromisoformat(
                entry.get("queued_at", "").replace("Z", "+00:00")
            )
            if queued_at < cutoff:
                _append_to(expired_path, entry)
                append_retry_state(
                    project_root,
                    entry_id=entry["idempotency_key"],
                    event="expired",
                    attempts=entry.get("attempts", 0),
                    failure_class=entry.get("failure_class"),
                    next_retry_after=None,
                    evidence={"queue_file": expired_path.name},
                )
                append_queue_cursor(
                    project_root,
                    queue_name=queue_path.name,
                    cursor=f"{index}",
                    event="expired",
                    entry_id=entry["idempotency_key"],
                    details={"queue_file": expired_path.name},
                )
                expired += 1
                continue
        except (ValueError, TypeError):
            pass  # malformed timestamp — attempt replay anyway

        col = db.collection(entry["collection"])
        doc = dict(entry["document"])
        old_rev = entry.get("old_rev")
        attempts = entry.get("attempts", 0) + 1

        try:
            if entry["operation"] == "replace":
                doc["_rev"] = old_rev
                col.replace(doc, check_rev=True, return_new=True)
            else:
                col.insert(doc, return_new=True)
            processed += 1
            append_queue_cursor(
                project_root,
                queue_name=queue_path.name,
                cursor=f"{index}",
                event="processed",
                entry_id=entry["idempotency_key"],
                details={"collection": entry["collection"]},
            )
        except Exception as exc:
            entry["attempts"] = attempts
            entry["failure_class"] = classify_queue_failure(exc)
            if entry["failure_class"] == "transient" and attempts < max_attempts:
                entry["next_retry_after"] = next_retry_after(attempts)
                append_retry_state(
                    project_root,
                    entry_id=entry["idempotency_key"],
                    event="retry-scheduled",
                    attempts=attempts,
                    failure_class=entry["failure_class"],
                    next_retry_after=entry["next_retry_after"],
                    evidence={"error": str(exc)},
                )
                append_queue_cursor(
                    project_root,
                    queue_name=queue_path.name,
                    cursor=f"{index}",
                    event="retry-scheduled",
                    entry_id=entry["idempotency_key"],
                    details={"error": str(exc)},
                )
                requeued_entries.append(entry)
            else:
                entry["next_retry_after"] = None
                _append_to(failed_path, entry)
                append_retry_state(
                    project_root,
                    entry_id=entry["idempotency_key"],
                    event="dead-lettered",
                    attempts=attempts,
                    failure_class=entry["failure_class"],
                    next_retry_after=None,
                    evidence={"error": str(exc), "queue_file": failed_path.name},
                )
                append_queue_cursor(
                    project_root,
                    queue_name=queue_path.name,
                    cursor=f"{index}",
                    event="dead-lettered",
                    entry_id=entry["idempotency_key"],
                    details={"error": str(exc), "queue_file": failed_path.name},
                )
                failed += 1

    # Any entries beyond max_entries are put back
    requeued_entries.extend(grouped_entries[max_entries:])

    _rewrite_queue_atomically(queue_path, requeued_entries)

    return {
        "pass": True,
        "processed": processed,
        "failed": failed,
        "expired": expired,
        "requeued": len(requeued_entries),
        "quarantined": quarantined,
    }


def _append_to(path: Path, entry: dict) -> None:
    """Append a JSON entry to a JSONL file, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# Auto-promotion
# ---------------------------------------------------------------------------


def auto_promote(
    doc: dict,
    schema_path: str | None = None,
) -> dict:
    """Validate a KG document against an explicit KG-document schema; VERIFIED on pass.

    The caller MUST supply the JSON Schema that defines a *promotable KG document*
    for this collection (the PROVISIONAL -> VERIFIED trust-tier model; QUARANTINED
    is set elsewhere on requeue failure). There is intentionally **no default**:
    ``governance/CANON-CORE-schema.json`` is the CANON-CORE *extension-header*
    schema — it requires ``extends`` and a status enum of ACTIVE/DEPRECATED/DRAFT,
    so a real PROVISIONAL EXTREF / KG document can never satisfy it. Defaulting to
    it made auto-promotion silently impossible (it could only ever promote a
    CANON-header-shaped doc, never an actual KG document). When no schema is
    supplied, this fails closed: ``doc["status"]`` stays/defaults to "PROVISIONAL".

    NOTE (governance decision, pending PI/operator): the canonical KG-document
    promotion schema (which fields gate VERIFIED) is not yet defined in-repo. Until
    it is, pass an explicit, reviewed schema path; do not reintroduce a
    header-schema default.

    Uses jsonschema.validate() with FormatChecker(). Modified in place.

    Args:
        doc: Document dict to validate. Modified in-place.
        schema_path: Path to the KG-document JSON Schema. Required for promotion;
            None (or a missing jsonschema install) fails closed to PROVISIONAL.

    Returns:
        The (possibly modified) doc dict.
    """
    if not JSONSCHEMA_AVAILABLE:
        warnings.warn(
            "jsonschema not installed; auto_promote always returns PROVISIONAL",
            RuntimeWarning,
            stacklevel=2,
        )
        doc.setdefault("status", "PROVISIONAL")
        return doc

    if not schema_path:
        warnings.warn(
            "auto_promote called without a KG-document schema_path; failing closed "
            "to PROVISIONAL (the CANON-CORE header schema must not be used to "
            "promote KG documents)",
            RuntimeWarning,
            stacklevel=2,
        )
        doc.setdefault("status", "PROVISIONAL")
        return doc

    try:
        schema_file = Path(schema_path)
        with schema_file.open(encoding="utf-8") as f:
            schema = json.load(f)
        jsonschema.validate(doc, schema, format_checker=FormatChecker())
        doc["status"] = "VERIFIED"
    except Exception:
        doc.setdefault("status", "PROVISIONAL")

    return doc
