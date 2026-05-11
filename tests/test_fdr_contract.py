"""Tests for FDR contract gate (FDR-01, FDR-02, FDR-03).

TDD RED: Tests written first to define the required interface.
"""
import pytest


# -- FDR-01: Schema validation and backward compat --

def test_fdr_gate_skip_pre_v17(sample_exp_record):
    """EXP record with no fdr_chain key returns pass=True with skip note."""
    from gsigmad.governance.gates.fdr_contract import check_fdr_contract_gate

    assert "fdr_chain" not in sample_exp_record
    result = check_fdr_contract_gate(sample_exp_record)
    assert result["pass"] is True
    assert "skipped" in result["note"].lower() or "pre-v1.7" in result["note"].lower()


def test_fdr_gate_missing_chain_confirmatory(sample_exp_record):
    """CONFIRMATORY EXP with fdr_chain=None returns pass=True (pre-v1.7 compat)."""
    from gsigmad.governance.gates.fdr_contract import check_fdr_contract_gate

    sample_exp_record["fdr_chain"] = None
    result = check_fdr_contract_gate(sample_exp_record)
    assert result["pass"] is True
    assert "note" in result


def test_fdr_chain_schema_validation():
    """fdr_chain with missing 'levels' key returns FAIL with FDR_CHAIN_SCHEMA_INVALID."""
    from gsigmad.governance.gates.fdr_contract import check_fdr_contract_gate

    exp = {"fdr_chain": {"method": "fdr_bh", "tool": "X", "tool_version": "1"}}
    result = check_fdr_contract_gate(exp)
    assert result["pass"] is False
    assert "FDR_CHAIN_SCHEMA_INVALID" in result["error"]


def test_fdr_chain_schema_invalid_threshold():
    """fdr_chain level with threshold=1.5 (>1.0) returns FAIL with FDR_CHAIN_SCHEMA_INVALID."""
    from gsigmad.governance.gates.fdr_contract import check_fdr_contract_gate

    exp = {
        "fdr_chain": {
            "levels": [{"name": "PSM", "threshold": 1.5}],
            "method": "fdr_bh",
            "tool": "Percolator",
            "tool_version": "3.06.1",
        }
    }
    result = check_fdr_contract_gate(exp)
    assert result["pass"] is False
    assert "FDR_CHAIN_SCHEMA_INVALID" in result["error"]


def test_fdr_chain_schema_invalid_method():
    """fdr_chain with method='invalid_method' returns FAIL with FDR_INVALID_METHOD."""
    from gsigmad.governance.gates.fdr_contract import check_fdr_contract_gate

    exp = {
        "fdr_chain": {
            "levels": [{"name": "PSM", "threshold": 0.01}],
            "method": "invalid_method",
            "tool": "Percolator",
            "tool_version": "3.06.1",
        }
    }
    result = check_fdr_contract_gate(exp)
    assert result["pass"] is False
    assert "FDR_INVALID_METHOD" in result["error"]


def test_fdr_chain_valid_proteomics(sample_exp_with_fdr):
    """Valid 3-level proteomics chain (PSM 0.01, peptide 0.01, protein 0.05) passes."""
    from gsigmad.governance.gates.fdr_contract import check_fdr_contract_gate

    result = check_fdr_contract_gate(sample_exp_with_fdr)
    assert result["pass"] is True


def test_fdr_chain_valid_single_test():
    """Single level with method='none' returns pass=True."""
    from gsigmad.governance.gates.fdr_contract import check_fdr_contract_gate

    exp = {
        "fdr_chain": {
            "levels": [{"name": "primary", "threshold": 0.05}],
            "method": "none",
            "tool": "custom",
            "tool_version": "1.0",
        }
    }
    result = check_fdr_contract_gate(exp)
    assert result["pass"] is True


# -- FDR-02: Monotonicity enforcement --

