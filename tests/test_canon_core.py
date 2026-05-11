"""Tests for CANON-CORE governance document — GOV-02."""
import pytest


@pytest.mark.xfail(strict=False, reason="CANON-CORE document not yet created")
def test_invariant_count(sample_canon_core_text):
    """CANON-CORE must contain exactly 9 invariants."""
    from gsigmad.governance.canon_core import load_canon_core
    core = load_canon_core()
    assert len(core.invariants) == 9


@pytest.mark.xfail(strict=False, reason="CANON-CORE document not yet created")
def test_extension_declaration_format(tmp_path):
    """Project extension file must have valid 'extends: CANON-CORE vX.Y.Z' header."""
    from gsigmad.governance.canon_core import validate_extension_header
    ext_file = tmp_path / "project_canon.md"
    ext_file.write_text("extends: CANON-CORE v1.0.0\n\n## Additional Invariants\n")
    result = validate_extension_header(str(ext_file))
    assert result["valid"] is True


@pytest.mark.xfail(strict=False, reason="CANON-CORE document not yet created")
def test_override_requires_justification(tmp_path):
    """Override of a CANON-CORE invariant without justification must fail validation."""
    from gsigmad.governance.canon_core import validate_extension_header
    ext_file = tmp_path / "bad_canon.md"
    ext_file.write_text("extends: CANON-CORE v1.0.0\noverride: invariant-3\n")
    result = validate_extension_header(str(ext_file))
    assert result["valid"] is False
    assert "override-justification" in result["error"]
