"""
Tests for governance.reports.registered_report.check_deviation.

Covers REG-04 (deviation detection between EXP record hypothesis fields and locked plan fields).

RED phase — all tests MUST fail until governance/reports/ is implemented.
"""
import json
import pytest
from pathlib import Path

from gsigmad.governance.reports.registered_report import check_deviation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LOCKED_PLAN = {
    "hypothesis.test": "ttest_ind",
    "hypothesis.alpha": 0.05,
    "hypothesis.mesi": 0.4,
}

_EXP_RECORD_MATCHING = {
    "exp_id": "EXP-001",
    "hypothesis": {
        "test": "ttest_ind",
        "alpha": 0.05,
        "mesi": 0.4,
    },
}


def _write_lock_record(tmp_path: Path, exp_id: str = "EXP-001", locked_plan: dict = None) -> None:
    """Write a pre-existing lock record to registered_reports.json for deviation tests."""
    agent_dir = tmp_path / ".agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    reports_file = agent_dir / "registered_reports.json"

    lock_record = {
        exp_id: {
            "commit_sha": "abc1234",
            "file_hash": "deadbeef",
            "locked_at": "2026-01-01T00:00:00Z",
            "locked_by": "SIG-test",
            "pre_reg_file": "prompts/PROMPT_001.md",
            "locked_plan": locked_plan if locked_plan is not None else _LOCKED_PLAN,
        }
    }
    reports_file.write_text(json.dumps(lock_record, indent=2))


# ---------------------------------------------------------------------------
# REG-04: Deviation check tests
# ---------------------------------------------------------------------------

class TestCheckDeviation:

    def test_no_deviation_passes(self, tmp_path):
        """check_deviation() returns {"pass": True} when EXP hypothesis matches locked plan exactly."""
        _write_lock_record(tmp_path)
        exp_record = _EXP_RECORD_MATCHING.copy()
        result = check_deviation("EXP-001", exp_record, gsd_root=str(tmp_path))
        assert result["pass"] is True
        assert result.get("error") is None

    def test_alpha_deviation_fails(self, tmp_path):
        """check_deviation() returns {"pass": False} with REGISTERED_REPORT_DEVIATION and hypothesis.alpha when alpha differs."""
        _write_lock_record(tmp_path)
        import copy
        exp_record = copy.deepcopy(_EXP_RECORD_MATCHING)
        exp_record["hypothesis"]["alpha"] = 0.01  # deviates from locked 0.05

        result = check_deviation("EXP-001", exp_record, gsd_root=str(tmp_path))
        assert result["pass"] is False
        assert "REGISTERED_REPORT_DEVIATION" in result.get("error", ""), (
            f"Expected 'REGISTERED_REPORT_DEVIATION' in error, got: {result.get('error')}"
        )
        assert "hypothesis.alpha" in result.get("error", ""), (
            f"Expected 'hypothesis.alpha' in error, got: {result.get('error')}"
        )

    def test_test_field_deviation_fails(self, tmp_path):
        """check_deviation() returns {"pass": False} with hypothesis.test in error when test field differs."""
        _write_lock_record(tmp_path)
        import copy
        exp_record = copy.deepcopy(_EXP_RECORD_MATCHING)
        exp_record["hypothesis"]["test"] = "mannwhitneyu"  # deviates from locked ttest_ind

        result = check_deviation("EXP-001", exp_record, gsd_root=str(tmp_path))
        assert result["pass"] is False
        assert "hypothesis.test" in result.get("error", ""), (
            f"Expected 'hypothesis.test' in error, got: {result.get('error')}"
        )

    def test_unlocked_exp_skipped(self, tmp_path):
        """check_deviation() returns {"pass": True} when EXP has no lock record — no KeyError."""
        # Do NOT write any lock record for EXP-999
        exp_record = {
            "exp_id": "EXP-999",
            "hypothesis": {
                "test": "ttest_ind",
                "alpha": 0.05,
                "mesi": 0.4,
            },
        }
        result = check_deviation("EXP-999", exp_record, gsd_root=str(tmp_path))
        assert result["pass"] is True
        assert result.get("error") is None
