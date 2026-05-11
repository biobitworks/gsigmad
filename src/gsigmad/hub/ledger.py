"""W5 ledger helpers for connector-backed append-only governance records."""
from __future__ import annotations

import getpass
import hashlib
import json
import os
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import rfc8785
except ImportError:  # pragma: no cover - exercised when dependency is missing locally
    rfc8785 = None

from gsigmad.connectors import ConnectorProtocol, get_connector


def canonical_json_bytes(payload: Any) -> bytes:
    """Return canonical JSON bytes for hashing."""
    if rfc8785 is not None:
        dumped = rfc8785.dumps(payload)
        return dumped if isinstance(dumped, bytes) else str(dumped).encode("utf-8")
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def hash_payload(payload: Any) -> str:
    """Hash a payload using SHA-256 over canonical JSON bytes."""
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _actor_identity() -> str:
    return (
        os.environ.get("GSD_ACTOR")
        or os.environ.get("USER")
        or os.environ.get("USERNAME")
        or getpass.getuser()
        or "unknown"
    )


def build_w5_record(
    *,
    who: dict[str, Any],
    what: dict[str, Any],
    where: dict[str, Any],
    why: dict[str, Any],
    prev_hash: str | None,
    when: str | None = None,
    archive: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construct one W5 ledger record with chain metadata."""
    record: dict[str, Any] = {
        "schema_version": 1,
        "who": who,
        "what": what,
        "where": where,
        "when": when or _utc_now(),
        "why": why,
        "prev_hash": prev_hash,
    }
    if archive is not None:
        record["archive"] = archive
    if metadata:
        record["metadata"] = metadata
    record["hash"] = hash_payload(record)
    return record


def load_ledger_entries(
    project_path: Path | str | None = None,
    *,
    connector: ConnectorProtocol | None = None,
) -> list[dict[str, Any]]:
    """Load all ledger entries for a project through the active connector."""
    resolved_connector = connector or get_connector(Path(project_path or Path.cwd()))
    return resolved_connector.load_ledger_entries()


def append_w5(
    project_path: Path | str | None = None,
    *,
    who: dict[str, Any],
    what: dict[str, Any],
    where: dict[str, Any],
    why: dict[str, Any],
    when: str | None = None,
    archive: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    connector: ConnectorProtocol | None = None,
) -> dict[str, Any]:
    """Append a W5 record via the active connector and return the stored entry."""
    project_root = Path(project_path or Path.cwd()).resolve()
    resolved_connector = connector or get_connector(project_root)
    entries = resolved_connector.load_ledger_entries()
    prev_hash = entries[-1]["hash"] if entries else None
    record = build_w5_record(
        who=who,
        what=what,
        where=where,
        why=why,
        when=when,
        archive=archive,
        metadata=metadata,
        prev_hash=prev_hash,
    )
    resolved_connector.append_ledger_entry(record)
    return record


def verify_ledger_chain(
    project_path: Path | str | None = None,
    *,
    connector: ConnectorProtocol | None = None,
) -> dict[str, Any]:
    """Verify a project's append-only ledger hash chain."""
    entries = load_ledger_entries(project_path, connector=connector)
    previous_hash: str | None = None

    for index, entry in enumerate(entries):
        current_prev = entry.get("prev_hash")
        if current_prev != previous_hash:
            return {
                "pass": False,
                "entries": len(entries),
                "verified": index,
                "error": "PREV_HASH_MISMATCH",
                "entry_index": index,
                "expected_prev_hash": previous_hash,
                "actual_prev_hash": current_prev,
            }

        actual_hash = entry.get("hash")
        payload = dict(entry)
        payload.pop("hash", None)
        expected_hash = hash_payload(payload)
        if actual_hash != expected_hash:
            return {
                "pass": False,
                "entries": len(entries),
                "verified": index,
                "error": "HASH_MISMATCH",
                "entry_index": index,
                "expected_hash": expected_hash,
                "actual_hash": actual_hash,
            }

        previous_hash = actual_hash

    return {
        "pass": True,
        "entries": len(entries),
        "verified": len(entries),
        "error": None,
        "entry_index": None,
    }


def best_effort_append_command_w5(
    project_path: Path | str | None = None,
    *,
    command: str,
    action: str,
    exp_id: str | None = None,
    archive: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Append a command-scoped W5 entry without breaking the primary CLI action."""
    project_root = Path(project_path or Path.cwd()).resolve()
    try:
        return append_w5(
            project_root,
            who={
                "actor": _actor_identity(),
                "runtime": "gsigmad-cli",
            },
            what={
                "command": command,
                "mode": "cli",
            },
            where={
                "project_root": str(project_root),
                "exp_id": exp_id,
            },
            why={
                "action": action,
            },
            archive=archive,
            metadata=metadata,
        )
    except Exception as exc:  # pragma: no cover - warning path validated through CLI tests
        warnings.warn(
            f"W5 ledger append failed for '{command}': {exc}",
            RuntimeWarning,
            stacklevel=2,
        )
        return None
