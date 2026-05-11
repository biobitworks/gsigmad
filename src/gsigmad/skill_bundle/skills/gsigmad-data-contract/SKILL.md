---
name: gsigmad-data-contract
description: "Validate data contract fields against observed data. Use when verifying a data contract before experiment execution. Applies to ALL experiment classifications; violations halt execution with DATA_CONTRACT_VIOLATION."
disable-model-invocation: true
allowed-tools:
  - Read
  - Write
  - Bash
  - Glob
  - Grep
---

# Data Contract Enforcer

Define and validate interface schemas, units, ranges between hierarchy layers and pipeline modules.

## Validation Gate (blocking — ALL experiment classifications)

```python
from gsigmad.governance.gates.data_contract import validate_data_contract

result = validate_data_contract(contract=contract_dict, data=data_dict)
if not result["valid"]:
    raise SystemExit(result["halt_message"])  # HALT — halt_message contains DATA CONTRACT VIOLATION
```

Gate applies to ALL experiment classifications (CONFIRMATORY, EXPLORATORY, REPLICATION). Record `data_contract: PASS` in EXP gates block on success.

**Trust tier note (EC-03)**: PROVISIONAL trust tier artifacts cannot be used in CONFIRMATORY evidence chains. If the data being validated originates from a PROVISIONAL artifact, the contract must record this limitation and block promotion to CONFIRMATORY status without human countersignature.

## Audit Protocol

1. Identify the pipeline or model being audited.
2. For each data interface (input/output boundary between modules):

### Schema Validation
- Field names match expected contract
- Data types correct (int/float/str/bool)
- Required fields present (no nulls where not allowed)
- Enum fields contain only valid values

### Unit Validation
- All numeric fields have documented units
- Unit conversions between modules are explicit
- No implicit unit assumptions (e.g., disorder score 0-1 vs 0-100)

### Range Validation
- Values within documented bounds
- Clamp/normalize functions present where needed
- Edge cases handled (division by zero, empty lists, negative values)

## Contract Definition Format

For each interface, produce:

```json
{
  "interface": "module_A -> module_B",
  "fields": [
    {"name": "mean_disorder", "type": "float", "unit": "fraction", "range": [0.0, 1.0], "required": true},
    {"name": "stiffness", "type": "float", "unit": "dimensionless", "range": [0.0, 1000.0], "required": true}
  ],
  "validated": true,
  "violations": []
}
```

## Report Back

- Interfaces audited (count)
- Contracts defined or updated
- Violations found (field, expected, actual)
- Missing unit documentation
- Recommended fixes
- Trust tier status of validated artifacts (PROVISIONAL / CONFIRMED)
