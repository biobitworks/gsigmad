"""Calibration contract tests for CAL-01 and REP-02.

Tests CalibrationDeclaration model validation, ContractField extension,
validate_calibration() gate logic, TRAITS_PILLARS update, and template
integration.
"""
import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# CalibrationDeclaration schema tests
# ---------------------------------------------------------------------------


def test_calibration_schema_valid():
    """CalibrationDeclaration validates a complete valid declaration without error."""
    from gsigmad.governance.gates.data_contract import CalibrationDeclaration

    decl = CalibrationDeclaration(
        calibrated=True,
        method="platt_scaling",
        tool="scikit-learn",
        tool_version="1.5.0",
        calibration_n=500,
        brier_score=0.12,
        ece_score=0.04,
        procedure_ref="calibration/platt_procedure.md",
    )
    assert decl.calibrated is True
    assert decl.method == "platt_scaling"
    assert decl.brier_score == 0.12


def test_calibration_schema_rejects_brier_above_one():
    """CalibrationDeclaration rejects brier_score > 1.0."""
    from gsigmad.governance.gates.data_contract import CalibrationDeclaration

    with pytest.raises(ValidationError):
        CalibrationDeclaration(calibrated=True, method="platt_scaling", brier_score=1.5)


def test_calibration_schema_rejects_brier_below_zero():
    """CalibrationDeclaration rejects brier_score < 0.0."""
    from gsigmad.governance.gates.data_contract import CalibrationDeclaration

    with pytest.raises(ValidationError):
        CalibrationDeclaration(calibrated=True, method="platt_scaling", brier_score=-0.1)


def test_calibration_schema_rejects_invalid_method():
    """CalibrationDeclaration rejects invalid method literal (e.g., 'magic')."""
    from gsigmad.governance.gates.data_contract import CalibrationDeclaration

    with pytest.raises(ValidationError):
        CalibrationDeclaration(calibrated=True, method="magic")


# ---------------------------------------------------------------------------
# ContractField backward compatibility tests
# ---------------------------------------------------------------------------


def test_contract_field_without_calibration():
    """ContractField with calibration=None validates normally (backward compat)."""
    from gsigmad.governance.gates.data_contract import ContractField

    field = ContractField(name="score", type="float")
    assert field.calibration is None


def test_contract_field_with_calibration():
    """ContractField with calibration sub-block validates successfully."""
    from gsigmad.governance.gates.data_contract import (
        CalibrationDeclaration,
        ContractField,
    )

    cal = CalibrationDeclaration(
        calibrated=True,
        method="platt_scaling",
        tool="scikit-learn",
    )
    field = ContractField(name="score", type="float", calibration=cal)
    assert field.calibration is not None
    assert field.calibration.method == "platt_scaling"


# ---------------------------------------------------------------------------
# validate_calibration() logic tests
# ---------------------------------------------------------------------------


def test_validate_calibration_no_block():
    """validate_calibration() returns empty violations for field with no calibration block."""
    from gsigmad.governance.gates.data_contract import validate_calibration

    result = validate_calibration({"name": "score", "type": "float"})
    assert result == []


def test_validate_calibration_not_calibrated():
    """validate_calibration() returns empty violations for calibrated=False (advisory only)."""
    from gsigmad.governance.gates.data_contract import validate_calibration

    result = validate_calibration({
        "name": "score",
        "type": "float",
        "calibration": {"calibrated": False},
    })
    assert result == []


def test_validate_calibration_method_missing_none():
    """validate_calibration() returns CALIBRATION_METHOD_MISSING for calibrated=True with method=None."""
    from gsigmad.governance.gates.data_contract import validate_calibration

    result = validate_calibration({
        "name": "score",
        "type": "float",
        "calibration": {"calibrated": True, "method": None},
    })
    assert any("CALIBRATION_METHOD_MISSING" in v for v in result)


def test_validate_calibration_method_missing_none_str():
    """validate_calibration() returns CALIBRATION_METHOD_MISSING for calibrated=True with method='none'."""
    from gsigmad.governance.gates.data_contract import validate_calibration

    result = validate_calibration({
        "name": "score",
        "type": "float",
        "calibration": {"calibrated": True, "method": "none"},
    })
    assert any("CALIBRATION_METHOD_MISSING" in v for v in result)


def test_validate_calibration_evidence_insufficient():
    """validate_calibration() returns CALIBRATION_EVIDENCE_INSUFFICIENT for method but no evidence."""
    from gsigmad.governance.gates.data_contract import validate_calibration

    result = validate_calibration({
        "name": "score",
        "type": "float",
        "calibration": {"calibrated": True, "method": "platt_scaling"},
    })
    assert any("CALIBRATION_EVIDENCE_INSUFFICIENT" in v for v in result)


