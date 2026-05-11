"""
Decision tree Pydantic v2 schema — STAT-02.

Validates conditional analysis decision trees authored in YAML.
Per D-09: full analysis plans (test selection, correction, sensitivity analyses, stopping rules).
Per D-10: JSON schema generated from this model for ArangoDB validation.

Reference: CANON-CORE Invariant 5 (pre-registration), EXPERIMENT_STANDARDS.md §2
"""
import json
from datetime import datetime
from pathlib import Path
from typing import List, Literal, Optional

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic import ValidationError  # re-export for convenience


class SensitivityAnalysis(BaseModel):
    """A pre-specified sensitivity analysis to run if trigger condition is met."""
    name: str = Field(..., description="Short name for this sensitivity analysis")
    trigger: str = Field(..., description="Condition that activates this analysis, e.g. 'shapiro_wilk_p < 0.05'")
    fallback_test: str = Field(..., description="Alternative test to use if trigger fires")


class Analysis(BaseModel):
    """A statistical analysis specification."""
    test: str = Field(..., description="Statistical test, e.g. 'ttest_ind', 'anova_oneway', 'logrank'")
    correction: Optional[str] = Field(None, description="Multiple comparison correction, e.g. 'bonferroni', 'fdr_bh'")
    post_hoc: Optional[str] = Field(None, description="Post-hoc test, e.g. 'tukey_hsd', 'dunn'")
    stopping_rule: Optional[str] = Field(None, description="Test-level stopping rule if different from global")


class ConditionalBranch(BaseModel):
    """A conditional analysis branch activated when a condition is met."""
    condition: str = Field(..., description="Boolean condition, e.g. 'n_groups > 2', 'outcome_type == survival'")
    analysis: Analysis


class StoppingRule(BaseModel):
    """Stopping rule for the experiment."""
    type: Literal["fixed_n", "sequential", "adaptive"] = Field(
        ..., description="'fixed_n': no interim analyses; 'sequential': GST/SPRT; 'adaptive': Bayesian adaptive"
    )
    max_n: int = Field(..., ge=1, description="Maximum sample size — execution must stop at or before this N")
    interim_analyses: List[dict] = Field(
        default_factory=list,
        description="List of interim analysis specifications (for sequential/adaptive designs)"
    )


class DecisionTree(BaseModel):
    """
    Full conditional analysis decision tree for an EXP pre-registration.

    Per D-09: must specify the complete analysis plan including:
    - Primary analysis (test, correction method)
    - Conditional branches (if/then alternative analyses)
    - Stopping rules (when to stop data collection)
    - Sensitivity analyses (pre-specified robustness checks)
    - Deviations require a new EXP (prevents post-hoc plan modification)
    """
    version: str = Field("1.0", description="Decision tree schema version")
    exp_id: str = Field(
        ...,
        pattern=r"^EXP-\d{3,}$",
        description="EXP identifier this tree belongs to, e.g. 'EXP-042'"
    )
    created_at: datetime = Field(..., description="ISO 8601 timestamp when tree was authored")
    author: str = Field(..., description="Agent that authored this decision tree (SIG-ID agent component)")
    primary_analysis: Analysis = Field(
        ...,
        description="The pre-specified primary analysis. This is the analysis that will be used "
                    "unless a conditional branch triggers."
    )
    conditional_branches: List[ConditionalBranch] = Field(
        default_factory=list,
        description="Pre-specified alternative analyses activated by conditions. "
                    "Per D-09: must cover key sensitivity scenarios."
    )
    stopping_rules: StoppingRule = Field(
        ...,
        description="When to stop data collection. Required. Per D-09: must be fully specified."
    )
    deviations_require: Literal["new_EXP"] = Field(
        "new_EXP",
        description="Any deviation from this tree requires a new EXP, not a post-hoc amendment."
    )
    sensitivity_analyses: List[SensitivityAnalysis] = Field(
        default_factory=list,
        description="Pre-specified robustness checks. Per D-09: must cover normality violations, "
                    "outlier handling, variance heterogeneity at minimum."
    )

    @field_validator("exp_id")
    @classmethod
    def exp_id_format(cls, v: str) -> str:
        if not v.startswith("EXP-"):
            raise ValueError(f"exp_id must start with 'EXP-'. Got: {v!r}")
        return v


def validate_decision_tree(yaml_path: str) -> dict:
    """
    Load and validate a decision tree YAML file against the DecisionTree schema.

    Args:
        yaml_path: Path to the decision tree YAML file.

    Returns:
        {"valid": True, "tree": dict}  — on success
        {"valid": False, "errors": list}  — on validation failure
    """
    try:
        with open(yaml_path) as f:
            raw = yaml.safe_load(f)
        tree = DecisionTree.model_validate(raw)
        return {"valid": True, "tree": tree.model_dump(mode="json")}
    except ValidationError as e:
        return {"valid": False, "errors": e.errors()}
    except Exception as e:
        return {"valid": False, "errors": [{"msg": str(e), "type": "parse_error"}]}


def generate_json_schema(output_path: Optional[str] = None) -> dict:
    """
    Generate the JSON Schema (draft 2020-12) from the DecisionTree Pydantic model.
    Used to populate governance/schemas/decision_tree.json.

    Args:
        output_path: If provided, write schema to this file path.

    Returns:
        The JSON Schema dict.
    """
    schema = DecisionTree.model_json_schema()
    # Add $schema and $id for draft compliance (D-10: following Overwatch canon.json pattern)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "https://gettingsciencedone/schemas/decision-tree/v1.0"

    if output_path:
        with open(output_path, "w") as f:
            json.dump(schema, f, indent=2)

    return schema
