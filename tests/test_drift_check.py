"""
Tests for governance.compiler.drift_check — GOV-01 drift detection.

Decision refs: D-09 (counter at .agent/drift_counter.txt, trigger at 5),
               D-10 (SCIENCE < 50% → DRIFT_WARNING halt),
               D-11 (MISSION_ANCHOR re-read on triggered analysis).
"""
import os
import pytest
from pathlib import Path

from gsigmad.governance.compiler.drift_check import check_drift


def _write_lab_notebook(tmp_path: Path, exp_lines: list[str]) -> None:
    """Write a minimal LAB_NOTEBOOK.md with given EXP header lines."""
    content = "# Lab Notebook\n\n"
    for line in exp_lines:
        content += f"{line}\n\nSome content here.\n\n"
    (tmp_path / "LAB_NOTEBOOK.md").write_text(content)


def test_drift_counter_increments(tmp_path):
    """check_drift increments counter from 0 to 1 on first call."""
    result = check_drift(str(tmp_path))
    assert result["pass"] is True
    assert result["triggered"] is False
    assert result["counter"] == 1

    counter_file = tmp_path / ".agent" / "drift_counter.txt"
    assert counter_file.exists()
    assert counter_file.read_text().strip() == "1"


def test_drift_trigger(tmp_path):
    """Calling check_drift 5 times triggers analysis on the 5th call; counter resets to 0."""
    # Write 5 EXP entries: 3 SCIENCE, 1 INFRASTRUCTURE, 1 VISUALIZATION
    _write_lab_notebook(tmp_path, [
        "## EXP-001 — SCIENCE — Baseline measurement",
        "## EXP-002 — CONFIRMATORY — Test hypothesis A",
        "## EXP-003 — INFRASTRUCTURE — Set up pipeline",
        "## EXP-004 — VISUALIZATION — Plot results",
        "## EXP-005 — EXPLORATORY — Explore parameter space",
    ])

    results = [check_drift(str(tmp_path)) for _ in range(5)]

    # Calls 1–4 must not trigger
    for i, r in enumerate(results[:4]):
        assert r["triggered"] is False, f"Call {i+1} should not trigger"

    # 5th call must trigger
    r5 = results[4]
    assert r5["triggered"] is True, "5th call must trigger drift analysis"

    # Counter must reset to 0
    counter_file = tmp_path / ".agent" / "drift_counter.txt"
    assert counter_file.read_text().strip() == "0"


def test_drift_warning_below_50pct(tmp_path):
    """pass=False with DRIFT_WARNING when only 1/5 EXPs are SCIENCE (20%)."""
    _write_lab_notebook(tmp_path, [
        "## EXP-001 — SCIENCE — One science entry",
        "## EXP-002 — INFRASTRUCTURE — Setup",
        "## EXP-003 — INFRASTRUCTURE — More setup",
        "## EXP-004 — INFRASTRUCTURE — Even more setup",
        "## EXP-005 — INFRASTRUCTURE — Still more setup",
    ])

    # Pre-set counter to 4 so next call triggers
    agent_dir = tmp_path / ".agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "drift_counter.txt").write_text("4")

    result = check_drift(str(tmp_path))

    assert result["pass"] is False
    assert result["triggered"] is True
    assert result["error"].startswith("DRIFT_WARNING: SCIENCE classification at")
    assert "below 50% threshold" in result["error"]
    assert result["science_pct"] == pytest.approx(20.0, abs=1.0)


def test_drift_pass_above_50pct(tmp_path):
    """pass=True when all 5 EXPs are SCIENCE (100%)."""
    _write_lab_notebook(tmp_path, [
        "## EXP-001 — SCIENCE — Measurement A",
        "## EXP-002 — CONFIRMATORY — Confirmation B",
        "## EXP-003 — EXPLORATORY — Exploration C",
        "## EXP-004 — REPLICATION — Replication D",
        "## EXP-005 — SCIENCE — Measurement E",
    ])

    agent_dir = tmp_path / ".agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "drift_counter.txt").write_text("4")

    result = check_drift(str(tmp_path))

    assert result["pass"] is True
    assert result["triggered"] is True
    assert result["science_pct"] == pytest.approx(100.0, abs=1.0)


def test_no_trigger_before_5(tmp_path):
    """All 4 calls before the 5th must return triggered=False."""
    results = [check_drift(str(tmp_path)) for _ in range(4)]
    for i, r in enumerate(results):
        assert r["triggered"] is False, f"Call {i+1} should not trigger (triggered=False expected)"
        assert r["pass"] is True