def test_validate_calibration_passes_with_tool():
    """validate_calibration() passes for calibrated=True with method and tool (tool counts as evidence)."""
    from gsigmad.governance.gates.data_contract import validate_calibration

    result = validate_calibration({
        "name": "score",
        "type": "float",
        "calibration": {
            "calibrated": True,
            "method": "platt_scaling",
            "tool": "scikit-learn",
        },
    })
    assert result == []


def test_validate_calibration_passes_with_metric():
    """validate_calibration() passes for calibrated=True with method and brier_score (metric counts)."""
    from gsigmad.governance.gates.data_contract import validate_calibration

    result = validate_calibration({
        "name": "score",
        "type": "float",
        "calibration": {
            "calibrated": True,
            "method": "isotonic_regression",
            "brier_score": 0.15,
        },
    })
    assert result == []


def test_validate_calibration_passes_with_procedure_ref():
    """validate_calibration() passes for calibrated=True with method and procedure_ref (ref counts)."""
    from gsigmad.governance.gates.data_contract import validate_calibration

    result = validate_calibration({
        "name": "score",
        "type": "float",
        "calibration": {
            "calibrated": True,
            "method": "beta_calibration",
            "procedure_ref": "calibration/proc.md",
        },
    })
    assert result == []


# ---------------------------------------------------------------------------
# TRAITS_PILLARS tests
# ---------------------------------------------------------------------------


def test_calibration_traits_pillars():
    """TRAITS_PILLARS in data_contract includes 'calibration': ['Accurate', 'Interpretable']."""
    from gsigmad.governance.gates.data_contract import TRAITS_PILLARS

    assert "calibration" in TRAITS_PILLARS
    assert TRAITS_PILLARS["calibration"] == ["Accurate", "Interpretable"]


_VALID_PILLARS = {"Traceable", "Rigorous", "Accurate", "Interpretable", "Transparent", "Secure"}


def test_all_traits_pillars_consistent_with_calibration():
    """Importing TRAITS_PILLARS from all gate modules produces exactly 8 entries with valid pillars."""
    from gsigmad.governance.gates.fdr_contract import TRAITS_PILLARS as fdr_tp
    from gsigmad.governance.gates.power_analysis import TRAITS_PILLARS as pa_tp
    from gsigmad.governance.gates.data_contract import TRAITS_PILLARS as dc_tp
    from gsigmad.governance.gates.temporal_integrity import TRAITS_PILLARS as ti_tp
    from gsigmad.governance.gates.red_team import TRAITS_PILLARS as rt_tp
    from gsigmad.governance.gates.audit_claims import TRAITS_PILLARS as ac_tp
    from gsigmad.governance.gates.null_model import TRAITS_PILLARS as nm_tp

    combined = {}
    for tp in [fdr_tp, pa_tp, dc_tp, ti_tp, rt_tp, ac_tp, nm_tp]:
        assert isinstance(tp, dict)
        combined.update(tp)

    # 8 unique gate names (7 original + calibration in data_contract module)
    assert len(combined) == 8, f"Expected 8 gates, got {len(combined)}: {list(combined.keys())}"

    for gate_name, pillars in combined.items():
        assert isinstance(pillars, list), f"{gate_name} pillars is not a list"
        for p in pillars:
            assert p in _VALID_PILLARS, f"{gate_name} has invalid pillar '{p}'"


def test_traits_coverage_matrix_includes_calibration():
    """traits_coverage_matrix discovers calibration Accurate and Interpretable pillars from data_contract module."""
    from gsigmad.governance.gates.fdr_contract import traits_coverage_matrix
    from gsigmad.commands.run import GATE_CHAIN

    result = traits_coverage_matrix(GATE_CHAIN)
    # data_contract module contributes calibration -> Accurate and Interpretable
    assert "Accurate" in result["covered"]
    assert "data_contract" in result["covered"]["Accurate"]
    assert "Interpretable" in result["covered"]
    assert "data_contract" in result["covered"]["Interpretable"]


# ---------------------------------------------------------------------------
# Template integration tests
# ---------------------------------------------------------------------------


def test_confirmatory_template_includes_calibration_contract():
    """exp_template('EXP-1.1', 'CONFIRMATORY') includes calibration_contract key."""
    from gsigmad.scaffold.templates import exp_template

    record = exp_template("EXP-1.1", "CONFIRMATORY")
    assert "calibration_contract" in record
    assert "scored_fields" in record["calibration_contract"]
    assert "default_calibration" in record["calibration_contract"]


def test_exploratory_template_excludes_calibration_contract():
    """exp_template('EXP-1.1', 'EXPLORATORY') does NOT include calibration_contract key."""
    from gsigmad.scaffold.templates import exp_template

    record = exp_template("EXP-1.1", "EXPLORATORY")
    assert "calibration_contract" not in record


