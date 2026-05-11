"""
Tests for governance.versioning.exp_diff — EXP-03 experiment versioning.

Decision refs:
  D-04: Re-run produces version-suffixed EXP (EXP-042.1, EXP-042.2, etc.)
  D-05: Structured diff output comparing two EXP records
  D-06: Diff includes changed inputs, changed parameters, changed governance
"""
import json
import pytest
from pathlib import Path

from gsigmad.governance.versioning.exp_diff import diff_exp_records, next_version_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pair(base_id: str = "EXP-042", version: int = 1):
    """
    Return (original, rerun) with minimal EXP record structure.
    original has exp_id=base_id; rerun has exp_id=f"{base_id}.{version}".
    """
    original = {
        "exp_id": base_id,
        "classification": "CONFIRMATORY",
        "data_file": None,
        "hypothesis": {
            "h0": "Effect equals zero",
            "h1": "Effect is non-zero",
            "test": "ttest_ind",
            "alpha": 0.05,
            "mesi": 0.4,
        },
        "power_analysis": {
            "tier": "formula",
            "required_n": 100,
            "effect_size_mesi": 0.4,
            "alpha": 0.05,
            "achieved_power": 0.80,
        },
        "gates": {
            "data_contract": "PASS",
            "temporal_integrity": "PASS",
            "red_team": "PASS",
            "power_analysis": "PASS",
        },
    }
    import copy
    rerun = copy.deepcopy(original)
    rerun["exp_id"] = f"{base_id}.{version}"
    return original, rerun


# ---------------------------------------------------------------------------
# Section 1: diff_exp_records tests
# ---------------------------------------------------------------------------

class TestDiffExpRecords:

    def test_identical_records(self):
        """Diffing two identical records (same content, versioned ID) returns 0 changes."""
        original, rerun = _make_pair()
        result = diff_exp_records(original, rerun)
        assert result["changed_inputs"] == []
        assert result["changed_parameters"] == []
        assert result["changed_governance"] == []
        assert result["summary"].startswith("0 field(s)")

    def test_changed_input_field(self):
        """Changing data_file field appears in changed_inputs."""
        original, rerun = _make_pair()
        original["data_file"] = "old.csv"
        rerun["data_file"] = "new.csv"
        result = diff_exp_records(original, rerun)
        assert len(result["changed_inputs"]) == 1
        entry = result["changed_inputs"][0]
        assert entry["field"] == "data_file"
        assert entry["old"] == "old.csv"
        assert entry["new"] == "new.csv"

    def test_changed_hypothesis_alpha(self):
        """Changing hypothesis.alpha appears in changed_parameters with dot notation."""
        original, rerun = _make_pair()
        rerun["hypothesis"]["alpha"] = 0.01
        result = diff_exp_records(original, rerun)
        param_fields = [e["field"] for e in result["changed_parameters"]]
        assert "hypothesis.alpha" in param_fields
        entry = next(e for e in result["changed_parameters"] if e["field"] == "hypothesis.alpha")
        assert entry["old"] == 0.05
        assert entry["new"] == 0.01

    def test_changed_classification(self):
        """Changing classification appears in changed_governance."""
        original, rerun = _make_pair()
        rerun["classification"] = "EXPLORATORY"
        result = diff_exp_records(original, rerun)
        gov_fields = [e["field"] for e in result["changed_governance"]]
        assert "classification" in gov_fields
        entry = next(e for e in result["changed_governance"] if e["field"] == "classification")
        assert entry["old"] == "CONFIRMATORY"
        assert entry["new"] == "EXPLORATORY"

    def test_mismatched_ids_raises(self):
        """diff_exp_records(EXP-001, EXP-002.1) raises ValueError with 'must start with'."""
        original = {"exp_id": "EXP-001", "classification": "CONFIRMATORY",
                    "hypothesis": {}, "gates": {}, "data_file": None}
        rerun = {"exp_id": "EXP-002.1", "classification": "CONFIRMATORY",
                 "hypothesis": {}, "gates": {}, "data_file": None}
        with pytest.raises(ValueError, match="must start with"):
            diff_exp_records(original, rerun)

    def test_markdown_diff_header(self):
        """markdown_diff contains the expected ## header line."""
        original, rerun = _make_pair(base_id="EXP-042", version=1)
        result = diff_exp_records(original, rerun)
        assert "## EXP-042 \u2192 EXP-042.1 Diff" in result["markdown_diff"]

    def test_pass_always_true(self):
        """pass is True even when there are changes — diff is informational."""
        original, rerun = _make_pair()
        original["data_file"] = "old.csv"
        rerun["data_file"] = "new.csv"
        result = diff_exp_records(original, rerun)
        assert result["pass"] is True

    def test_return_keys_complete(self):
        """Return dict has all 8 required keys."""
        original, rerun = _make_pair()
        result = diff_exp_records(original, rerun)
        required_keys = {
            "pass", "original_id", "rerun_id",
            "changed_inputs", "changed_parameters", "changed_governance",
            "summary", "markdown_diff",
        }
        assert required_keys.issubset(result.keys())

    def test_original_and_rerun_ids_set(self):
        """original_id and rerun_id carry the correct exp IDs."""
        original, rerun = _make_pair(base_id="EXP-042", version=1)
        result = diff_exp_records(original, rerun)
        assert result["original_id"] == "EXP-042"
        assert result["rerun_id"] == "EXP-042.1"

    def test_no_changes_markdown_note(self):
        """When no changes, markdown_diff contains '(no changes)' marker."""
        original, rerun = _make_pair()
        result = diff_exp_records(original, rerun)
        assert "no changes" in result["markdown_diff"].lower()


