"""Tests for data contract blocking pre-flight gate — EXP-01."""
import pytest


@pytest.mark.xfail(strict=False, reason="data contract gate not yet implemented")
def test_blocking_preflight():
    """Data contract violation must HALT experiment execution."""
    from gsigmad.governance.gates.data_contract import validate_data_contract
    contract = {
        "interface": "module_A -> module_B",
        "fields": [
            {"name": "gene_id", "type": "str", "required": True},
            {"name": "expression", "type": "float", "unit": "TPM", "required": True},
        ]
    }
    # Data missing required field 'expression'
    data = {"gene_id": "BRCA1"}
    result = validate_data_contract(contract, data)
    assert result["valid"] is False
    assert len(result["violations"]) > 0
    assert "DATA CONTRACT VIOLATION" in result["halt_message"]


@pytest.mark.xfail(strict=False, reason="data contract gate not yet implemented")
def test_passing_contract():
    """Valid data satisfying contract must pass."""
    from gsigmad.governance.gates.data_contract import validate_data_contract
    contract = {
        "interface": "module_A -> module_B",
        "fields": [
            {"name": "gene_id", "type": "str", "required": True},
            {"name": "expression", "type": "float", "unit": "TPM", "required": True},
        ]
    }
    data = {"gene_id": "BRCA1", "expression": 42.5}
    result = validate_data_contract(contract, data)
    assert result["valid"] is True
    assert result["violations"] == []
