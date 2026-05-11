"""Tests for null model governance gate (NULL-01, NULL-02, NULL-03).

TDD RED: Tests written first to define the required interface.
"""
import pytest


# -- NULL-01: Schema validation, backward compat, strategy enforcement --

def test_null_model_skip_pre_v17(sample_exp_record):
    """EXP record with no null_model key returns pass=True with skip note."""
    from gsigmad.governance.gates.null_model import check_null_model_gate

    assert "null_model" not in sample_exp_record
    result = check_null_model_gate(sample_exp_record)
    assert result["pass"] is True
    assert "skipped" in result["note"].lower() or "pre-v1.7" in result["note"].lower()


def test_null_model_skip_none(sample_exp_record):
    """EXP record with null_model=None returns pass=True with skip note."""
    from gsigmad.governance.gates.null_model import check_null_model_gate

    sample_exp_record["null_model"] = None
    result = check_null_model_gate(sample_exp_record)
    assert result["pass"] is True
    assert "note" in result


def test_null_model_confirmatory_required(sample_exp_with_null_model):
    """CONFIRMATORY EXP with valid null_model block returns pass=True."""
    from gsigmad.governance.gates.null_model import check_null_model_gate

    result = check_null_model_gate(sample_exp_with_null_model)
    assert result["pass"] is True


def test_null_model_schema_validation(sample_exp_record):
    """null_model block missing required field (baseline_description) returns pass=False."""
    from gsigmad.governance.gates.null_model import check_null_model_gate

    sample_exp_record["null_model"] = {
        "strategy": "permutation",
        "n_permutations": 1000,
        # baseline_description missing
        "exchangeability_assumption": "Labels exchangeable",
        "novel_space": False,
    }
    result = check_null_model_gate(sample_exp_record)
    assert result["pass"] is False
    assert "NULL_MODEL_SCHEMA_INVALID" in result["error"]


def test_null_model_invalid_strategy(sample_exp_record):
    """null_model with strategy='bogus' returns pass=False."""
    from gsigmad.governance.gates.null_model import check_null_model_gate

    sample_exp_record["null_model"] = {
        "strategy": "bogus",
        "n_permutations": 1000,
        "baseline_description": "Random shuffling",
        "exchangeability_assumption": "Labels exchangeable",
        "novel_space": False,
    }
    result = check_null_model_gate(sample_exp_record)
    assert result["pass"] is False
    assert "NULL_MODEL_INVALID_STRATEGY" in result["error"]


def test_null_model_permutation_requires_n(sample_exp_record):
    """strategy='permutation' with n_permutations=None returns pass=False."""
    from gsigmad.governance.gates.null_model import check_null_model_gate

    sample_exp_record["null_model"] = {
        "strategy": "permutation",
        "n_permutations": None,
        "baseline_description": "Random shuffling",
        "exchangeability_assumption": "Labels exchangeable",
        "novel_space": False,
    }
    result = check_null_model_gate(sample_exp_record)
    assert result["pass"] is False
    assert "NULL_MODEL_MISSING_PERMUTATIONS" in result["error"]


def test_null_model_shuffle_requires_n(sample_exp_record):
    """strategy='shuffle' with n_permutations=None returns pass=False."""
    from gsigmad.governance.gates.null_model import check_null_model_gate

    sample_exp_record["null_model"] = {
        "strategy": "shuffle",
        "n_permutations": None,
        "baseline_description": "Random shuffling of features",
        "exchangeability_assumption": "Features exchangeable under null",
        "novel_space": False,
    }
    result = check_null_model_gate(sample_exp_record)
    assert result["pass"] is False
    assert "NULL_MODEL_MISSING_PERMUTATIONS" in result["error"]


def test_null_model_theoretical_no_n(sample_exp_record):
    """strategy='theoretical' with n_permutations=None returns pass=True."""
    from gsigmad.governance.gates.null_model import check_null_model_gate

    sample_exp_record["null_model"] = {
        "strategy": "theoretical",
        "n_permutations": None,
        "baseline_description": "Theoretical null distribution",
        "exchangeability_assumption": "Samples drawn from same population",
        "novel_space": False,
    }
    result = check_null_model_gate(sample_exp_record)
    assert result["pass"] is True