def test_monotonicity_valid():
    """Levels [0.01, 0.01, 0.05] passes (equal and looser are OK)."""
    from gsigmad.governance.gates.fdr_contract import check_fdr_contract_gate

    exp = {
        "fdr_chain": {
            "levels": [
                {"name": "PSM", "threshold": 0.01},
                {"name": "peptide", "threshold": 0.01},
                {"name": "protein", "threshold": 0.05},
            ],
            "method": "fdr_bh",
            "tool": "Percolator",
            "tool_version": "3.06.1",
        }
    }
    result = check_fdr_contract_gate(exp)
    assert result["pass"] is True


def test_monotonicity_violation():
    """Levels [0.05, 0.01] returns FAIL with FDR_MONOTONICITY_VIOLATION and fix hint."""
    from gsigmad.governance.gates.fdr_contract import check_fdr_contract_gate

    exp = {
        "fdr_chain": {
            "levels": [
                {"name": "upstream", "threshold": 0.05},
                {"name": "downstream", "threshold": 0.01},
            ],
            "method": "fdr_bh",
            "tool": "Percolator",
            "tool_version": "3.06.1",
        }
    }
    result = check_fdr_contract_gate(exp)
    assert result["pass"] is False
    assert "FDR_MONOTONICITY_VIOLATION" in result["error"]
    # Fix hint should name both levels
    assert "downstream" in result["error"]
    assert "upstream" in result["error"]


def test_monotonicity_equal_thresholds():
    """Levels [0.01, 0.01] passes (equal thresholds are permitted)."""
    from gsigmad.governance.gates.fdr_contract import check_fdr_contract_gate

    exp = {
        "fdr_chain": {
            "levels": [
                {"name": "level_a", "threshold": 0.01},
                {"name": "level_b", "threshold": 0.01},
            ],
            "method": "fdr_bh",
            "tool": "Percolator",
            "tool_version": "3.06.1",
        }
    }
    result = check_fdr_contract_gate(exp)
    assert result["pass"] is True


def test_monotonicity_single_level():
    """One level always passes (nothing to compare)."""
    from gsigmad.governance.gates.fdr_contract import check_fdr_contract_gate

    exp = {
        "fdr_chain": {
            "levels": [{"name": "only", "threshold": 0.05}],
            "method": "none",
            "tool": "custom",
            "tool_version": "1.0",
        }
    }
    result = check_fdr_contract_gate(exp)
    assert result["pass"] is True


# -- TRAITS pillar declarations (D-09, D-10) --

def test_traits_pillars_declared():
    """fdr_contract module has TRAITS_PILLARS = {'fdr_contract': ['Rigorous', 'Traceable']}."""
    from gsigmad.governance.gates.fdr_contract import TRAITS_PILLARS

    assert "fdr_contract" in TRAITS_PILLARS
    assert "Rigorous" in TRAITS_PILLARS["fdr_contract"]
    assert "Traceable" in TRAITS_PILLARS["fdr_contract"]


def test_gate_returns_traits(sample_exp_with_fdr):
    """Valid fdr_chain result includes traits=['Rigorous', 'Traceable']."""
    from gsigmad.governance.gates.fdr_contract import check_fdr_contract_gate

    result = check_fdr_contract_gate(sample_exp_with_fdr)
    assert result["pass"] is True
    assert "traits" in result
    assert "Rigorous" in result["traits"]
    assert "Traceable" in result["traits"]


def test_skip_returns_traits(sample_exp_record):
    """Skip result (no fdr_chain) also includes traits key."""
    from gsigmad.governance.gates.fdr_contract import check_fdr_contract_gate

    result = check_fdr_contract_gate(sample_exp_record)
    assert result["pass"] is True
    assert "traits" in result


# -- FDR-03: Tool-version binding --

def test_tool_version_no_original(sample_exp_with_fdr):
    """fdr_chain present but no __original_fdr_chain__ key -> PASS (first registration)."""
    from gsigmad.governance.gates.fdr_contract import check_fdr_contract_gate

    assert "__original_fdr_chain__" not in sample_exp_with_fdr
    result = check_fdr_contract_gate(sample_exp_with_fdr)
    assert result["pass"] is True


