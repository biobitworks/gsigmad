"""Queue helper utilities for conservative replay classification."""
from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


_TRANSIENT_ERROR_NAMES = {
    "ConnectionError",
    "TimeoutError",
}

_PERMANENT_ERROR_NAMES = {
    "DocumentRevisionError",
    "KGWriteConflict",
    "TrustTierError",
    "PermissionError",
}

_TRANSIENT_MESSAGE_MARKERS = (
    "connection",
    "temporar",
    "timeout",
    "timed out",
    "unavailable",
    "reset by peer",
)

_PERMANENT_MESSAGE_MARKERS = (
    "auth",
    "forbidden",
    "schema",
    "trust",
    "unauthorized",
    "validation",
    "_rev",
    "revision",
    "conflict",
)

_QUEUE_FILES = {
    "pending": "kg_queue.jsonl",
    "failed": "kg_queue_failed.jsonl",
    "expired": "kg_queue_expired.jsonl",
    "quarantine": "kg_queue_quarantine.jsonl",
}
_QUEUE_STATE_DIR = Path(".gsigmad") / "queue"
_RETRY_STATE_FILE = "retry-state.jsonl"
_CURSOR_FILE = "cursors.jsonl"


def classify_queue_failure(exc: Exception) -> str:
    """Classify replay failures conservatively for queue handling."""
    name = exc.__class__.__name__
    if isinstance(exc, (ConnectionError, TimeoutError)) or name in _TRANSIENT_ERROR_NAMES:
        return "transient"

    message = str(exc).lower()
    if any(marker in message for marker in _TRANSIENT_MESSAGE_MARKERS):
        return "transient"

    if name in _PERMANENT_ERROR_NAMES:
        return "permanent"

    if any(marker in message for marker in _PERMANENT_MESSAGE_MARKERS):
        return "permanent"

    return "permanent"


def next_retry_after(attempts: int, *, base_seconds: int = 30) -> str:
    """Return an ISO-8601 retry timestamp using exponential backoff."""
    delay_seconds = base_seconds * (2 ** max(attempts - 1, 0))
    retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
    return retry_at.isoformat().replace("+00:00", "Z")


def quarantine_queue_line(
    quarantine_path: Path,
    *,
    source_path: Path,
    raw_line: str,
    error: str,
) -> None:
    """Persist one malformed JSONL line for operator review."""
    quarantine_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "source_path": str(source_path),
        "raw_line": raw_line.rstrip("\n"),
        "error": error,
        "quarantined_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    with quarantine_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def project_root_from_queue_path(queue_path: Path) -> Path:
    """Resolve the project root from a queue file path."""
    resolved = queue_path.resolve()
    if resolved.parent.name == ".agent":
        return resolved.parent.parent
    return resolved.parent


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def append_retry_state(
    project_root: Path | str,
    *,
    entry_id: str,
    event: str,
    attempts: int,
    failure_class: str | None,
    next_retry_after: str | None,
    evidence: dict[str, Any] | None = None,
) -> None:
    """Persist one append-only retry evidence event."""
    root = Path(project_root).resolve()
    payload = {
        "recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "entry_id": entry_id,
        "event": event,
        "attempts": attempts,
        "failure_class": failure_class,
        "next_retry_after": next_retry_after,
        "evidence": evidence or {},
    }
    _append_jsonl(root / _QUEUE_STATE_DIR / _RETRY_STATE_FILE, payload)


