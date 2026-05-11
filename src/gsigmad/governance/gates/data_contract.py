"""
Data contract blocking pre-flight gate — EXP-01.

Promotes data-contract validation from optional audit to a mandatory blocking
pre-flight gate in run-experiment. Validates interface boundaries before execution.

Reference: CANON-CORE Invariant 1 (all data traced to source), data-contract.md skill
"""
from typing import Any, List, Literal, Optional
from pydantic import BaseModel, Field

# -- TRAITS pillar mapping (REP-02) --

TRAITS_PILLARS: dict[str, list[str]] = {
    "data_contract": ["Accurate", "Traceable"],
    "calibration": ["Accurate", "Interpretable"],
}


class CalibrationDeclaration(BaseModel):
    """Score calibration declaration for a ContractField.

    Declares whether a scored output has been calibrated, with what method,
    and what evidence supports the calibration quality.  Part of the
    score-to-probability contract (CAL-01).
    """
    calibrated: bool = False
    method: Optional[Literal[
        "platt_scaling",
        "isotonic_regression",
        "beta_calibration",
        "temperature_scaling",
        "none",
    ]] = None
    tool: Optional[str] = None
    tool_version: Optional[str] = None
    calibration_dataset: Optional[str] = None
    calibration_n: Optional[int] = Field(default=None, ge=1)
    brier_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    ece_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    procedure_ref: Optional[str] = None


class ContractField(BaseModel):
    """Definition of a single field in a data interface contract."""
    name: str
    type: Literal["float", "int", "str", "bool", "list", "dict"]
    unit: Optional[str] = None
    range: Optional[List[float]] = None  # [min, max]; None means no range constraint
    required: bool = True
    enum_values: Optional[List[Any]] = None
    calibration: Optional[CalibrationDeclaration] = None


class DataContract(BaseModel):
    """A contract defining the expected interface between two modules."""
    interface: str  # e.g., "module_A -> module_B"
    fields: List[ContractField]
    validated: bool = False
    violations: List[str] = []


def validate_data_contract(contract: dict, data: dict) -> dict:
    """
    Validate data against a contract definition.

    Args:
        contract: Contract dict matching DataContract schema.
                  Must contain: interface (str), fields (list of ContractField dicts).
        data: The actual data dict to validate.

    Returns:
        {"valid": bool, "violations": list[str], "halt_message": Optional[str]}
        On violation, halt_message contains "DATA CONTRACT VIOLATION" with interface and violation list.
    """
    violations = []

    # Parse contract fields
    try:
        parsed_contract = DataContract.model_validate(contract)
    except Exception as e:
        return {
            "valid": False,
            "violations": [f"Contract definition error: {str(e)}"],
            "halt_message": (
                f"DATA CONTRACT VIOLATION — cannot proceed with experiment.\n"
                f"Interface: {contract.get('interface', 'unknown')}\n"
                f"Contract parse error: {str(e)}\n"
                "Fix: Verify the data contract schema in the experiment's contract file."
            )
        }

    interface = parsed_contract.interface

    for field in parsed_contract.fields:
        value = data.get(field.name)

        # Required field check
        if field.required and value is None:
            violations.append(f"Missing required field '{field.name}'")
            continue

        if value is None:
            continue  # Optional field, not present — OK

        # Type check
        type_map = {
            "float": (float, int),  # int is acceptable for float fields
            "int": (int,),
            "str": (str,),
            "bool": (bool,),
            "list": (list,),
            "dict": (dict,),
        }
        expected_types = type_map.get(field.type, (object,))
        if not isinstance(value, expected_types):
            violations.append(
                f"Field '{field.name}': expected type {field.type}, "
                f"got {type(value).__name__} (value: {repr(value)[:50]})"
            )
            continue

        # Range check (numeric fields only)
        if field.range and field.type in ("float", "int"):
            min_val, max_val = field.range[0], field.range[1]
            if not (min_val <= value <= max_val):
                violations.append(
                    f"Field '{field.name}': value {value} out of documented range "
                    f"[{min_val}, {max_val}]"
                    + (f" {field.unit}" if field.unit else "")
                )

        # Enum check
        if field.enum_values is not None and value not in field.enum_values:
            violations.append(
                f"Field '{field.name}': value {repr(value)} not in allowed values "
                f"{field.enum_values}"
            )

    if violations:
        violation_list = "\n".join(f"  - {v}" for v in violations)
        halt_message = (
            f"DATA CONTRACT VIOLATION — cannot proceed with experiment.\n"
            f"Interface: {interface}\n"
            f"Violations:\n{violation_list}\n"
            f"Fix: Update the data contract schema or fix the data before re-running.\n"
            "Reference: CANON-CORE Invariant 1 (no fabricated data, all data traced to source)"
        )
        return {"valid": False, "violations": violations, "halt_message": halt_message}

    return {"valid": True, "violations": [], "halt_message": None}


def validate_calibration(field_dict: dict) -> list[str]:
    """Validate a calibration declaration on a contract field.

    Rules (per CAL-01, D-01, D-05, D-07, D-08):
    - No calibration block -> [] (SKIP, not a scored field or pre-v1.7)
    - calibrated=False -> [] (advisory only, not blocking)
    - calibrated=True + method is None or "none" -> CALIBRATION_METHOD_MISSING
    - calibrated=True + valid method but no evidence -> CALIBRATION_EVIDENCE_INSUFFICIENT
      Evidence = at least one of: tool, brier_score, ece_score, procedure_ref

    Args:
        field_dict: A dict representing a ContractField (may or may not have
                    a ``calibration`` sub-dict).

    Returns:
        List of violation strings (empty if valid or skipped).
    """
    cal = field_dict.get("calibration")
    if cal is None:
        return []

    calibrated = cal.get("calibrated", False)
    if not calibrated:
        return []

    violations: list[str] = []
    method = cal.get("method")

    # Method must be declared and not "none"
    if method is None or method == "none":
        field_name = field_dict.get("name", "<unknown>")
        violations.append(
            f"CALIBRATION_METHOD_MISSING: field '{field_name}' declares "
            f"calibrated=True but method is {method!r}"
        )
        return violations

    # Evidence check: at least one of tool, brier_score, ece_score, procedure_ref
    has_tool = bool(cal.get("tool"))
    has_brier = cal.get("brier_score") is not None
    has_ece = cal.get("ece_score") is not None
    has_ref = bool(cal.get("procedure_ref"))

    if not (has_tool or has_brier or has_ece or has_ref):
        field_name = field_dict.get("name", "<unknown>")
        violations.append(
            f"CALIBRATION_EVIDENCE_INSUFFICIENT: field '{field_name}' declares "
            f"calibrated=True with method='{method}' but provides no evidence "
            f"(need at least one of: tool, brier_score, ece_score, procedure_ref)"
        )

    return violations
