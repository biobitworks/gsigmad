"""
Tests for decision tree Pydantic schema (STAT-02).

TDD: These tests define the interface before implementation.
"""
import json
import os
import tempfile

import pytest


VALID_TREE_DICT = {
    "version": "1.0",
    "exp_id": "EXP-001",
    "created_at": "2026-03-31T10:00:00Z",
    "author": "claude-sonnet-4-6",
    "primary_analysis": {
        "test": "ttest_ind",
        "correction": None,
        "post_hoc": None,
    },
    "conditional_branches": [
        {
            "condition": "n_groups > 2",
            "analysis": {
                "test": "anova_oneway",
                "correction": "bonferroni",
                "post_hoc": "tukey_hsd",
            }
        }
    ],
    "stopping_rules": {
        "type": "fixed_n",
        "max_n": 200,
        "interim_analyses": [],
    },
    "deviations_require": "new_EXP",
    "sensitivity_analyses": [
        {
            "name": "normality_violation",
            "trigger": "shapiro_wilk_p < 0.05",
            "fallback_test": "mann_whitney_u",
        }
    ],
}

VALID_TREE_YAML = """
version: "1.0"
exp_id: "EXP-001"
created_at: "2026-03-31T10:00:00Z"
author: "claude-sonnet-4-6"
primary_analysis:
  test: "ttest_ind"
  correction: null
  post_hoc: null
conditional_branches:
  - condition: "n_groups > 2"
    analysis:
      test: "anova_oneway"
      correction: "bonferroni"
      post_hoc: "tukey_hsd"
stopping_rules:
  type: "fixed_n"
  max_n: 200
  interim_analyses: []
deviations_require: "new_EXP"
sensitivity_analyses:
  - name: "normality_violation"
    trigger: "shapiro_wilk_p < 0.05"
    fallback_test: "mann_whitney_u"
"""


def test_yaml_to_json():
    """DecisionTree.model_validate accepts a valid dict and produces correct model."""
    from gsigmad.governance.schemas.decision_tree import DecisionTree
    tree = DecisionTree.model_validate(VALID_TREE_DICT)
    assert tree.exp_id == "EXP-001"
    assert tree.stopping_rules.type == "fixed_n"
    assert tree.stopping_rules.max_n == 200
    assert len(tree.conditional_branches) == 1
    assert tree.conditional_branches[0].condition == "n_groups > 2"


def test_invalid_tree_rejected():
    """DecisionTree.model_validate raises ValidationError when stopping_rules is missing."""
    from pydantic import ValidationError
    from gsigmad.governance.schemas.decision_tree import DecisionTree
    invalid = {k: v for k, v in VALID_TREE_DICT.items() if k != "stopping_rules"}
    with pytest.raises(ValidationError):
        DecisionTree.model_validate(invalid)


def test_invalid_exp_id_rejected():
    """DecisionTree rejects exp_id that does not match EXP-\\d{3,} pattern."""
    from pydantic import ValidationError
    from gsigmad.governance.schemas.decision_tree import DecisionTree
    bad = dict(VALID_TREE_DICT)
    bad["exp_id"] = "WRONG-001"
    with pytest.raises(ValidationError):
        DecisionTree.model_validate(bad)


def test_json_schema_file_exists():
    """governance/schemas/decision_tree.json exists and has type == object."""
    schema_path = os.path.join(
        os.path.dirname(__file__), "..", "src", "gsigmad", "governance", "schemas", "decision_tree.json"
    )
    assert os.path.isfile(schema_path), f"Schema file not found: {schema_path}"
    with open(schema_path) as f:
        schema = json.load(f)
    assert schema["type"] == "object"
    assert "$schema" in schema


def test_validate_decision_tree_valid(tmp_path):
    """validate_decision_tree returns valid=True for a valid YAML file."""
    import yaml
    from gsigmad.governance.schemas.decision_tree import validate_decision_tree
    yaml_file = tmp_path / "decision_tree.yaml"
    yaml_file.write_text(VALID_TREE_YAML)
    result = validate_decision_tree(str(yaml_file))
    assert result["valid"] is True
    assert "tree" in result


def test_validate_decision_tree_invalid(tmp_path):
    """validate_decision_tree returns valid=False for an invalid YAML file."""
    from gsigmad.governance.schemas.decision_tree import validate_decision_tree
    bad_yaml = """
version: "1.0"
exp_id: "EXP-001"
created_at: "2026-03-31T10:00:00Z"
author: "test"
primary_analysis:
  test: "ttest_ind"
# stopping_rules intentionally omitted — should fail validation
deviations_require: "new_EXP"
"""
    yaml_file = tmp_path / "bad_tree.yaml"
    yaml_file.write_text(bad_yaml)
    result = validate_decision_tree(str(yaml_file))
    assert result["valid"] is False
    assert "errors" in result


def test_sensitivity_analysis_model():
    """SensitivityAnalysis model validates correctly."""
    from gsigmad.governance.schemas.decision_tree import SensitivityAnalysis
    sa = SensitivityAnalysis(
        name="normality_violation",
        trigger="shapiro_wilk_p < 0.05",
        fallback_test="mann_whitney_u"
    )
    assert sa.name == "normality_violation"
    assert sa.fallback_test == "mann_whitney_u"


def test_stopping_rule_type_validation():
    """StoppingRule rejects invalid type values."""
    from pydantic import ValidationError
    from gsigmad.governance.schemas.decision_tree import StoppingRule
    with pytest.raises(ValidationError):
        StoppingRule(type="invalid_type", max_n=100)


def test_deviations_require_locked():
    """DecisionTree.deviations_require must be 'new_EXP' — any other value is rejected."""
    from pydantic import ValidationError
    from gsigmad.governance.schemas.decision_tree import DecisionTree
    bad = dict(VALID_TREE_DICT)
    bad["deviations_require"] = "amendment"
    with pytest.raises(ValidationError):
        DecisionTree.model_validate(bad)
