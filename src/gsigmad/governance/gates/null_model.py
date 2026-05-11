"""
Null model governance gate -- NULL-01, NULL-02, NULL-03.

Validates that experiments declare their null model strategy before execution.
Enforces classification-tiered rules:

  - CONFIRMATORY: full validation required (schema, strategy, permutation count,
    novel space justification)
  - EXPLORATORY: advisory only (pass with note, never blocking)
  - REPLICATION: same validation as CONFIRMATORY (must declare valid null model)

Pre-v1.7 backward compatibility: records without null_model get SKIP (pass with
note), not FAIL.

Reference: NULL-01, NULL-02, NULL-03, D-01 through D-09
"""
from __future__ import annotations

from typing import List, Optional, Literal

from pydantic import BaseModel, Field, ValidationError


# -- TRAITS pillar mapping (D-02) --

TRAITS_PILLARS: dict[str, list[str]] = {
    "null_model": ["Rigorous", "Accurate"],
}

# -- Allowed null model strategies (D-07) --

ALLOWED_STRATEGIES = frozenset({
    "permutation",
    "shuffle",
    "random_baseline",
    "theoretical",
    "established_prior",
})


# -- Pydantic schema models (D-07, D-08, Pitfall 5) --

class ValidationEvidence(BaseModel):
    """A single validation evidence entry for novel search space justification."""
    type: Literal["doi", "simulation", "first_principles"]
    reference: str = Field(min_length=1)


class NullModelDeclaration(BaseModel):
    """Null model declaration for an experiment pre-registration."""
    strategy: str
    n_permutations: Optional[int] = Field(default=None, ge=100)
    baseline_description: str = Field(min_length=1)
    exchangeability_assumption: str = Field(min_length=1)
    novel_space: bool = False
    justification: Optional[str] = None
    validation_evidence: Optional[List[ValidationEvidence]] = None


# -- Gate function (D-04, D-06, D-09) --

def check_null_model_gate(exp_record: dict) -> dict:
    """Validate the null model declaration in an EXP record.

    Returns {"pass": bool, "error": str|None, "traits": list, "note": str|None}.

    Classification-tiered enforcement:
      - CONFIRMATORY: full validation required
      - EXPLORATORY: advisory only (pass with note)
      - REPLICATION: full validation required (same as CONFIRMATORY)

    Pre-v1.7 backward compatibility: if null_model key is absent or None,
    returns pass=True with a skip note (for non-EXPLORATORY classifications).
    """
    traits = TRAITS_PILLARS["null_model"]
    classification = str(exp_record.get("classification", "")).upper()
    null_raw = exp_record.get("null_model")

    # -- Handle missing null_model (D-01) --
    if null_raw is None:
        if classification == "EXPLORATORY":
            return {
                "pass": True,
                "error": None,
                "traits": traits,
                "note": (
                    "ADVISORY: Consider declaring a null model for reproducibility. "
                    "EXPLORATORY experiments are not required to declare null models."
                ),
            }
        # CONFIRMATORY, REPLICATION, or unknown: pre-v1.7 backward compat
        return {
            "pass": True,
            "error": None,
            "traits": traits,
            "note": "No null_model in EXP record; skipped (pre-v1.7 backward compat).",
        }

    # -- EXPLORATORY with block present: advisory only (D-09) --
    if classification == "EXPLORATORY":
        return {
            "pass": True,
            "error": None,
            "traits": traits,
            "note": (
                "ADVISORY: Null model declared -- good practice. "
                "EXPLORATORY experiments are not required to declare null models."
            ),
        }

    # -- CONFIRMATORY and REPLICATION: validate via Pydantic --
    try:
        decl = NullModelDeclaration.model_validate(null_raw)
    except ValidationError as e:
        return {
            "pass": False,
            "error": f"NULL_MODEL_SCHEMA_INVALID: {e}",
            "traits": traits,
        }

    # -- Strategy validation --
    if decl.strategy not in ALLOWED_STRATEGIES:
        return {
            "pass": False,
            "error": (
                f"NULL_MODEL_INVALID_STRATEGY: '{decl.strategy}' not in "
                f"{sorted(ALLOWED_STRATEGIES)}"
            ),
            "traits": traits,
        }

    # -- Permutation count check --
    if decl.strategy in ("permutation", "shuffle") and decl.n_permutations is None:
        return {
            "pass": False,
            "error": (
                f"NULL_MODEL_MISSING_PERMUTATIONS: strategy is '{decl.strategy}' "
                f"but n_permutations is not set. Specify n_permutations >= 100."
            ),
            "traits": traits,
        }

    # -- Novel space justification (NULL-02, D-08) --
    if decl.novel_space:
        if not decl.justification or len(decl.justification.strip()) == 0:
            return {
                "pass": False,
                "error": (
                    "NULL_MODEL_NOVEL_MISSING_JUSTIFICATION: novel_space is True "
                    "but justification is empty. Explain why this search space is novel."
                ),
                "traits": traits,
            }
        if not decl.validation_evidence or len(decl.validation_evidence) == 0:
            return {
                "pass": False,
                "error": (
                    "NULL_MODEL_NOVEL_MISSING_EVIDENCE: novel_space is True but "
                    "no validation_evidence provided. Provide at least one DOI, "
                    "simulation reference, or first-principles derivation."
                ),
                "traits": traits,
            }

    # -- All checks passed --
    return {
        "pass": True,
        "error": None,
        "traits": traits,
    }
