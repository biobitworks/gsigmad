"""
KG citation tests — Phase 3, Plan 04.
Tests for governance/kg/citations.py: create_citation_edge() and get_or_create_publication().
"""
from unittest.mock import MagicMock, patch, call

import pytest


def test_citation_edge():
    """KG-02: create_citation_edge() inserts rels edge with rel_type='references' from experiment to publication."""
    mock_write_result = {"pass": True, "result": {}}
    mock_pub_key = "pub_key_abc"

    with patch("gsigmad.governance.kg.citations.verify_doi") as mock_verify_doi, \
         patch("gsigmad.governance.kg.citations.write_document") as mock_write_doc, \
         patch("gsigmad.governance.kg.citations.get_or_create_publication") as mock_get_pub:

        mock_verify_doi.return_value = {"verified": True, "title": "Test Paper"}
        mock_write_doc.return_value = mock_write_result
        mock_get_pub.return_value = mock_pub_key

        from gsigmad.governance.kg.citations import create_citation_edge
        result = create_citation_edge(
            exp_key="overwatch_exp_015",
            doi="10.1371/test",
            citation_type="supports"
        )

    # write_document called with rels collection
    assert mock_write_doc.called
    call_kwargs = mock_write_doc.call_args
    assert call_kwargs[1]["collection"] == "rels" or (
        len(call_kwargs[0]) > 0 and call_kwargs[0][0] == "rels"
    )
    # doc has correct _from and rel_type
    doc_arg = call_kwargs[1].get("doc") or call_kwargs[0][1]
    assert doc_arg["_from"] == "experiments/overwatch_exp_015"
    assert doc_arg["_to"] == "publications/pub_key_abc"
    assert doc_arg["rel_type"] == "references"
    assert result == mock_write_result


def test_citation_doi_resolution():
    """KG-02: create_citation_edge() returns error dict when verify_doi() fails; write_document not called."""
    with patch("gsigmad.governance.kg.citations.verify_doi") as mock_verify_doi, \
         patch("gsigmad.governance.kg.citations.write_document") as mock_write_doc:

        mock_verify_doi.return_value = {"verified": False, "error": "DOI_VERIFICATION_ERROR: DOI does not exist"}

        from gsigmad.governance.kg.citations import create_citation_edge
        result = create_citation_edge(
            exp_key="overwatch_exp_015",
            doi="10.1371/nonexistent",
        )

    assert result["pass"] is False
    assert "DOI_VERIFICATION_ERROR" in result["error"]
    mock_write_doc.assert_not_called()


def test_citation_pmid_resolution():
    """KG-02: create_citation_edge() calls verify_pmid() (not verify_doi) for PMID-only references."""
    mock_write_result = {"pass": True, "result": {}}
    mock_pub_key = "pub_key_pmid"

    with patch("gsigmad.governance.kg.citations.verify_doi") as mock_verify_doi, \
         patch("gsigmad.governance.kg.citations.verify_pmid") as mock_verify_pmid, \
         patch("gsigmad.governance.kg.citations.write_document") as mock_write_doc, \
         patch("gsigmad.governance.kg.citations.get_or_create_publication") as mock_get_pub:

        mock_verify_pmid.return_value = {"verified": True, "title": "PubMed Paper"}
        mock_write_doc.return_value = mock_write_result
        mock_get_pub.return_value = mock_pub_key

        from gsigmad.governance.kg.citations import create_citation_edge
        create_citation_edge(
            exp_key="overwatch_exp_015",
            pmid="25147205",
        )

    mock_verify_doi.assert_not_called()
    mock_verify_pmid.assert_called_once_with("25147205")


def test_citation_prov_block():
    """KG-02: doc passed to write_document() must NOT contain _provenance — writer.py injects it."""
    mock_write_result = {"pass": True, "result": {}}
    mock_pub_key = "pub_key_prov"

    with patch("gsigmad.governance.kg.citations.verify_doi") as mock_verify_doi, \
         patch("gsigmad.governance.kg.citations.write_document") as mock_write_doc, \
         patch("gsigmad.governance.kg.citations.get_or_create_publication") as mock_get_pub:

        mock_verify_doi.return_value = {"verified": True, "title": "Provenance Test Paper"}
        mock_write_doc.return_value = mock_write_result
        mock_get_pub.return_value = mock_pub_key

        from gsigmad.governance.kg.citations import create_citation_edge
        create_citation_edge(
            exp_key="overwatch_exp_015",
            doi="10.1371/prov-test",
        )

    call_kwargs = mock_write_doc.call_args
    doc_arg = call_kwargs[1].get("doc") or call_kwargs[0][1]
    assert "_provenance" not in doc_arg, (
        "citations.py must NOT set _provenance — writer.py injects it"
    )


def test_citation_pending_doi():
    """KG-02: UNVERIFIED_PENDING DOIs are blocked — returns error dict without calling write_document."""
    with patch("gsigmad.governance.kg.citations.verify_doi") as mock_verify_doi, \
         patch("gsigmad.governance.kg.citations.write_document") as mock_write_doc:

        mock_verify_doi.return_value = {
            "verified": "TIMEOUT",
            "warning": "DOI_VERIFICATION_TIMEOUT: UNVERIFIED_PENDING"
        }

        from gsigmad.governance.kg.citations import create_citation_edge
        result = create_citation_edge(
            exp_key="overwatch_exp_015",
            doi="10.1371/pending-doi",
        )

    assert result["pass"] is False
    assert "UNVERIFIED_PENDING" in result["error"] or "TIMEOUT" in result["error"]
    mock_write_doc.assert_not_called()


def test_get_or_create_publication_exists():
    """KG-02: get_or_create_publication returns existing _key without inserting when pub already exists."""
    mock_cursor = MagicMock()
    mock_cursor.__iter__ = MagicMock(return_value=iter(["pub_key_existing"]))

    with patch("gsigmad.governance.kg.citations.write_document") as mock_write_doc, \
         patch("gsigmad.governance.kg.citations._get_db") as mock_get_db:

        mock_db = MagicMock()
        mock_db.aql.execute.return_value = mock_cursor
        mock_get_db.return_value = mock_db

        from gsigmad.governance.kg.citations import get_or_create_publication
        result = get_or_create_publication(doi="10.1371/test")

    assert result == "pub_key_existing"
    mock_write_doc.assert_not_called()


def test_get_or_create_publication_new():
    """KG-02: get_or_create_publication calls write_document(collection='publications') when pub not found."""
    mock_cursor_empty = MagicMock()
    mock_cursor_empty.__iter__ = MagicMock(return_value=iter([]))

    with patch("gsigmad.governance.kg.citations.write_document") as mock_write_doc, \
         patch("gsigmad.governance.kg.citations._get_db") as mock_get_db:

        mock_db = MagicMock()
        mock_db.aql.execute.return_value = mock_cursor_empty
        mock_get_db.return_value = mock_db
        mock_write_doc.return_value = {"pass": True, "result": {"_key": "new_pub_key"}}

        from gsigmad.governance.kg.citations import get_or_create_publication
        result = get_or_create_publication(doi="10.1371/new")

    assert result == "new_pub_key"
    mock_write_doc.assert_called_once()
    call_kwargs = mock_write_doc.call_args
    collection_arg = call_kwargs[1].get("collection") or call_kwargs[0][0]
    assert collection_arg == "publications"
