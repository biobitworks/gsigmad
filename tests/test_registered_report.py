"""
Tests for governance.reports.registered_report and governance.reports.amendment.

Covers REG-01 (lock, is_locked, immutability, double-lock) and
REG-02 (amendment validation, file creation, counter increment).

RED phase — all tests MUST fail until governance/reports/ is implemented.
"""
import json
import pytest
from pathlib import Path

from gsigmad.governance.reports.registered_report import lock_report, is_locked, check_immutability
from gsigmad.governance.reports.amendment import create_amendment, validate_amendment


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pre_reg_file(tmp_path: Path) -> str:
    """Create a minimal pre-registration markdown file. Returns relative path string."""
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    pre_reg = prompt_dir / "PROMPT_001.md"
    pre_reg.write_text("# Pre-reg\nHypothesis: Effect is non-zero.\nalpha: 0.05\nmesi: 0.4\ntest: ttest_ind\n")
    return "prompts/PROMPT_001.md"


def _lock_fresh(tmp_path: Path, exp_id: str = "EXP-001") -> dict:
    """Lock a freshly created EXP and return the lock result."""
    pre_reg_file = _make_pre_reg_file(tmp_path)
    return lock_report(
        exp_id=exp_id,
        pre_reg_file=pre_reg_file,
        locked_by="SIG-20260101T000000Z-test-ab12",
        gsd_root=str(tmp_path),
    )


# ---------------------------------------------------------------------------
# REG-01: Lock and immutability tests
# ---------------------------------------------------------------------------

class TestLockReport:

    def test_lock_creates_record(self, tmp_path):
        """lock_report() creates .agent/registered_reports.json with required keys."""
        result = _lock_fresh(tmp_path)
        assert result["pass"] is True

        reports_file = tmp_path / ".agent" / "registered_reports.json"
        assert reports_file.exists(), "registered_reports.json was not created"

        data = json.loads(reports_file.read_text())
        assert "EXP-001" in data, "EXP-001 key missing from registered_reports.json"

        record = data["EXP-001"]
        for key in ("commit_sha", "file_hash", "locked_at", "locked_by", "pre_reg_file"):
            assert key in record, f"Expected key '{key}' missing from lock record"

    def test_is_locked_after_lock(self, tmp_path):
        """is_locked(exp_id) returns True after lock_report() succeeds."""
        _lock_fresh(tmp_path)
        assert is_locked("EXP-001", gsd_root=str(tmp_path)) is True

    def test_is_locked_before_lock(self, tmp_path):
        """is_locked(exp_id) returns False when no lock record exists."""
        assert is_locked("EXP-001", gsd_root=str(tmp_path)) is False

    def test_immutability_passes_clean(self, tmp_path):
        """check_immutability() returns {"pass": True} when file is unmodified."""
        _lock_fresh(tmp_path)
        result = check_immutability("EXP-001", gsd_root=str(tmp_path))
        assert result["pass"] is True
        assert result.get("error") is None

    def test_immutability_detects_modification(self, tmp_path):
        """check_immutability() returns {"pass": False} and REGISTERED_REPORT_IMMUTABLE after file changed."""
        _lock_fresh(tmp_path)
        # Modify the pre-registration file after locking
        pre_reg_path = tmp_path / "prompts" / "PROMPT_001.md"
        pre_reg_path.write_bytes(pre_reg_path.read_bytes() + b"\n# Appended after lock\n")

        result = check_immutability("EXP-001", gsd_root=str(tmp_path))
        assert result["pass"] is False
        assert "REGISTERED_REPORT_IMMUTABLE" in result.get("error", ""), (
            f"Expected 'REGISTERED_REPORT_IMMUTABLE' in error, got: {result.get('error')}"
        )

    def test_double_lock_rejected(self, tmp_path):
        """Second lock_report() on same EXP returns {"pass": False} with REGISTERED_REPORT_ALREADY_LOCKED."""
        _lock_fresh(tmp_path)
        # Attempt to lock the same EXP again
        pre_reg_file = _make_pre_reg_file(tmp_path)
        result = lock_report(
            exp_id="EXP-001",
            pre_reg_file=pre_reg_file,
            locked_by="SIG-20260101T000001Z-test-cd34",
            gsd_root=str(tmp_path),
        )
        assert result["pass"] is False
        assert "REGISTERED_REPORT_ALREADY_LOCKED" in result.get("error", ""), (
            f"Expected 'REGISTERED_REPORT_ALREADY_LOCKED' in error, got: {result.get('error')}"
        )


# ---------------------------------------------------------------------------
# REG-02: Amendment validation tests
# ---------------------------------------------------------------------------