# -- NULL-02: Novel space justification --

def test_novel_space_missing_justification(sample_exp_record):
    """novel_space=True with justification=None returns pass=False."""
    from gsigmad.governance.gates.null_model import check_null_model_gate

    sample_exp_record["null_model"] = {
        "strategy": "permutation",
        "n_permutations": 1000,
        "baseline_description": "Custom permutation scheme",
        "exchangeability_assumption": "Custom assumption",
        "novel_space": True,
        "justification": None,
        "validation_evidence": [{"type": "doi", "reference": "10.1234/test"}],
    }
    result = check_null_model_gate(sample_exp_record)
    assert result["pass"] is False
    assert "NULL_MODEL_NOVEL_MISSING_JUSTIFICATION" in result["error"]


def test_novel_space_empty_justification(sample_exp_record):
    """novel_space=True with justification='' returns pass=False."""
    from gsigmad.governance.gates.null_model import check_null_model_gate

    sample_exp_record["null_model"] = {
        "strategy": "permutation",
        "n_permutations": 1000,
        "baseline_description": "Custom permutation scheme",
        "exchangeability_assumption": "Custom assumption",
        "novel_space": True,
        "justification": "",
        "validation_evidence": [{"type": "doi", "reference": "10.1234/test"}],
    }
    result = check_null_model_gate(sample_exp_record)
    assert result["pass"] is False
    assert "NULL_MODEL_NOVEL_MISSING_JUSTIFICATION" in result["error"]


def test_novel_space_missing_evidence(sample_exp_record):
    """novel_space=True with validation_evidence=None returns pass=False."""
    from gsigmad.governance.gates.null_model import check_null_model_gate

    sample_exp_record["null_model"] = {
        "strategy": "permutation",
        "n_permutations": 1000,
        "baseline_description": "Custom permutation scheme",
        "exchangeability_assumption": "Custom assumption",
        "novel_space": True,
        "justification": "This is a novel search space because...",
        "validation_evidence": None,
    }
    result = check_null_model_gate(sample_exp_record)
    assert result["pass"] is False
    assert "NULL_MODEL_NOVEL_MISSING_EVIDENCE" in result["error"]


def test_novel_space_empty_evidence(sample_exp_record):
    """novel_space=True with validation_evidence=[] returns pass=False."""
    from gsigmad.governance.gates.null_model import check_null_model_gate

    sample_exp_record["null_model"] = {
        "strategy": "permutation",
        "n_permutations": 1000,
        "baseline_description": "Custom permutation scheme",
        "exchangeability_assumption": "Custom assumption",
        "novel_space": True,
        "justification": "This is a novel search space because...",
        "validation_evidence": [],
    }
    result = check_null_model_gate(sample_exp_record)
    assert result["pass"] is False
    assert "NULL_MODEL_NOVEL_MISSING_EVIDENCE" in result["error"]


def test_novel_space_valid(sample_exp_record):
    """novel_space=True with justification and evidence returns pass=True."""
    from gsigmad.governance.gates.null_model import check_null_model_gate

    sample_exp_record["null_model"] = {
        "strategy": "permutation",
        "n_permutations": 1000,
        "baseline_description": "Novel permutation for custom space",
        "exchangeability_assumption": "Domain-specific exchangeability",
        "novel_space": True,
        "justification": "This search space has not been previously characterized",
        "validation_evidence": [{"type": "doi", "reference": "10.1234/test"}],
    }
    result = check_null_model_gate(sample_exp_record)
    assert result["pass"] is True