def test_tool_version_match(sample_exp_with_fdr):
    """fdr_chain.tool and tool_version match __original_fdr_chain__ -> PASS."""
    from gsigmad.governance.gates.fdr_contract import check_fdr_contract_gate

    sample_exp_with_fdr["__original_fdr_chain__"] = {
        "tool": "Percolator",
        "tool_version": "3.06.1",
    }
    result = check_fdr_contract_gate(sample_exp_with_fdr)
    assert result["pass"] is True


def test_tool_version_drift_detected(sample_exp_with_fdr, tmp_path):
    """fdr_chain.tool differs from __original and no amendment -> FAIL with FDR_TOOL_VERSION_DRIFT."""
    from gsigmad.governance.gates.fdr_contract import check_fdr_contract_gate

    sample_exp_with_fdr["__original_fdr_chain__"] = {
        "tool": "OldTool",
        "tool_version": "1.0",
    }
    sample_exp_with_fdr["__project_root__"] = str(tmp_path)

    result = check_fdr_contract_gate(sample_exp_with_fdr)
    assert result["pass"] is False
    assert "FDR_TOOL_VERSION_DRIFT" in result["error"]
    assert "amendment" in result["error"].lower()


def test_tool_version_with_amendment(sample_exp_with_fdr, tmp_path):
    """fdr_chain.tool differs but amendment file exists with changed_fields -> PASS."""
    import json as _json
    from gsigmad.governance.gates.fdr_contract import check_fdr_contract_gate

    sample_exp_with_fdr["__original_fdr_chain__"] = {
        "tool": "OldTool",
        "tool_version": "1.0",
    }
    sample_exp_with_fdr["__project_root__"] = str(tmp_path)

    # Create amendment file
    amendments_dir = tmp_path / ".agent" / "amendments"
    amendments_dir.mkdir(parents=True)
    amendment = {
        "exp_id": sample_exp_with_fdr.get("exp_id", "EXP-001"),
        "changed_fields": ["fdr_chain.tool", "fdr_chain.tool_version"],
        "justification": "Upgraded tool for better accuracy",
        "pi_countersignature": "PI-SIG-001",
    }
    (amendments_dir / "EXP-001-1.json").write_text(_json.dumps(amendment))

    result = check_fdr_contract_gate(sample_exp_with_fdr)
    assert result["pass"] is True


# -- Template extension --

def test_exp_template_confirmatory_has_fdr():
    """exp_template('EXP-1', 'CONFIRMATORY') produces dict with fdr_chain key."""
    from gsigmad.scaffold.templates import exp_template

    record = exp_template("EXP-1", "CONFIRMATORY")
    assert "fdr_chain" in record
    assert "levels" in record["fdr_chain"]
    assert "method" in record["fdr_chain"]
    assert "tool" in record["fdr_chain"]
    assert "tool_version" in record["fdr_chain"]


def test_exp_template_exploratory_no_fdr():
    """exp_template('EXP-1', 'EXPLORATORY') produces dict without fdr_chain key."""
    from gsigmad.scaffold.templates import exp_template

    record = exp_template("EXP-1", "EXPLORATORY")
    assert "fdr_chain" not in record


# -- Plan 02: TRAITS pillar consistency across all gate modules --

_VALID_PILLARS = {"Traceable", "Rigorous", "Accurate", "Interpretable", "Transparent", "Secure"}


def test_power_analysis_traits():
    """power_analysis module has TRAITS_PILLARS = {'power_analysis': ['Rigorous']}."""
    from gsigmad.governance.gates.power_analysis import TRAITS_PILLARS

    assert "power_analysis" in TRAITS_PILLARS
    assert TRAITS_PILLARS["power_analysis"] == ["Rigorous"]


