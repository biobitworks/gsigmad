"""Tests for EXP-02: session-start EXP status summary."""
import warnings
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Import guard — module does not exist until Wave 2
# ---------------------------------------------------------------------------
try:
    from gsigmad.governance.compiler.session_status import (
        get_exp_status_summary,
        render_exp_table,
    )
    SESSION_STATUS_AVAILABLE = True
except ImportError:
    get_exp_status_summary = None
    render_exp_table = None
    SESSION_STATUS_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not SESSION_STATUS_AVAILABLE,
    reason="gsigmad.governance.compiler.session_status not yet implemented (Wave 2)",
)


# ---------------------------------------------------------------------------
# test_exp_status
# ---------------------------------------------------------------------------
def test_exp_status(tmp_path):
    """get_exp_status_summary returns a list of EXP dicts with required fields."""
    sample_docs = [
        {
            "exp_id": "EXP-001",
            "classification": "SCIENCE",
            "status": "completed",
            "project": "gettingsciencedone",
            "last_run_id": "RUN-001",
        },
        {
            "exp_id": "EXP-002",
            "classification": "EXPLORATORY",
            "status": "in_progress",
            "project": "overwatch",
            "last_run_id": None,
        },
    ]

    # Mock ArangoClient so no real DB connection is needed
    mock_cursor = iter(sample_docs)
    mock_db = MagicMock()
    mock_db.aql.execute.return_value = mock_cursor
    mock_client = MagicMock()
    mock_client.db.return_value = mock_db

    with patch("gsigmad.governance.compiler.session_status.ARANGO_AVAILABLE", True), \
         patch("gsigmad.governance.compiler.session_status.ArangoClient", return_value=mock_client) as arango_client:
        result = get_exp_status_summary(str(tmp_path))

    arango_client.assert_called_once_with(hosts="http://localhost:8531", request_timeout=0.5)
    assert result["pass"] is True
    exps = result["exps"]
    assert isinstance(exps, list)
    assert len(exps) == 2

    required_fields = {"exp_id", "classification", "status", "project", "last_run_id"}
    for exp in exps:
        assert required_fields.issubset(set(exp.keys())), (
            f"EXP dict missing fields: {required_fields - set(exp.keys())}"
        )

    assert result["source"] in ("kg", "local_fallback")
    # When KG succeeds, source should be "kg"
    assert result["source"] == "kg"


# ---------------------------------------------------------------------------
# test_exp_status_kg_unavailable_fallback
# ---------------------------------------------------------------------------
def test_exp_status_kg_unavailable_fallback(tmp_path):
    """Falls back to local file scan with KG_UNAVAILABLE warning when ArangoDB is unreachable."""
    # Set up modern gsigmad local experiment structure
    exp_dir = tmp_path / ".gsigmad" / "experiments"
    exp_dir.mkdir(parents=True)
    (exp_dir / "EXP-1.1.yaml").write_text(
        "\n".join(
            [
                "exp_id: EXP-1.1",
                "classification: EXPLORATORY",
                "status: planned",
                "project: demo-project",
            ]
        )
    )

    # Force ArangoDB connection to fail (ARANGO_AVAILABLE=True but client raises)
    mock_client = MagicMock()
    mock_client.db.side_effect = ConnectionRefusedError("Connection refused")

    with patch("gsigmad.governance.compiler.session_status.ARANGO_AVAILABLE", True), \
         patch("gsigmad.governance.compiler.session_status.ArangoClient", return_value=mock_client):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = get_exp_status_summary(str(tmp_path))

    assert result["pass"] is True
    assert result["source"] == "local_fallback"
    assert result["warning"] is not None
    assert "KG_UNAVAILABLE" in result["warning"]

    # At least one EXP should come back from the local scan
    assert len(result["exps"]) >= 1
    assert result["exps"][0]["exp_id"] == "EXP-1.1"
    assert result["exps"][0]["project"] == "demo-project"


# ---------------------------------------------------------------------------
# test_exp_status_markdown_table
# ---------------------------------------------------------------------------
def test_exp_status_markdown_table(tmp_path):
    """Rendered output is a valid markdown table with header row."""
    exps = [
        {
            "exp_id": "EXP-001",
            "classification": "SCIENCE",
            "status": "completed",
            "project": "gettingsciencedone",
            "last_run_id": "RUN-001",
        }
    ]

    table = render_exp_table(exps)

    assert "| EXP-" in table or "| EXP-001 |" in table, (
        "Table must contain '| EXP-' prefix in a cell"
    )
    assert "| Classification |" in table or "Classification" in table, (
        "Table must contain 'Classification' column header"
    )
    assert "EXP-001" in table
    assert "completed" in table

    # Verify it looks like a markdown table (pipe-delimited)
    lines = [line.strip() for line in table.splitlines() if line.strip()]
    assert any(line.startswith("|") for line in lines), "Table rows must start with '|'"
    assert any("---" in line for line in lines), "Table must have a separator row"

    # Empty list renders gracefully
    empty_table = render_exp_table([])
    assert "no experiments found" in empty_table.lower() or "EXP-###" in empty_table