def test_novel_space_evidence_types(sample_exp_record):
    """validation_evidence with type='simulation' and type='first_principles' both accepted."""
    from gsigmad.governance.gates.null_model import check_null_model_gate

    sample_exp_record["null_model"] = {
        "strategy": "permutation",
        "n_permutations": 1000,
        "baseline_description": "Novel permutation for custom space",
        "exchangeability_assumption": "Domain-specific exchangeability",
        "novel_space": True,
        "justification": "This search space has not been previously characterized",
        "validation_evidence": [
            {"type": "simulation", "reference": "Monte Carlo simulation v2"},
            {"type": "first_principles", "reference": "Derivation in appendix A"},
        ],
    }
    result = check_null_model_gate(sample_exp_record)
    assert result["pass"] is True


# -- NULL-03: Classification-tiered enforcement --

def test_null_model_exploratory_no_block(sample_exp_record):
    """EXPLORATORY EXP with no null_model key returns pass=True with ADVISORY note."""
    from gsigmad.governance.gates.null_model import check_null_model_gate

    sample_exp_record["classification"] = "EXPLORATORY"
    assert "null_model" not in sample_exp_record
    result = check_null_model_gate(sample_exp_record)
    assert result["pass"] is True
    assert "ADVISORY" in result["note"]


def test_null_model_exploratory_with_block(sample_exp_record):
    """EXPLORATORY EXP with valid null_model block returns pass=True with advisory note."""
    from gsigmad.governance.gates.null_model import check_null_model_gate

    sample_exp_record["classification"] = "EXPLORATORY"
    sample_exp_record["null_model"] = {
        "strategy": "permutation",
        "n_permutations": 1000,
        "baseline_description": "Random shuffling",
        "exchangeability_assumption": "Labels exchangeable",
        "novel_space": False,
    }
    result = check_null_model_gate(sample_exp_record)
    assert result["pass"] is True
    assert "note" in result


def test_null_model_replication_required(sample_exp_record):
    """REPLICATION EXP with valid null_model block returns pass=True."""
    from gsigmad.governance.gates.null_model import check_null_model_gate

    sample_exp_record["classification"] = "REPLICATION"
    sample_exp_record["null_model"] = {
        "strategy": "permutation",
        "n_permutations": 1000,
        "baseline_description": "Random shuffling of target labels",
        "exchangeability_assumption": "Target labels are exchangeable under null hypothesis",
        "novel_space": False,
    }
    result = check_null_model_gate(sample_exp_record)
    assert result["pass"] is True


def test_null_model_replication_no_block_pre_v17(sample_exp_record):
    """REPLICATION EXP with no null_model key returns pass=True with skip note."""
    from gsigmad.governance.gates.null_model import check_null_model_gate

    sample_exp_record["classification"] = "REPLICATION"
    assert "null_model" not in sample_exp_record
    result = check_null_model_gate(sample_exp_record)
    assert result["pass"] is True
    assert "note" in result


# -- Fixture tests: TRAITS pillar declarations --

def test_null_model_traits_pillars():
    """TRAITS_PILLARS = {'null_model': ['Rigorous', 'Accurate']}."""
    from gsigmad.governance.gates.null_model import TRAITS_PILLARS

    assert "null_model" in TRAITS_PILLARS
    assert "Rigorous" in TRAITS_PILLARS["null_model"]
    assert "Accurate" in TRAITS_PILLARS["null_model"]


def test_gate_returns_traits(sample_exp_with_null_model):
    """Valid gate result includes traits=['Rigorous', 'Accurate']."""
    from gsigmad.governance.gates.null_model import check_null_model_gate

    result = check_null_model_gate(sample_exp_with_null_model)
    assert result["pass"] is True
    assert "traits" in result
    assert "Rigorous" in result["traits"]
    assert "Accurate" in result["traits"]


# -- Template extension tests --

def test_exp_template_confirmatory_has_null_model():
    """exp_template('EXP-1', 'CONFIRMATORY') produces dict with 'null_model' key."""
    from gsigmad.scaffold.templates import exp_template

    record = exp_template("EXP-1", "CONFIRMATORY")
    assert "null_model" in record
    assert "strategy" in record["null_model"]
    assert "baseline_description" in record["null_model"]
    assert "exchangeability_assumption" in record["null_model"]
    assert "novel_space" in record["null_model"]