# ---------------------------------------------------------------------------
# Pre-v1.7 backward compatibility test
# ---------------------------------------------------------------------------


def test_calibration_skip_pre_v17():
    """Pre-v1.7 records without calibration field produce no errors (SKIP behavior)."""
    from gsigmad.governance.gates.data_contract import validate_calibration

    # A pre-v1.7 field dict has no "calibration" key at all
    old_field = {"name": "pvalue", "type": "float", "required": True}
    result = validate_calibration(old_field)
    assert result == []


# ---------------------------------------------------------------------------
# Fixture integration tests
# ---------------------------------------------------------------------------


def test_sample_calibration_declaration_fixture(sample_calibration_declaration):
    """Fixture provides a valid CalibrationDeclaration dict."""
    from gsigmad.governance.gates.data_contract import CalibrationDeclaration

    decl = CalibrationDeclaration(**sample_calibration_declaration)
    assert decl.calibrated is True
    assert decl.method == "platt_scaling"


def test_sample_exp_with_calibration_fixture(sample_exp_with_calibration):
    """Fixture provides an EXP with a calibration sub-block on a data_contract field."""
    assert "data_contract" in sample_exp_with_calibration
    fields = sample_exp_with_calibration["data_contract"]["fields"]
    scored_field = next(f for f in fields if f["name"] == "confidence_score")
    assert "calibration" in scored_field
    assert scored_field["calibration"]["calibrated"] is True


# ---------------------------------------------------------------------------
# CAL-02: Calibration evidence enforcement (check_calibration_evidence)
# ---------------------------------------------------------------------------


def test_calibration_evidence_no_scored_fields():
    """check_calibration_evidence() returns pass=True for claim with no scored_fields key (backward compat)."""
    from gsigmad.governance.gates.audit_claims import check_calibration_evidence

    result = check_calibration_evidence({"text": "Some claim"})
    assert result["pass"] is True
    assert result["error"] is None
    assert result["advisory"] is None


def test_calibration_evidence_empty_scored_fields():
    """check_calibration_evidence() returns pass=True for claim with empty scored_fields list."""
    from gsigmad.governance.gates.audit_claims import check_calibration_evidence

    result = check_calibration_evidence({"text": "Some claim", "scored_fields": []})
    assert result["pass"] is True
    assert result["error"] is None
    assert result["advisory"] is None


def test_calibration_evidence_rejected_no_method():
    """check_calibration_evidence() returns pass=False with CALIBRATION_EVIDENCE_REJECTED for calibrated=True but method=None."""
    from gsigmad.governance.gates.audit_claims import check_calibration_evidence

    claim = {
        "text": "Model predicts with high confidence",
        "scored_fields": [
            {"name": "confidence", "calibration": {"calibrated": True, "method": None}}
        ],
    }
    result = check_calibration_evidence(claim)
    assert result["pass"] is False
    assert "CALIBRATION_EVIDENCE_REJECTED" in result["error"]


def test_calibration_evidence_rejected_method_but_no_evidence():
    """check_calibration_evidence() returns pass=False for calibrated=True, method='platt_scaling' but no tool, no metric, no procedure_ref."""
    from gsigmad.governance.gates.audit_claims import check_calibration_evidence

    claim = {
        "text": "Model predicts with high confidence",
        "scored_fields": [
            {"name": "confidence", "calibration": {"calibrated": True, "method": "platt_scaling"}}
        ],
    }
    result = check_calibration_evidence(claim)
    assert result["pass"] is False
    assert "CALIBRATION_EVIDENCE_REJECTED" in result["error"]


def test_calibration_evidence_pass_with_tool():
    """check_calibration_evidence() returns pass=True for calibrated=True, method='platt_scaling', tool='scikit-learn'."""
    from gsigmad.governance.gates.audit_claims import check_calibration_evidence

    claim = {
        "text": "Model predicts with high confidence",
        "scored_fields": [
            {"name": "confidence", "calibration": {
                "calibrated": True, "method": "platt_scaling", "tool": "scikit-learn"
            }}
        ],
    }
    result = check_calibration_evidence(claim)
    assert result["pass"] is True


def test_calibration_evidence_pass_with_metric():
    """check_calibration_evidence() returns pass=True for calibrated=True, method='isotonic_regression', brier_score=0.15."""
    from gsigmad.governance.gates.audit_claims import check_calibration_evidence

    claim = {
        "text": "Model predicts with high confidence",
        "scored_fields": [
            {"name": "confidence", "calibration": {
                "calibrated": True, "method": "isotonic_regression", "brier_score": 0.15
            }}
        ],
    }
    result = check_calibration_evidence(claim)
    assert result["pass"] is True