# ---------------------------------------------------------------------------
# Section 2: next_version_id tests
# ---------------------------------------------------------------------------

class TestNextVersionId:

    def test_next_version_id_first_call(self, tmp_path):
        """First call returns 'EXP-042.1' and creates exp_versions.json."""
        result = next_version_id("EXP-042", str(tmp_path))
        assert result == "EXP-042.1"
        versions_file = tmp_path / ".agent" / "exp_versions.json"
        assert versions_file.exists()

    def test_next_version_id_second_call(self, tmp_path):
        """Second call for same base returns 'EXP-042.2'."""
        next_version_id("EXP-042", str(tmp_path))
        result = next_version_id("EXP-042", str(tmp_path))
        assert result == "EXP-042.2"

    def test_next_version_id_different_bases(self, tmp_path):
        """Different base EXP IDs maintain independent counters."""
        r1 = next_version_id("EXP-001", str(tmp_path))
        r2 = next_version_id("EXP-002", str(tmp_path))
        assert r1 == "EXP-001.1"
        assert r2 == "EXP-002.1"

    def test_next_version_id_creates_agent_dir(self, tmp_path):
        """The .agent/ directory is created if it does not exist."""
        agent_dir = tmp_path / ".agent"
        assert not agent_dir.exists()
        next_version_id("EXP-042", str(tmp_path))
        assert agent_dir.exists()

    def test_next_version_id_persists_across_calls(self, tmp_path):
        """Counter is persisted in the JSON file between calls."""
        next_version_id("EXP-042", str(tmp_path))
        next_version_id("EXP-042", str(tmp_path))
        versions_file = tmp_path / ".agent" / "exp_versions.json"
        data = json.loads(versions_file.read_text())
        assert data["EXP-042"] == 2

    def test_next_version_id_different_bases_independent(self, tmp_path):
        """Calling for EXP-001 and EXP-002 each once gives independent .1 versions."""
        v1 = next_version_id("EXP-001", str(tmp_path))
        v2 = next_version_id("EXP-002", str(tmp_path))
        # Call EXP-001 again — should be .2 not .3
        v1b = next_version_id("EXP-001", str(tmp_path))
        assert v1 == "EXP-001.1"
        assert v2 == "EXP-002.1"
        assert v1b == "EXP-001.2"