def test_exp_template_exploratory_no_null_model():
    """exp_template('EXP-1', 'EXPLORATORY') produces dict WITHOUT 'null_model' key."""
    from gsigmad.scaffold.templates import exp_template

    record = exp_template("EXP-1", "EXPLORATORY")
    assert "null_model" not in record


def test_exp_template_replication_no_null_model():
    """exp_template('EXP-1', 'REPLICATION') produces dict WITHOUT 'null_model' key."""
    from gsigmad.scaffold.templates import exp_template

    record = exp_template("EXP-1", "REPLICATION")
    assert "null_model" not in record


# -- REP-02: TRAITS pillar integration --

def test_null_model_traits_declared():
    """null_model module has TRAITS_PILLARS = {'null_model': ['Rigorous', 'Accurate']}."""
    from gsigmad.governance.gates.null_model import TRAITS_PILLARS

    assert "null_model" in TRAITS_PILLARS
    assert "Rigorous" in TRAITS_PILLARS["null_model"]
    assert "Accurate" in TRAITS_PILLARS["null_model"]


def test_null_model_gate_returns_traits(sample_exp_with_null_model):
    """Valid CONFIRMATORY gate result includes traits=['Rigorous', 'Accurate']."""
    from gsigmad.governance.gates.null_model import check_null_model_gate

    result = check_null_model_gate(sample_exp_with_null_model)
    assert result["pass"] is True
    assert "traits" in result
    assert "Rigorous" in result["traits"]
    assert "Accurate" in result["traits"]


def test_null_model_skip_returns_traits(sample_exp_record):
    """Skip result (no null_model) also includes traits key."""
    from gsigmad.governance.gates.null_model import check_null_model_gate

    result = check_null_model_gate(sample_exp_record)
    assert result["pass"] is True
    assert "traits" in result


def test_null_model_advisory_returns_traits():
    """EXPLORATORY advisory result includes traits key."""
    from gsigmad.governance.gates.null_model import check_null_model_gate

    exp = {"classification": "EXPLORATORY"}
    result = check_null_model_gate(exp)
    assert result["pass"] is True
    assert "traits" in result


def test_traits_coverage_matrix_includes_null_model():
    """traits_coverage_matrix discovers null_model Rigorous and Accurate pillars."""
    from gsigmad.governance.gates.fdr_contract import traits_coverage_matrix
    from gsigmad.commands.run import GATE_CHAIN

    result = traits_coverage_matrix(GATE_CHAIN)
    # null_model should contribute to Rigorous and Accurate
    assert "Rigorous" in result["covered"]
    assert "null_model" in result["covered"]["Rigorous"]
    assert "Accurate" in result["covered"]
    assert "null_model" in result["covered"]["Accurate"]


# -- REP-03: RT challenge_target for null model --

def test_rt_challenge_target_null_model():
    """RT record with challenge_target='null_model.strategy' passes through red_team gate."""
    from gsigmad.governance.gates.red_team import check_red_team_gate

    result = check_red_team_gate(
        "CONFIRMATORY",
        {"h0": "No effect", "challenge_target": "null_model.strategy",
         "risk_tier": "P1", "red_team_status": "PASS",
         "remediation_constraints": ["Validate with independent data"],
         "execution_decision": "GO"},
    )
    # challenge_target is metadata, does not block
    assert result["pass"] is True


def test_rt_challenge_target_null_model_exchangeability():
    """RT record with challenge_target='null_model.exchangeability_assumption' passes."""
    from gsigmad.governance.gates.red_team import check_red_team_gate

    result = check_red_team_gate(
        "CONFIRMATORY",
        {"h0": "No effect", "challenge_target": "null_model.exchangeability_assumption",
         "risk_tier": "P1", "red_team_status": "PASS",
         "remediation_constraints": ["Check exchangeability"],
         "execution_decision": "GO"},
    )
    assert result["pass"] is True