def test_calibration_evidence_pass_with_procedure_ref():
    """check_calibration_evidence() returns pass=True for calibrated=True, method='beta_calibration', procedure_ref='calibration/proc.md'."""
    from gsigmad.governance.gates.audit_claims import check_calibration_evidence

    claim = {
        "text": "Model predicts with high confidence",
        "scored_fields": [
            {"name": "confidence", "calibration": {
                "calibrated": True, "method": "beta_calibration",
                "procedure_ref": "calibration/proc.md"
            }}
        ],
    }
    result = check_calibration_evidence(claim)
    assert result["pass"] is True


# ---------------------------------------------------------------------------
# CAL-03: CALIBRATION_ADVISORY warnings
# ---------------------------------------------------------------------------


def test_calibration_advisory_uncalibrated():
    """check_calibration_evidence() returns advisory containing 'CALIBRATION_ADVISORY' for scored field with calibrated=False."""
    from gsigmad.governance.gates.audit_claims import check_calibration_evidence

    claim = {
        "text": "Model predicts with high confidence",
        "scored_fields": [
            {"name": "confidence", "calibration": {"calibrated": False}}
        ],
    }
    result = check_calibration_evidence(claim)
    assert result["pass"] is True  # Advisory, not failure
    assert "CALIBRATION_ADVISORY" in result["advisory"]


def test_calibration_advisory_no_calibration_block():
    """check_calibration_evidence() returns advisory containing 'CALIBRATION_ADVISORY' for scored field with no calibration block (None)."""
    from gsigmad.governance.gates.audit_claims import check_calibration_evidence

    claim = {
        "text": "Model predicts with high confidence",
        "scored_fields": [
            {"name": "confidence", "calibration": None}
        ],
    }
    result = check_calibration_evidence(claim)
    assert result["pass"] is True  # Advisory, not failure
    assert "CALIBRATION_ADVISORY" in result["advisory"]


# ---------------------------------------------------------------------------
# CAL-02/CAL-03: audit_claims_gate integration
# ---------------------------------------------------------------------------


def test_audit_claims_gate_calibration_advisory():
    """audit_claims_gate with claim containing scored_fields with calibrated=False produces warning containing CALIBRATION_ADVISORY."""
    from gsigmad.governance.gates.audit_claims import audit_claims_gate

    claims = [{
        "text": "Model predicts well",
        "scored_fields": [
            {"name": "confidence", "calibration": {"calibrated": False}}
        ],
    }]
    result = audit_claims_gate(claims, verify_citations=False)
    assert result["pass"] is True  # Advisory, not failure
    assert any("CALIBRATION_ADVISORY" in w for w in result["warnings"])


def test_audit_claims_gate_calibration_evidence_rejected():
    """audit_claims_gate with claim containing scored_fields with calibrated=True but no evidence produces failure."""
    from gsigmad.governance.gates.audit_claims import audit_claims_gate

    claims = [{
        "text": "Model predicts well",
        "scored_fields": [
            {"name": "confidence", "calibration": {"calibrated": True, "method": None}}
        ],
    }]
    result = audit_claims_gate(claims, verify_citations=False)
    assert result["pass"] is False
    assert any("CALIBRATION_EVIDENCE_REJECTED" in f["error"] for f in result["failures"])


def test_audit_claims_gate_no_scored_fields_backward_compat():
    """audit_claims_gate with claim containing no scored_fields key passes (backward compat)."""
    from gsigmad.governance.gates.audit_claims import audit_claims_gate

    claims = [{"text": "Simple claim without scores"}]
    result = audit_claims_gate(claims, verify_citations=False)
    assert result["pass"] is True


# ---------------------------------------------------------------------------
# REP-03: RT challenge_target for calibration
# ---------------------------------------------------------------------------


def test_rt_challenge_target_calibration_method():
    """RT record with challenge_target='calibration.method' passes through red_team gate."""
    from gsigmad.governance.gates.red_team import check_red_team_gate

    result = check_red_team_gate(
        "CONFIRMATORY",
        {"h0": "No effect", "challenge_target": "calibration.method",
         "risk_tier": "P1", "red_team_status": "PASS",
         "remediation_constraints": ["Validate calibration method"],
         "execution_decision": "GO"},
    )
    assert result["pass"] is True


def test_rt_challenge_target_calibration_brier():
    """RT record with challenge_target='calibration.brier_score' passes through red_team gate."""
    from gsigmad.governance.gates.red_team import check_red_team_gate

    result = check_red_team_gate(
        "CONFIRMATORY",
        {"h0": "No effect", "challenge_target": "calibration.brier_score",
         "risk_tier": "P1", "red_team_status": "PASS",
         "remediation_constraints": ["Check Brier score validity"],
         "execution_decision": "GO"},
    )
    assert result["pass"] is True