def test_data_contract_traits():
    """data_contract module has TRAITS_PILLARS = {'data_contract': ['Accurate', 'Traceable']}."""
    from gsigmad.governance.gates.data_contract import TRAITS_PILLARS

    assert "data_contract" in TRAITS_PILLARS
    assert TRAITS_PILLARS["data_contract"] == ["Accurate", "Traceable"]


def test_temporal_integrity_traits():
    """temporal_integrity module has TRAITS_PILLARS = {'temporal_integrity': ['Traceable']}."""
    from gsigmad.governance.gates.temporal_integrity import TRAITS_PILLARS

    assert "temporal_integrity" in TRAITS_PILLARS
    assert TRAITS_PILLARS["temporal_integrity"] == ["Traceable"]


def test_red_team_traits():
    """red_team module has TRAITS_PILLARS = {'red_team': ['Rigorous', 'Transparent']}."""
    from gsigmad.governance.gates.red_team import TRAITS_PILLARS

    assert "red_team" in TRAITS_PILLARS
    assert TRAITS_PILLARS["red_team"] == ["Rigorous", "Transparent"]


def test_audit_claims_traits():
    """audit_claims module has TRAITS_PILLARS = {'audit_claims': ['Accurate', 'Interpretable']}."""
    from gsigmad.governance.gates.audit_claims import TRAITS_PILLARS

    assert "audit_claims" in TRAITS_PILLARS
    assert TRAITS_PILLARS["audit_claims"] == ["Accurate", "Interpretable"]


def test_all_traits_pillars_consistent():
    """Importing TRAITS_PILLARS from all 6 gate modules produces exactly 6 entries with valid pillars."""
    from gsigmad.governance.gates.fdr_contract import TRAITS_PILLARS as fdr_tp
    from gsigmad.governance.gates.power_analysis import TRAITS_PILLARS as pa_tp
    from gsigmad.governance.gates.data_contract import TRAITS_PILLARS as dc_tp
    from gsigmad.governance.gates.temporal_integrity import TRAITS_PILLARS as ti_tp
    from gsigmad.governance.gates.red_team import TRAITS_PILLARS as rt_tp
    from gsigmad.governance.gates.audit_claims import TRAITS_PILLARS as ac_tp
    from gsigmad.governance.gates.null_model import TRAITS_PILLARS as nm_tp

    # Merge all into one dict
    combined = {}
    for tp in [fdr_tp, pa_tp, dc_tp, ti_tp, rt_tp, ac_tp, nm_tp]:
        assert isinstance(tp, dict)
        combined.update(tp)

    # Exactly 8 unique gate names (6 original + null_model + calibration)
    assert len(combined) == 8, f"Expected 8 gates, got {len(combined)}: {list(combined.keys())}"

    # All values are lists of valid pillar names
    for gate_name, pillars in combined.items():
        assert isinstance(pillars, list), f"{gate_name} pillars is not a list"
        for p in pillars:
            assert p in _VALID_PILLARS, f"{gate_name} has invalid pillar '{p}'"


# -- Plan 02: FDR consistency check (FDR-04) --

def test_fdr_consistency_all_match():
    """2 CONFIRMATORY experiments with identical fdr_chain -> consistent=True."""
    from gsigmad.governance.gates.fdr_contract import check_fdr_consistency

    chain = {
        "levels": [
            {"name": "PSM", "threshold": 0.01},
            {"name": "peptide", "threshold": 0.01},
        ],
        "method": "fdr_bh",
        "tool": "Percolator",
        "tool_version": "3.06.1",
    }
    exps = [
        {"exp_id": "EXP-1.1", "classification": "CONFIRMATORY", "fdr_chain": chain},
        {"exp_id": "EXP-1.2", "classification": "CONFIRMATORY", "fdr_chain": chain},
    ]
    result = check_fdr_consistency(exps)
    assert result["consistent"] is True
    assert result["inconsistencies"] == []


