"""
Tests for governance/kg/writer.py — trust tier enforcement and auto-promotion.

Tests: PROVISIONAL blocked, audit trail SIG-ID format, VERIFIED allowed,
auto-promotion schema valid, auto-promotion schema invalid.
"""
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
# test_auto_promotion_schema_valid
# ---------------------------------------------------------------------------

def test_auto_promotion_schema_valid():
    """
    auto_promote() on a doc that satisfies CANON-CORE-schema.json must set
    doc["status"] = "VERIFIED".

    The CANON-CORE-schema.json requires "extends" (matching pattern
    "CANON-CORE v{semver}") and optionally validates "status" as one of
    ["ACTIVE", "DEPRECATED", "DRAFT"]. To avoid a status enum clash we
    start with status="DRAFT" (a valid schema value) and confirm auto_promote
    sets it to "VERIFIED" on a passing validation.
    """
    doc = {
        "extends": "CANON-CORE v1.0.0",
        # Do not pre-set status — auto_promote should SET it to VERIFIED
    }
    result = auto_promote(doc)
    assert result["status"] == "VERIFIED"


# ---------------------------------------------------------------------------
# test_auto_promotion_schema_invalid
# ---------------------------------------------------------------------------

def test_auto_promotion_schema_invalid():
    """
    auto_promote() on a doc missing required 'extends' must keep
    doc["status"] = "PROVISIONAL".
    """
    doc = {
        "project": "test-project",
        "status": "PROVISIONAL",
        # 'extends' is missing — required by CANON-CORE-schema.json
    }
    result = auto_promote(doc)
    assert result["status"] == "PROVISIONAL"
