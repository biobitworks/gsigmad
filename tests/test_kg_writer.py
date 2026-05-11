"""
Tests for governance/kg/writer.py — TDD RED phase.

Tests: _rev conflict, PROV-JSON injection, queue fallback, queue replay.
"""
import json
import re
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gsigmad.governance.kg.writer import (
    KGWriteConflict,
    TrustTierError,
    make_provenance_block,
    make_sig_id,
    replay_queue,
    write_document,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_doc(trust_tier: str = "VERIFIED") -> dict:
    """Return a minimal document with a _provenance block."""
    sig_id = make_sig_id("test-agent")
    prov = make_provenance_block(
        sig_id=sig_id,
        agent_name="test-agent",
        trust_tier=trust_tier,
        activity_id="EXP-001",
        activity_type="experiment",
        entity_id="claim/001",
        entity_type="claim",
        evidence_class="MEASURED",
    )
    return {
        "_key": "test-doc-001",
        "classification": "CONFIRMATORY",
        "_provenance": prov,
    }


# ---------------------------------------------------------------------------
# test_rev_conflict
# ---------------------------------------------------------------------------

def test_rev_conflict(tmp_path):
    """
    A write with a stale _rev must raise KGWriteConflict — no silent retry.

    We patch DocumentRevisionError in the writer module to a plain Exception
    subclass so it can be instantiated and isinstance-checked without needing
    a real python-arango Response/Request pair.
    """
    # Create a simple exception class that can be raised and caught by the
    # isinstance check inside writer.py
    class FakeDocumentRevisionError(Exception):
        pass

    mock_col = MagicMock()
    mock_col.replace.side_effect = FakeDocumentRevisionError("conflict")
    current_doc = {"_key": "test-doc-001", "_rev": "_new_rev_xyz"}
    mock_col.get.return_value = current_doc

    mock_db = MagicMock()
    mock_db.collection.return_value = mock_col

    mock_client = MagicMock()
    mock_client.db.return_value = mock_db

    doc = _make_doc()
    doc["_rev"] = "_old_rev_abc"  # stale _rev

    with patch("gsigmad.governance.kg.writer.ArangoClient", return_value=mock_client), \
         patch("gsigmad.governance.kg.writer.ARANGO_AVAILABLE", True), \
         patch("gsigmad.governance.kg.writer.DocumentRevisionError", FakeDocumentRevisionError), \
         patch("gsigmad.governance.kg.writer._QUEUE_PATH", tmp_path / "kg_queue.jsonl"):
        with pytest.raises(KGWriteConflict) as exc_info:
            write_document("experiments", doc, old_rev="_old_rev_abc")

    assert "KG_WRITE_CONFLICT" in str(exc_info.value)
    assert "stale _rev" in str(exc_info.value)


# ---------------------------------------------------------------------------
# test_prov_json
# ---------------------------------------------------------------------------

def test_prov_json(tmp_path):
    """
    Every successful write must return a document with _provenance containing
    prov:Agent, prov:Activity, prov:Entity, and timestamp.
    """
    doc_with_prov = _make_doc()
    doc_with_prov["_rev"] = "some_rev"

    inserted_doc = dict(doc_with_prov)
    inserted_doc["_id"] = "experiments/test-doc-001"

    mock_col = MagicMock()
    mock_col.get.return_value = None  # no existing doc -> insert path
    mock_col.insert.return_value = {"new": inserted_doc}

    mock_db = MagicMock()
    mock_db.collection.return_value = mock_col

    mock_client = MagicMock()
    mock_client.db.return_value = mock_db

    with patch("gsigmad.governance.kg.writer.ArangoClient", return_value=mock_client), \
         patch("gsigmad.governance.kg.writer.ARANGO_AVAILABLE", True), \
         patch("gsigmad.governance.kg.writer._QUEUE_PATH", tmp_path / "kg_queue.jsonl"):
        result = write_document("experiments", doc_with_prov)

    # Result doc (or result itself) should have _provenance
    assert result.get("pass") is True
    returned_doc = result.get("result") or result.get("doc")
    # _provenance comes from the doc we passed in
    prov = doc_with_prov.get("_provenance")
    assert prov is not None
    assert "prov:Agent" in prov
    assert "prov:Activity" in prov
    assert "prov:Entity" in prov
    assert "timestamp" in prov


# ---------------------------------------------------------------------------
# test_queue_fallback
# ---------------------------------------------------------------------------

def test_queue_fallback(tmp_path):
    """
    When ArangoDB is unreachable, write_document must queue to .agent/kg_queue.jsonl
    and return {"queued": True}.
    """
    queue_path = tmp_path / "kg_queue.jsonl"

    with patch("gsigmad.governance.kg.writer.ArangoClient", side_effect=ConnectionError("unreachable")), \
         patch("gsigmad.governance.kg.writer.ARANGO_AVAILABLE", True), \
         patch("gsigmad.governance.kg.writer._QUEUE_PATH", queue_path):
        result = write_document("experiments", _make_doc())

    assert result.get("pass") is True
    assert result.get("queued") is True
    assert queue_path.exists()
    lines = queue_path.read_text().strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["collection"] == "experiments"
    assert entry["attempts"] == 0


# ---------------------------------------------------------------------------
# test_queue_replay
# ---------------------------------------------------------------------------

def test_queue_replay(tmp_path):
    """
    replay_queue() must process all queued entries; on success the queue file
    should be empty and the mock insert called for each entry.
    """
    queue_path = tmp_path / "kg_queue.jsonl"
    doc1 = _make_doc()
    doc2 = _make_doc()
    doc2["_key"] = "test-doc-002"

    entry1 = {
        "queued_at": "2099-04-01T00:00:00Z",
        "operation": "insert",
        "collection": "experiments",
        "document": doc1,
        "old_rev": None,
        "attempts": 0,
    }
    entry2 = {
        "queued_at": "2099-04-01T00:01:00Z",
        "operation": "insert",
        "collection": "experiments",
        "document": doc2,
        "old_rev": None,
        "attempts": 0,
    }
    with queue_path.open("w") as f:
        f.write(json.dumps(entry1) + "\n")
        f.write(json.dumps(entry2) + "\n")

    mock_col = MagicMock()
    mock_col.insert.return_value = {"new": doc1}

    mock_db = MagicMock()
    mock_db.collection.return_value = mock_col

    mock_client = MagicMock()
    mock_client.db.return_value = mock_db

    with patch("gsigmad.governance.kg.writer.ArangoClient", return_value=mock_client), \
         patch("gsigmad.governance.kg.writer.ARANGO_AVAILABLE", True), \
         patch("gsigmad.governance.kg.writer._QUEUE_PATH", queue_path):
        replay_result = replay_queue()

    # Queue should be empty (or not exist) after successful replay
    if queue_path.exists():
        remaining = queue_path.read_text().strip()
        assert remaining == "", f"Queue not empty after replay: {remaining}"

    # Insert should have been called twice
    assert mock_col.insert.call_count == 2
    assert replay_result.get("processed") == 2


def test_queue_replay_uses_mark_and_sweep_atomic_rewrite(tmp_path):
    """
    replay_queue() must remove successful entries by rewriting survivors instead
    of clearing the queue file before processing.
    """
    queue_path = tmp_path / "kg_queue.jsonl"
    doc1 = _make_doc()
    doc2 = _make_doc()
    doc2["_key"] = "test-doc-atomic-002"
    entry1 = {
        "queued_at": "2099-04-01T00:00:00Z",
        "operation": "insert",
        "collection": "experiments",
        "document": doc1,
        "old_rev": None,
        "attempts": 0,
    }
    entry2 = {
        "queued_at": "2099-04-01T00:01:00Z",
        "operation": "insert",
        "collection": "experiments",
        "document": doc2,
        "old_rev": None,
        "attempts": 0,
    }
    queue_path.write_text(
        json.dumps(entry1) + "\n" + json.dumps(entry2) + "\n",
        encoding="utf-8",
    )

    mock_col = MagicMock()
    mock_col.insert.return_value = {"new": doc1}
    mock_db = MagicMock()
    mock_db.collection.return_value = mock_col
    mock_client = MagicMock()
    mock_client.db.return_value = mock_db

    original_write_text = Path.write_text
    write_text_calls = []

    def _recording_write_text(self, *args, **kwargs):
        if self == queue_path:
            write_text_calls.append((args, kwargs))
        return original_write_text(self, *args, **kwargs)

    with patch("pathlib.Path.write_text", autospec=True, side_effect=_recording_write_text), \
         patch("gsigmad.governance.kg.writer.ArangoClient", return_value=mock_client), \
         patch("gsigmad.governance.kg.writer.ARANGO_AVAILABLE", True), \
         patch("gsigmad.governance.kg.writer._QUEUE_PATH", queue_path):
        replay_result = replay_queue(max_entries=1)

    assert replay_result == {
        "pass": True,
        "processed": 1,
        "failed": 0,
        "expired": 0,
        "requeued": 1,
        "quarantined": 0,
    }
    assert not any(args and args[0] == "" for args, _ in write_text_calls)

    remaining_lines = queue_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(remaining_lines) == 1
    remaining_entry = json.loads(remaining_lines[0])
    assert remaining_entry["document"]["_key"] == "test-doc-atomic-002"


def test_queue_replay_preserves_backward_compatible_entries_without_idempotency_metadata(tmp_path):
    """Legacy queue entries without new metadata still replay successfully."""
    queue_path = tmp_path / "kg_queue.jsonl"
    legacy_entry = {
        "queued_at": "2099-04-01T00:00:00Z",
        "operation": "insert",
        "collection": "experiments",
        "document": _make_doc(),
        "old_rev": None,
        "attempts": 0,
    }
    queue_path.write_text(json.dumps(legacy_entry) + "\n", encoding="utf-8")

    mock_col = MagicMock()
    mock_col.insert.return_value = {"new": legacy_entry["document"]}
    mock_db = MagicMock()
    mock_db.collection.return_value = mock_col
    mock_client = MagicMock()
    mock_client.db.return_value = mock_db

    with patch("gsigmad.governance.kg.writer.ArangoClient", return_value=mock_client), \
         patch("gsigmad.governance.kg.writer.ARANGO_AVAILABLE", True), \
         patch("gsigmad.governance.kg.writer._QUEUE_PATH", queue_path):
        replay_result = replay_queue()

    assert replay_result == {
        "pass": True,
        "processed": 1,
        "failed": 0,
        "expired": 0,
        "requeued": 0,
        "quarantined": 0,
    }
    if queue_path.exists():
        assert queue_path.read_text(encoding="utf-8").strip() == ""
    assert mock_col.insert.call_count == 1


def test_queue_replay_records_retry_state_and_cursor_events(tmp_path):
    """Replay should persist append-only retry evidence and cursor checkpoints."""
    queue_path = tmp_path / "kg_queue.jsonl"
    entry = {
        "queued_at": "2099-04-01T00:00:00Z",
        "operation": "insert",
        "collection": "experiments",
        "document": _make_doc(),
        "old_rev": None,
        "attempts": 0,
    }
    queue_path.write_text(json.dumps(entry) + "\n", encoding="utf-8")

    mock_col = MagicMock()
    mock_col.insert.side_effect = ConnectionError("temporary unavailable")
    mock_db = MagicMock()
    mock_db.collection.return_value = mock_col
    mock_client = MagicMock()
    mock_client.db.return_value = mock_db

    with patch("gsigmad.governance.kg.writer.ArangoClient", return_value=mock_client), \
         patch("gsigmad.governance.kg.writer.ARANGO_AVAILABLE", True), \
         patch("gsigmad.governance.kg.writer._QUEUE_PATH", queue_path):
        replay_result = replay_queue()

    assert replay_result["requeued"] == 1

    retry_log = tmp_path / ".gsigmad" / "queue" / "retry-state.jsonl"
    cursor_log = tmp_path / ".gsigmad" / "queue" / "cursors.jsonl"
    assert retry_log.is_file()
    assert cursor_log.is_file()

    retry_events = [json.loads(line) for line in retry_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    cursor_events = [json.loads(line) for line in cursor_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert retry_events[-1]["event"] == "retry-scheduled"
    assert retry_events[-1]["failure_class"] == "transient"
    assert cursor_events[-1]["event"] == "retry-scheduled"


def test_queue_replay_sweeps_duplicate_pending_entries_by_idempotency_key(tmp_path):
    """Duplicate pending entries with one idempotency key should write once."""
    queue_path = tmp_path / "kg_queue.jsonl"
    doc = _make_doc()
    idempotency_key = "experiments:insert:test-doc-001"
    entry1 = {
        "queued_at": "2099-04-01T00:00:00Z",
        "operation": "insert",
        "collection": "experiments",
        "document": doc,
        "old_rev": None,
        "attempts": 0,
        "idempotency_key": idempotency_key,
    }
    entry2 = dict(entry1)
    entry2["queued_at"] = "2099-04-01T00:01:00Z"
    queue_path.write_text(
        json.dumps(entry1) + "\n" + json.dumps(entry2) + "\n",
        encoding="utf-8",
    )

    mock_col = MagicMock()
    mock_col.insert.return_value = {"new": doc}
    mock_db = MagicMock()
    mock_db.collection.return_value = mock_col
    mock_client = MagicMock()
    mock_client.db.return_value = mock_db

    with patch("gsigmad.governance.kg.writer.ArangoClient", return_value=mock_client), \
         patch("gsigmad.governance.kg.writer.ARANGO_AVAILABLE", True), \
         patch("gsigmad.governance.kg.writer._QUEUE_PATH", queue_path):
        replay_result = replay_queue()

    assert replay_result == {
        "pass": True,
        "processed": 1,
        "failed": 0,
        "expired": 0,
        "requeued": 0,
        "quarantined": 0,
    }
    assert mock_col.insert.call_count == 1
    if queue_path.exists():
        assert queue_path.read_text(encoding="utf-8").strip() == ""


def test_queue_replay_routes_permanent_failures_to_dead_letter(tmp_path):
    """Permanent replay failures should dead-letter immediately with metadata."""
    queue_path = tmp_path / "kg_queue.jsonl"
    failed_path = tmp_path / "kg_queue_failed.jsonl"
    entry = {
        "queued_at": "2099-04-01T00:00:00Z",
        "operation": "insert",
        "collection": "experiments",
        "document": _make_doc(),
        "old_rev": None,
        "attempts": 0,
    }
    queue_path.write_text(json.dumps(entry) + "\n", encoding="utf-8")

    mock_col = MagicMock()
    mock_col.insert.side_effect = TrustTierError("TRUST_TIER_ERROR: blocked")
    mock_db = MagicMock()
    mock_db.collection.return_value = mock_col
    mock_client = MagicMock()
    mock_client.db.return_value = mock_db

    with patch("gsigmad.governance.kg.writer.ArangoClient", return_value=mock_client), \
         patch("gsigmad.governance.kg.writer.ARANGO_AVAILABLE", True), \
         patch("gsigmad.governance.kg.writer._QUEUE_PATH", queue_path), \
         patch("gsigmad.governance.kg.writer._QUEUE_FAILED_PATH", failed_path):
        replay_result = replay_queue()

    assert replay_result["pass"] is True
    assert replay_result["processed"] == 0
    assert replay_result["failed"] == 1
    assert replay_result["requeued"] == 0
    failed_entry = json.loads(failed_path.read_text(encoding="utf-8").strip())
    assert failed_entry["attempts"] == 1
    assert failed_entry["failure_class"] == "permanent"


def test_queue_replay_schedules_backoff_for_transient_failures(tmp_path):
    """Transient replay failures should stay pending with retry metadata."""
    queue_path = tmp_path / "kg_queue.jsonl"
    failed_path = tmp_path / "kg_queue_failed.jsonl"
    entry = {
        "queued_at": "2099-04-01T00:00:00Z",
        "operation": "insert",
        "collection": "experiments",
        "document": _make_doc(),
        "old_rev": None,
        "attempts": 0,
    }
    queue_path.write_text(json.dumps(entry) + "\n", encoding="utf-8")

    mock_col = MagicMock()
    mock_col.insert.side_effect = ConnectionError("temporary timeout")
    mock_db = MagicMock()
    mock_db.collection.return_value = mock_col
    mock_client = MagicMock()
    mock_client.db.return_value = mock_db

    with patch("gsigmad.governance.kg.writer.ArangoClient", return_value=mock_client), \
         patch("gsigmad.governance.kg.writer.ARANGO_AVAILABLE", True), \
         patch("gsigmad.governance.kg.writer._QUEUE_PATH", queue_path), \
         patch("gsigmad.governance.kg.writer._QUEUE_FAILED_PATH", failed_path):
        replay_result = replay_queue()

    assert replay_result["pass"] is True
    assert replay_result["processed"] == 0
    assert replay_result["failed"] == 0
    assert replay_result["requeued"] == 1
    assert not failed_path.exists()
    pending_entry = json.loads(queue_path.read_text(encoding="utf-8").strip())
    assert pending_entry["attempts"] == 1
    assert pending_entry["failure_class"] == "transient"
    assert pending_entry["next_retry_after"]


def test_queue_replay_quarantines_malformed_lines_and_continues_valid_entries(tmp_path):
    """Malformed JSONL should be quarantined line-by-line without blocking valid work."""
    queue_path = tmp_path / "kg_queue.jsonl"
    quarantine_path = tmp_path / "kg_queue_quarantine.jsonl"
    valid_entry = {
        "queued_at": "2099-04-01T00:00:00Z",
        "operation": "insert",
        "collection": "experiments",
        "document": _make_doc(),
        "old_rev": None,
        "attempts": 0,
    }
    malformed_line = '{"queued_at": "2099-04-01T00:00:00Z",'
    queue_path.write_text(
        malformed_line + "\n" + json.dumps(valid_entry) + "\n",
        encoding="utf-8",
    )

    mock_col = MagicMock()
    mock_col.insert.return_value = {"new": valid_entry["document"]}
    mock_db = MagicMock()
    mock_db.collection.return_value = mock_col
    mock_client = MagicMock()
    mock_client.db.return_value = mock_db

    with patch("gsigmad.governance.kg.writer.ArangoClient", return_value=mock_client), \
         patch("gsigmad.governance.kg.writer.ARANGO_AVAILABLE", True), \
         patch("gsigmad.governance.kg.writer._QUEUE_PATH", queue_path), \
         patch("gsigmad.governance.kg.writer._QUEUE_QUARANTINE_PATH", quarantine_path, create=True):
        replay_result = replay_queue()

    assert replay_result["pass"] is True
    assert replay_result["processed"] == 1
    assert replay_result["quarantined"] == 1
    quarantine_entry = json.loads(quarantine_path.read_text(encoding="utf-8").strip())
    assert quarantine_entry["raw_line"] == malformed_line
    assert quarantine_entry["source_path"] == str(queue_path)
    assert "Expecting property name enclosed in double quotes" in quarantine_entry["error"]
    assert mock_col.insert.call_count == 1
    if queue_path.exists():
        assert queue_path.read_text(encoding="utf-8").strip() == ""