def append_queue_cursor(
    project_root: Path | str,
    *,
    queue_name: str,
    cursor: str,
    event: str,
    entry_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Persist one append-only queue cursor checkpoint."""
    root = Path(project_root).resolve()
    payload = {
        "recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "queue_name": queue_name,
        "cursor": cursor,
        "event": event,
        "entry_id": entry_id,
        "details": details or {},
    }
    _append_jsonl(root / _QUEUE_STATE_DIR / _CURSOR_FILE, payload)


def read_retry_state(project_root: Path | str) -> list[dict[str, Any]]:
    """Load append-only retry evidence events."""
    root = Path(project_root).resolve()
    path = root / _QUEUE_STATE_DIR / _RETRY_STATE_FILE
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_queue_cursors(project_root: Path | str) -> list[dict[str, Any]]:
    """Load append-only queue cursor checkpoints."""
    root = Path(project_root).resolve()
    path = root / _QUEUE_STATE_DIR / _CURSOR_FILE
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _queue_entry_key(entry: dict[str, Any]) -> str | None:
    document = entry.get("document")
    if isinstance(document, dict):
        return document.get("_key") or document.get("id")
    return None


def _normalize_queue_entry(entry: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(entry)
    document = normalized.get("document")
    normalized["document"] = document if isinstance(document, dict) else {}
    normalized["queued_at"] = normalized.get("queued_at")
    normalized["operation"] = normalized.get("operation")
    normalized["collection"] = normalized.get("collection")
    normalized["old_rev"] = normalized.get("old_rev")
    normalized["attempts"] = int(normalized.get("attempts", 0) or 0)
    normalized["failure_class"] = normalized.get("failure_class")
    normalized["next_retry_after"] = normalized.get("next_retry_after")
    normalized["idempotency_key"] = normalized.get("idempotency_key")
    normalized["entry_id"] = normalized.get("idempotency_key") or _queue_entry_key(normalized)
    return normalized


def _normalize_quarantine_entry(entry: dict[str, Any], *, source_path: Path) -> dict[str, Any]:
    normalized = dict(entry)
    normalized["source_path"] = normalized.get("source_path") or str(source_path)
    normalized["raw_line"] = normalized.get("raw_line", "")
    normalized["error"] = normalized.get("error")
    normalized["quarantined_at"] = normalized.get("quarantined_at")
    normalized["entry_id"] = normalized.get("entry_id") or None
    return normalized


def _iter_jsonl(path: Path) -> Iterable[tuple[dict[str, Any] | None, str | None, str | None]]:
    if not path.exists():
        return ()

    def _generator() -> Iterable[tuple[dict[str, Any] | None, str | None, str | None]]:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                yield json.loads(line), None, None
            except json.JSONDecodeError as exc:
                yield None, raw_line, str(exc)

    return _generator()


def inspect_queue_state(project_root: Path | str) -> dict[str, Any]:
    """Return a structured local queue snapshot for operator surfaces."""
    root = Path(project_root).resolve()
    agent_root = root / ".agent"
    entries: dict[str, list[dict[str, Any]]] = {
        "pending": [],
        "failed": [],
        "expired": [],
        "quarantine": [],
    }

    for state in ("pending", "failed", "expired"):
        source_path = agent_root / _QUEUE_FILES[state]
        for payload, raw_line, error in _iter_jsonl(source_path):
            if payload is not None:
                entries[state].append(_normalize_queue_entry(payload))
            elif raw_line is not None and error is not None:
                entries["quarantine"].append(
                    _normalize_quarantine_entry(
                        {
                            "source_path": str(source_path),
                            "raw_line": raw_line,
                            "error": error,
                            "quarantined_at": None,
                        },
                        source_path=source_path,
                    )
                )

    quarantine_path = agent_root / _QUEUE_FILES["quarantine"]
    for payload, raw_line, error in _iter_jsonl(quarantine_path):
        if payload is not None:
            entries["quarantine"].append(_normalize_quarantine_entry(payload, source_path=quarantine_path))
        elif raw_line is not None and error is not None:
            entries["quarantine"].append(
                _normalize_quarantine_entry(
                    {
                        "source_path": str(quarantine_path),
                        "raw_line": raw_line,
                        "error": error,
                        "quarantined_at": None,
                    },
                    source_path=quarantine_path,
                )
            )

    counts = {
        "pending": len(entries["pending"]),
        "failed": len(entries["failed"]),
        "expired": len(entries["expired"]),
        "quarantine": len(entries["quarantine"]),
        "retry_scheduled": sum(1 for entry in entries["pending"] if entry.get("next_retry_after")),
        "dead_letter": len(entries["failed"]),
    }
    retry_state = read_retry_state(root)
    cursor_events = read_queue_cursors(root)
    counts["retry_evidence"] = len(retry_state)
    counts["cursor_checkpoints"] = len(cursor_events)
    return {
        "project_root": str(root),
        "agent_root": str(agent_root),
        "counts": counts,
        "entries": entries,
        "retry_state": retry_state,
        "cursor_events": cursor_events,
    }
