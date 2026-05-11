"""
Tests for governance/kg/query.py — AQL-based cross-project experiment search.

All tests mock the ArangoDB connection so they pass without a live instance.
"""
from unittest.mock import MagicMock, patch


def _make_cursor(rows):
    """Create a mock AQL cursor that iterates over the given rows."""
    cursor = MagicMock()
    cursor.__iter__ = MagicMock(return_value=iter(rows))
    return cursor


def test_find_experiments():
    """Basic call: single result with project prefix added to exp_id."""
    raw_row = {
        "exp_id": "EXP-001",
        "project": "overwatch",
        "classification": "CONFIRMATORY",
        "status": "completed",
        "last_run_id": "RUN-001",
        "provenance_sig": "SIG-20260401T000000Z-claude-abcd",
    }
    mock_cursor = _make_cursor([raw_row])

    with patch("gsigmad.governance.kg.query.ARANGO_AVAILABLE", True), \
         patch("gsigmad.governance.kg.query._get_db") as mock_get_db:
        mock_db = MagicMock()
        mock_db.aql.execute.return_value = mock_cursor
        mock_get_db.return_value = mock_db

        from gsigmad.governance.kg.query import find_experiments
        results = find_experiments()

    assert isinstance(results, list)
    assert len(results) == 1
    assert results[0]["exp_id"] == "overwatch:EXP-001"


def test_find_experiments_cross_project():
    """Cross-project search (project=None) passes null bind var to AQL."""
    mock_cursor = _make_cursor([])

    with patch("gsigmad.governance.kg.query.ARANGO_AVAILABLE", True), \
         patch("gsigmad.governance.kg.query._get_db") as mock_get_db:
        mock_db = MagicMock()
        mock_db.aql.execute.return_value = mock_cursor
        mock_get_db.return_value = mock_db

        from gsigmad.governance.kg.query import find_experiments
        find_experiments(project=None)

        # Verify the bind_vars passed to AQL contain project=None
        call_args = mock_db.aql.execute.call_args
        bind_vars = call_args[1].get("bind_vars") or call_args[0][1]
        assert "project" in bind_vars
        assert bind_vars["project"] is None


def test_find_experiments_protein_filter():
    """Protein filter passes protein name into AQL bind vars."""
    mock_cursor = _make_cursor([])

    with patch("gsigmad.governance.kg.query.ARANGO_AVAILABLE", True), \
         patch("gsigmad.governance.kg.query._get_db") as mock_get_db:
        mock_db = MagicMock()
        mock_db.aql.execute.return_value = mock_cursor
        mock_get_db.return_value = mock_db

        from gsigmad.governance.kg.query import find_experiments
        find_experiments(protein="TP53")

        call_args = mock_db.aql.execute.call_args
        bind_vars = call_args[1].get("bind_vars") or call_args[0][1]
        assert "protein" in bind_vars
        assert bind_vars["protein"] == "TP53"


def test_find_experiments_doi_filter():
    """DOI filter passes DOI into AQL bind vars."""
    mock_cursor = _make_cursor([])

    with patch("gsigmad.governance.kg.query.ARANGO_AVAILABLE", True), \
         patch("gsigmad.governance.kg.query._get_db") as mock_get_db:
        mock_db = MagicMock()
        mock_db.aql.execute.return_value = mock_cursor
        mock_get_db.return_value = mock_db

        from gsigmad.governance.kg.query import find_experiments
        find_experiments(doi="10.1001/jamainternmed.2013.13563")

        call_args = mock_db.aql.execute.call_args
        bind_vars = call_args[1].get("bind_vars") or call_args[0][1]
        assert bind_vars["doi"] == "10.1001/jamainternmed.2013.13563"


def test_find_experiments_pmid_filter():
    """PMID filter passes PMID into AQL bind vars."""
    mock_cursor = _make_cursor([])

    with patch("gsigmad.governance.kg.query.ARANGO_AVAILABLE", True), \
         patch("gsigmad.governance.kg.query._get_db") as mock_get_db:
        mock_db = MagicMock()
        mock_db.aql.execute.return_value = mock_cursor
        mock_get_db.return_value = mock_db

        from gsigmad.governance.kg.query import find_experiments
        find_experiments(pmid="24493081")

        call_args = mock_db.aql.execute.call_args
        bind_vars = call_args[1].get("bind_vars") or call_args[0][1]
        assert bind_vars["pmid"] == "24493081"


def test_find_experiments_namespace_format():
    """Namespace collision prevention: raw 'EXP-042' + project 'cellico' -> 'cellico:EXP-042'."""
    raw_row = {
        "exp_id": "EXP-042",
        "project": "cellico",
        "classification": "EXPLORATORY",
        "status": "in_progress",
        "last_run_id": "RUN-099",
        "provenance_sig": "SIG-20260301T120000Z-codex-1234",
    }
    mock_cursor = _make_cursor([raw_row])

    with patch("gsigmad.governance.kg.query.ARANGO_AVAILABLE", True), \
         patch("gsigmad.governance.kg.query._get_db") as mock_get_db:
        mock_db = MagicMock()
        mock_db.aql.execute.return_value = mock_cursor
        mock_get_db.return_value = mock_db

        from gsigmad.governance.kg.query import find_experiments
        results = find_experiments()

    assert results[0]["exp_id"] == "cellico:EXP-042"


def test_find_experiments_empty():
    """Empty cursor returns empty list, not an exception."""
    mock_cursor = _make_cursor([])

    with patch("gsigmad.governance.kg.query.ARANGO_AVAILABLE", True), \
         patch("gsigmad.governance.kg.query._get_db") as mock_get_db:
        mock_db = MagicMock()
        mock_db.aql.execute.return_value = mock_cursor
        mock_get_db.return_value = mock_db

        from gsigmad.governance.kg.query import find_experiments
        results = find_experiments()

    assert results == []


def test_find_experiments_no_arango():
    """When ARANGO_AVAILABLE is False, returns structured KG_UNAVAILABLE error dict."""
    with patch("gsigmad.governance.kg.query.ARANGO_AVAILABLE", False):
        from gsigmad.governance.kg.query import find_experiments
        result = find_experiments()

    assert isinstance(result, dict)
    assert result["pass"] is False
    assert "KG_UNAVAILABLE" in result["error"]


def test_format_results_table():
    """format_results_table returns markdown table containing the exp_id."""
    from gsigmad.governance.kg.query import format_results_table

    rows = [
        {
            "exp_id": "overwatch:EXP-001",
            "project": "overwatch",
            "classification": "CONFIRMATORY",
            "status": "completed",
            "last_run_id": "RUN-001",
            "provenance_sig": "SIG-20260401T000000Z-claude-abcd",
        }
    ]
    table = format_results_table(rows)
    assert "| overwatch:EXP-001 |" in table


def test_format_results_table_empty():
    """format_results_table with empty list returns human-readable no-results message."""
    from gsigmad.governance.kg.query import format_results_table

    result = format_results_table([])
    assert "No experiments found" in result
