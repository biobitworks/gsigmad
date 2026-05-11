"""Shared test fixtures for Phase 1 gate tests."""
import pytest
from datetime import datetime, timezone


@pytest.fixture
def sample_exp_record():
    """Minimal EXP pre-registration record for gate testing."""
    return {
        "exp_id": "EXP-001",
        "classification": "CONFIRMATORY",
        "created_at": "2026-01-01T10:00:00Z",
        "author": "test-agent",
        "sig": "SIG-20260101T100000Z-test-a1b2",
        "hypothesis": {
            "h0": "Effect equals zero",
            "h1": "Effect is non-zero (|delta| > 0.4)",
            "test": "ttest_ind",
            "alpha": 0.05,
            "mesi": 0.4,
        },
        "power_analysis": {
            "tier": "formula",
            "test_type": "ttest_ind",
            "required_n": 100,
            "effect_size_mesi": 0.4,
            "alpha": 0.05,
            "achieved_power": 0.80,
            "computed_at": "2026-01-01T10:00:00Z",
            "tool_version": "statsmodels-0.14.5",
        },
        "gates": {
            "data_contract": "PASS",
            "temporal_integrity": "PASS",
            "red_team": "PASS",
            "power_analysis": "PASS",
        },
    }


@pytest.fixture
def sample_canon_core_text():
    """Minimal CANON-CORE document text for structure tests."""
    return """# CANON-CORE

> **Status**: ACTIVE
> **Version**: 1.0.0

## Invariants

### Invariant 1
No fabricated data, claims, or values.

### Invariant 2
Run-id-specific result artifacts only.
"""


@pytest.fixture
def sample_decision_tree_yaml():
    """Minimal valid decision tree YAML for schema tests."""
    return {
        "version": "1.0",
        "exp_id": "EXP-001",
        "created_at": "2026-01-01T10:00:00Z",
        "author": "test-agent",
        "primary_analysis": {
            "test": "ttest_ind",
            "correction": None,
            "post_hoc": None,
        },
        "conditional_branches": [],
        "stopping_rules": {
            "type": "fixed_n",
            "max_n": 200,
            "interim_analyses": [],
        },
        "deviations_require": "new_EXP",
        "sensitivity_analyses": [],
    }


@pytest.fixture
def sample_fdr_chain():
    """Valid 3-level proteomics FDR chain for gate testing."""
    return {
        "levels": [
            {"name": "PSM", "threshold": 0.01},
            {"name": "peptide", "threshold": 0.01},
            {"name": "protein", "threshold": 0.05},
        ],
        "method": "fdr_bh",
        "tool": "Percolator",
        "tool_version": "3.06.1",
    }


@pytest.fixture
def sample_exp_with_fdr(sample_exp_record, sample_fdr_chain):
    """EXP record with fdr_chain attached."""
    import copy
    record = copy.deepcopy(sample_exp_record)
    record["fdr_chain"] = copy.deepcopy(sample_fdr_chain)
    return record


@pytest.fixture
def sample_null_model():
    """Valid null model declaration for gate testing."""
    return {
        "strategy": "permutation",
        "n_permutations": 1000,
        "baseline_description": "Random shuffling of target labels",
        "exchangeability_assumption": "Target labels are exchangeable under null hypothesis",
        "novel_space": False,
        "justification": None,
        "validation_evidence": None,
    }


@pytest.fixture
def sample_exp_with_null_model(sample_exp_record, sample_null_model):
    """EXP record with null_model attached."""
    import copy
    record = copy.deepcopy(sample_exp_record)
    record["null_model"] = copy.deepcopy(sample_null_model)
    return record


@pytest.fixture
def sample_calibration_declaration():
    """Valid calibration declaration dict for gate testing."""
    return {
        "calibrated": True,
        "method": "platt_scaling",
        "tool": "scikit-learn",
        "tool_version": "1.5.0",
        "calibration_n": 500,
        "brier_score": 0.12,
        "ece_score": 0.04,
        "procedure_ref": "calibration/platt_procedure.md",
    }


@pytest.fixture
def sample_exp_with_calibration(sample_exp_record, sample_calibration_declaration):
    """EXP record with data_contract containing a scored field with calibration sub-block."""
    import copy
    record = copy.deepcopy(sample_exp_record)
    record["data_contract"] = {
        "interface": "model -> output",
        "fields": [
            {
                "name": "confidence_score",
                "type": "float",
                "range": [0.0, 1.0],
                "required": True,
                "calibration": copy.deepcopy(sample_calibration_declaration),
            },
        ],
    }
    return record