class TestValidateAmendment:

    def _valid_amendment(self) -> dict:
        """Return a complete, valid amendment dict."""
        return {
            "exp_id": "EXP-001",
            "justification": "New calibration data invalidates original alpha assumption.",
            "pi_countersignature": "SIG-20260102T000000Z-pi-ef56",
            "changed_fields": ["hypothesis.alpha"],
            "original_values": {"hypothesis.alpha": 0.05},
            "new_values": {"hypothesis.alpha": 0.01},
        }

    def test_amendment_short_justification(self, tmp_path):
        """validate_amendment() returns {"pass": False} when justification < 20 chars."""
        _lock_fresh(tmp_path)
        amendment = self._valid_amendment()
        amendment["justification"] = "Too short"
        result = validate_amendment(amendment, gsd_root=str(tmp_path))
        assert result["pass"] is False
        assert result.get("error") is not None

    def test_amendment_missing_countersig(self, tmp_path):
        """validate_amendment() returns {"pass": False} when pi_countersignature is empty."""
        _lock_fresh(tmp_path)
        amendment = self._valid_amendment()
        amendment["pi_countersignature"] = ""
        result = validate_amendment(amendment, gsd_root=str(tmp_path))
        assert result["pass"] is False

        amendment2 = self._valid_amendment()
        amendment2["pi_countersignature"] = None
        result2 = validate_amendment(amendment2, gsd_root=str(tmp_path))
        assert result2["pass"] is False

    def test_amendment_missing_changed_fields(self, tmp_path):
        """validate_amendment() returns {"pass": False} when changed_fields is empty list."""
        _lock_fresh(tmp_path)
        amendment = self._valid_amendment()
        amendment["changed_fields"] = []
        result = validate_amendment(amendment, gsd_root=str(tmp_path))
        assert result["pass"] is False

    def test_amendment_values_mismatch(self, tmp_path):
        """validate_amendment() returns {"pass": False} when changed_fields keys don't match original/new values keys."""
        _lock_fresh(tmp_path)
        amendment = self._valid_amendment()
        # changed_fields says hypothesis.alpha but values reference hypothesis.mesi
        amendment["original_values"] = {"hypothesis.mesi": 0.4}
        amendment["new_values"] = {"hypothesis.mesi": 0.3}
        result = validate_amendment(amendment, gsd_root=str(tmp_path))
        assert result["pass"] is False

    def test_amendment_valid_passes(self, tmp_path):
        """validate_amendment() returns {"pass": True} with complete, valid amendment dict."""
        _lock_fresh(tmp_path)
        amendment = self._valid_amendment()
        result = validate_amendment(amendment, gsd_root=str(tmp_path))
        assert result["pass"] is True


# ---------------------------------------------------------------------------
# REG-02: Amendment file creation tests
# ---------------------------------------------------------------------------

class TestCreateAmendment:

    def _valid_amendment(self) -> dict:
        return {
            "exp_id": "EXP-001",
            "justification": "New calibration data invalidates original alpha assumption.",
            "pi_countersignature": "SIG-20260102T000000Z-pi-ef56",
            "changed_fields": ["hypothesis.alpha"],
            "original_values": {"hypothesis.alpha": 0.05},
            "new_values": {"hypothesis.alpha": 0.01},
        }

    def test_amendment_file_created(self, tmp_path):
        """create_amendment() writes .agent/amendments/EXP-001-1.json with correct schema keys."""
        _lock_fresh(tmp_path)
        amendment = self._valid_amendment()
        result = create_amendment(amendment, gsd_root=str(tmp_path))
        assert result["pass"] is True

        amendment_file = tmp_path / ".agent" / "amendments" / "EXP-001-1.json"
        assert amendment_file.exists(), f"Expected {amendment_file} to be created"

        data = json.loads(amendment_file.read_text())
        for key in ("exp_id", "justification", "pi_countersignature", "changed_fields",
                    "original_values", "new_values", "created_at"):
            assert key in data, f"Expected key '{key}' missing from amendment file"

    def test_amendment_counter_increments(self, tmp_path):
        """Second create_amendment() writes EXP-001-2.json (counter from glob count)."""
        _lock_fresh(tmp_path)
        amendment = self._valid_amendment()

        result1 = create_amendment(amendment, gsd_root=str(tmp_path))
        assert result1["pass"] is True

        result2 = create_amendment(amendment, gsd_root=str(tmp_path))
        assert result2["pass"] is True

        amendment_file_2 = tmp_path / ".agent" / "amendments" / "EXP-001-2.json"
        assert amendment_file_2.exists(), f"Expected {amendment_file_2} to be created on second call"
