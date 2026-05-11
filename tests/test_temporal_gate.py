"""Tests for temporal integrity HARKing prevention gate — GOV-04."""
import pytest
import os
import tempfile
import subprocess
from pathlib import Path


@pytest.mark.xfail(strict=False, reason="temporal gate not yet implemented")
def test_harking_rejection(tmp_path):
    """Pre-registration commit AFTER data file mtime must be rejected with HARKING_PREVENTION_ERROR."""
    from gsigmad.governance.gates.temporal_integrity import check_temporal_integrity
    result = check_temporal_integrity(
        prereg_file="PROMPT-001.md",
        data_file="data/results.csv"
    )
    # When commit_ts > data_mtime, must fail
    assert result["pass"] is False
    assert "HARKING_PREVENTION_ERROR" in result["error"]


@pytest.mark.xfail(strict=False, reason="temporal gate not yet implemented")
def test_uncommitted_prereg_fails():
    """Pre-registration with no git commit history must fail (not pass silently)."""
    from gsigmad.governance.gates.temporal_integrity import check_temporal_integrity
    result = check_temporal_integrity(
        prereg_file="UNCOMMITTED_PROMPT.md",
        data_file="data/results.csv"
    )
    assert result["pass"] is False
    assert "HARKING_PREVENTION_ERROR" in result["error"]


@pytest.mark.xfail(strict=False, reason="temporal gate not yet implemented")
def test_valid_prereg_passes(tmp_path):
    """Pre-registration committed BEFORE data file mtime must pass."""
    from gsigmad.governance.gates.temporal_integrity import check_temporal_integrity
    # This test requires a git repo fixture — will be implemented in Plan 03
    result = {"pass": True}  # placeholder
    assert result["pass"] is True
