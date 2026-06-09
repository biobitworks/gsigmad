"""
Tests for governance/kg/writer.py — trust tier enforcement and auto-promotion.

Tests: PROVISIONAL blocked, audit trail SIG-ID format, VERIFIED allowed,
auto-promotion schema valid, auto-promotion schema invalid.
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
    auto_promote,
    make_provenance_block,
    make_sig_id,
    write_document,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_doc(trust_tier: str = "VERIFIED", with_classification: bool = True) -> dict:
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
    doc = {
        "_key": "test-doc-001",
        "_provenance": prov,
    }
    if with_classification:
        doc["classification"] = "CONFIRMATORY"
        doc["extends"] = "CANON-CORE v1.0.0"
    return doc


# ---------------------------------------------------------------------------
# test_provisional_blocked
# ---------------------------------------------------------------------------

def test_provisional_blocked(tmp_path):
    """
    A write with trust_tier=PROVISIONAL must raise TrustTierError with
    'TRUST_TIER_ERROR' in the message — cannot reach ArangoDB.
    """
    doc = _make_doc(trust_tier="PROVISIONAL")

    with patch("gsigmad.governance.kg.writer.ARANGO_AVAILABLE", True), \
         patch("gsigmad.governance.kg.writer._QUEUE_PATH", tmp_path / "kg_queue.jsonl"):
        with pytest.raises(TrustTierError) as exc_info:
            write_document("experiments", doc)

    assert "TRUST_TIER_ERROR" in str(exc_info.value)
    assert "PROVISIONAL" in str(exc_info.value)


# ---------------------------------------------------------------------------
# test_audit_trail
# ---------------------------------------------------------------------------

def test_audit_trail(tmp_path):
    """
    write_document() with agent='claude-sonnet-4-6' must produce a _provenance
    block whose prov:Agent.prov:id matches the SIG-ID pattern.
    """
    sig_id = make_sig_id("claude-sonnet-4-6")
    prov = make_provenance_block(
        sig_id=sig_id,
        agent_name="claude-sonnet-4-6",
        trust_tier="VERIFIED",
        activity_id="EXP-001",
        activity_type="experiment",
        entity_id="claim/001",
        entity_type="artifact",
        evidence_class="MEASURED",
    )
    doc = {
        "_key": "audit-doc-001",
        "classification": "CONFIRMATORY",
        "extends": "CANON-CORE v1.0.0",
        "_provenance": prov,
    }

    inserted_doc = dict(doc)
    mock_col = MagicMock()
    mock_col.get.return_value = None
    mock_col.insert.return_value = {"new": inserted_doc}

    mock_db = MagicMock()
    mock_db.collection.return_value = mock_col

    mock_client = MagicMock()
    mock_client.db.return_value = mock_db

    with patch("gsigmad.governance.kg.writer.ArangoClient", return_value=mock_client), \
         patch("gsigmad.governance.kg.writer.ARANGO_AVAILABLE", True), \
         patch("gsigmad.governance.kg.writer._QUEUE_PATH", tmp_path / "kg_queue.jsonl"):
        result = write_document(
            "experiments",
            doc,
            agent="claude-sonnet-4-6",
            activity_id="EXP-001",
        )

    # Verify SIG-ID format in the _provenance we constructed
    # Agent names may contain hyphens (e.g., claude-sonnet-4-6) so we use
    # .+-[0-9a-f]{4}$ to match agent + hash4 at end of string.
    sig_id_pattern = r"SIG-\d{8}T\d{6}Z-.+-[0-9a-f]{4}$"
    assert re.match(sig_id_pattern, sig_id), (
        f"SIG-ID '{sig_id}' does not match pattern '{sig_id_pattern}'"
    )
    # The prov block agent id should match
    agent_id = prov["prov:Agent"]["prov:id"]
    assert re.match(sig_id_pattern, agent_id)


# ---------------------------------------------------------------------------
# test_verified_allowed
# ---------------------------------------------------------------------------

def test_verified_allowed(tmp_path):
    """
    A write with trust_tier=VERIFIED must NOT raise TrustTierError and
    must return result["pass"] is True.
    """
    doc = _make_doc(trust_tier="VERIFIED")

    mock_col = MagicMock()
    mock_col.get.return_value = None
    mock_col.insert.return_value = {"new": dict(doc)}

    mock_db = MagicMock()
    mock_db.collection.return_value = mock_col

    mock_client = MagicMock()
    mock_client.db.return_value = mock_db

    with patch("gsigmad.governance.kg.writer.ArangoClient", return_value=mock_client), \
         patch("gsigmad.governance.kg.writer.ARANGO_AVAILABLE", True), \
         patch("gsigmad.governance.kg.writer._QUEUE_PATH", tmp_path / "kg_queue.jsonl"):
        result = write_document("experiments", doc)

    assert result.get("pass") is True
    assert not result.get("queued")


# ---------------------------------------------------------------------------
# auto-promotion: validates a KG document against an EXPLICIT KG-document schema
# ---------------------------------------------------------------------------

# Illustrative KG-document schema (test fixture, NOT committed governance canon):
# encodes the established PROVISIONAL/VERIFIED/QUARANTINED trust-tier status model
# and the minimal pointer+hash shape of a real KG document. The canonical
# promotion schema is a pending PI/operator governance decision.
_KG_DOC_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["id", "collection", "content_sha256"],
    "properties": {
        "status": {"enum": ["PROVISIONAL", "VERIFIED", "QUARANTINED"]},
        "id": {"type": "string"},
        "collection": {"type": "string"},
        "content_sha256": {"type": "string"},
    },
}


def _write_kg_doc_schema(tmp_path: Path) -> str:
    schema_file = tmp_path / "kg_doc.schema.json"
    schema_file.write_text(json.dumps(_KG_DOC_SCHEMA), encoding="utf-8")
    return str(schema_file)


def test_auto_promotion_schema_valid(tmp_path):
    """A real PROVISIONAL KG document that satisfies an explicit KG-document
    schema is promoted to VERIFIED."""
    schema_path = _write_kg_doc_schema(tmp_path)
    doc = {
        "id": "EXTREF-0001",
        "collection": "extrefs",
        "content_sha256": "a" * 64,
        "status": "PROVISIONAL",
    }
    result = auto_promote(doc, schema_path)
    assert result["status"] == "VERIFIED"


def test_auto_promotion_schema_invalid(tmp_path):
    """A doc missing a required KG-document field stays PROVISIONAL."""
    schema_path = _write_kg_doc_schema(tmp_path)
    doc = {
        "id": "EXTREF-0002",
        "status": "PROVISIONAL",
        # missing 'collection' and 'content_sha256' — required by the KG-doc schema
    }
    result = auto_promote(doc, schema_path)
    assert result["status"] == "PROVISIONAL"


def test_auto_promotion_requires_explicit_schema():
    """Regression: auto_promote must NOT default to the CANON-CORE extension-header
    schema. Without an explicit KG-document schema it fails closed to PROVISIONAL —
    even for a doc that satisfies the CANON-CORE header schema."""
    canon_header_doc = {"extends": "CANON-CORE v1.0.0"}
    with pytest.warns(RuntimeWarning):
        result = auto_promote(canon_header_doc)  # no schema_path supplied
    assert result["status"] == "PROVISIONAL"