def test_fdr_consistency_threshold_diff():
    """2 CONFIRMATORY experiments with different peptide threshold -> consistent=False."""
    from gsigmad.governance.gates.fdr_contract import check_fdr_consistency

    chain_a = {
        "levels": [
            {"name": "PSM", "threshold": 0.01},
            {"name": "peptide", "threshold": 0.01},
        ],
        "method": "fdr_bh",
        "tool": "Percolator",
        "tool_version": "3.06.1",
    }
    chain_b = {
        "levels": [
            {"name": "PSM", "threshold": 0.01},
            {"name": "peptide", "threshold": 0.05},
        ],
        "method": "fdr_bh",
        "tool": "Percolator",
        "tool_version": "3.06.1",
    }
    exps = [
        {"exp_id": "EXP-1.1", "classification": "CONFIRMATORY", "fdr_chain": chain_a},
        {"exp_id": "EXP-1.2", "classification": "CONFIRMATORY", "fdr_chain": chain_b},
    ]
    result = check_fdr_consistency(exps)
    assert result["consistent"] is False
    assert len(result["inconsistencies"]) >= 1
    inc = result["inconsistencies"][0]
    assert "peptide" in inc["level"]


def test_fdr_consistency_different_pipeline():
    """2 CONFIRMATORY experiments with different tools -> no comparison, consistent=True."""
    from gsigmad.governance.gates.fdr_contract import check_fdr_consistency

    chain_a = {
        "levels": [{"name": "PSM", "threshold": 0.01}],
        "method": "fdr_bh",
        "tool": "Percolator",
        "tool_version": "3.06.1",
    }
    chain_b = {
        "levels": [{"name": "PSM", "threshold": 0.05}],
        "method": "fdr_bh",
        "tool": "MaxQuant",
        "tool_version": "2.0",
    }
    exps = [
        {"exp_id": "EXP-1.1", "classification": "CONFIRMATORY", "fdr_chain": chain_a},
        {"exp_id": "EXP-1.2", "classification": "CONFIRMATORY", "fdr_chain": chain_b},
    ]
    result = check_fdr_consistency(exps)
    assert result["consistent"] is True


def test_fdr_consistency_skip_exploratory():
    """EXPLORATORY experiments excluded from consistency check."""
    from gsigmad.governance.gates.fdr_contract import check_fdr_consistency

    chain = {
        "levels": [{"name": "PSM", "threshold": 0.01}],
        "method": "fdr_bh",
        "tool": "Percolator",
        "tool_version": "3.06.1",
    }
    exps = [
        {"exp_id": "EXP-1.1", "classification": "EXPLORATORY", "fdr_chain": chain},
        {"exp_id": "EXP-1.2", "classification": "EXPLORATORY", "fdr_chain": chain},
    ]
    result = check_fdr_consistency(exps)
    assert result["consistent"] is True
    assert result["pipelines_checked"] == 0


def test_fdr_consistency_skip_no_fdr():
    """CONFIRMATORY experiments without fdr_chain excluded from consistency check."""
    from gsigmad.governance.gates.fdr_contract import check_fdr_consistency

    exps = [
        {"exp_id": "EXP-1.1", "classification": "CONFIRMATORY"},
        {"exp_id": "EXP-1.2", "classification": "CONFIRMATORY"},
    ]
    result = check_fdr_consistency(exps)
    assert result["consistent"] is True
    assert result["pipelines_checked"] == 0


# -- Plan 02: TRAITS coverage matrix --

def test_traits_coverage_matrix():
    """traits_coverage_matrix produces covered dict and uncovered list."""
    from gsigmad.governance.gates.fdr_contract import traits_coverage_matrix
    from gsigmad.commands.run import GATE_CHAIN

    result = traits_coverage_matrix(GATE_CHAIN)
    assert "covered" in result
    assert "uncovered" in result
    assert isinstance(result["covered"], dict)
    assert isinstance(result["uncovered"], list)
    assert result["total_pillars"] == 6
    # At least some pillars should be covered by the 6 gates
    assert result["covered_count"] >= 4
