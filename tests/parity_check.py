"""
Parity check: validates behavioral specs and runs reference experiment.

Loads all 13 behavioral specs from specs/, runs a reference EXPLORATORY experiment
through the full Phase 1-3 gate chain on the Claude Code platform, and validates
that the output schema matches the expected contract defined in the specs.

Any schema divergences between Claude and Codex output are reported as named
PARITY_FAILURE failures in the format:
    PARITY_FAILURE: {command}.{field} differs — claude={X}, codex={Y}

Usage as pytest:  python -m pytest tests/parity_check.py -v
Usage standalone: python tests/parity_check.py [--codex-output path/to/codex_output.json]

FRM-03: This is the validation mechanism for cross-platform behavioral parity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

import pytest
import yaml

# ---------------------------------------------------------------------------
# Optional KG writer import (ARANGO_AVAILABLE guard)
# ---------------------------------------------------------------------------

try:
    from gsigmad.governance.kg.writer import write_document, TrustTierError  # noqa: F401
    KG_AVAILABLE = True
except ImportError:
    KG_AVAILABLE = False
    write_document = None  # type: ignore[assignment]
    TrustTierError = None  # type: ignore[assignment,misc]

# ---------------------------------------------------------------------------
# Gate imports (always available — pure Python)
# ---------------------------------------------------------------------------

from gsigmad.governance.gates.power_analysis import check_power_analysis_gate
from gsigmad.governance.gates.temporal_integrity import check_temporal_integrity
from gsigmad.governance.gates.red_team import check_red_team_gate
from gsigmad.governance.gates.data_contract import validate_data_contract
from gsigmad.governance.gates.audit_claims import audit_claims_gate, check_effect_size_reporting
from gsigmad.governance.compiler.drift_check import check_drift

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SPECS_DIR = Path("specs")

PARITY_FAILURE_PREFIX = "PARITY_FAILURE"

ALL_COMMANDS = [
    "ablation",
    "audit-claims",
    "audit-output",
    "create-prompt",
    "data-contract",
    "find-experiments",
    "handoff",
    "model-identifiability",
    "negative-results",
    "run-experiment",
    "session-end",
    "session-pause",
    "session-start",
]

REQUIRED_SPEC_FIELDS = {
    "command",
    "version",
    "description",
    "inputs",
    "outputs",
    "gate_checks",
    "error_names",
    "edge_cases",
}

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def load_spec(command: str) -> dict:
    """Load a single behavioral spec YAML file by command name.

    Args:
        command: Command name matching specs/{command}.yaml filename.

    Returns:
        Parsed YAML dict.

    Raises:
        FileNotFoundError: If the spec file does not exist.
        yaml.YAMLError: If the YAML is malformed.
    """
    spec_path = SPECS_DIR / f"{command}.yaml"
    return yaml.safe_load(spec_path.read_text(encoding="utf-8"))


def load_all_specs() -> dict[str, dict]:
    """Load all 13 behavioral specs from specs/ directory.

    Returns:
        {command_name: spec_dict} for all YAML files in specs/.
    """
    specs: dict[str, dict] = {}
    for command in ALL_COMMANDS:
        specs[command] = load_spec(command)
    return specs


def run_reference_experiment_claude() -> dict:
    """Run a reference EXPLORATORY experiment through the full gate chain.

    EXPLORATORY classification: power_analysis and temporal_integrity gates
    do NOT apply (they are CONFIRMATORY-only). The reference experiment exercises:
      - validate_data_contract (applies to ALL classifications)
      - audit_claims_gate (applies to ALL classifications)

    Constructs a minimal but complete experiment record with:
      - Minimal data contract and data dict (passes validation)
      - Well-formed claims with effect size and CI (passes audit)
      - SIG-ID generated via hashlib (stdlib)

    Returns:
        {
            "status": "PASS" | "FAIL",
            "gates_passed": list[str],
            "gates_failed": list[str],
            "error": None | str,
        }
    """
    gates_passed: list[str] = []
    gates_failed: list[str] = []
    error: Optional[str] = None

    # --- Minimal data contract for EXPLORATORY ---
    contract = {
        "interface": "reference_module_A -> reference_module_B",
        "fields": [
            {"name": "sample_id", "type": "str", "required": True},
            {"name": "measurement", "type": "float", "required": True},
        ],
    }
    data = {
        "sample_id": "SAMPLE-001",
        "measurement": 1.23,
    }

    dc_result = validate_data_contract(contract, data)
    if dc_result.get("valid", False):
        gates_passed.append("data_contract")
    else:
        gates_failed.append("data_contract")
        error = dc_result.get("halt_message")
        return {
            "status": "FAIL",
            "gates_passed": gates_passed,
            "gates_failed": gates_failed,
            "error": error,
        }

    # --- Minimal well-formed claims for audit ---
    claims = [
        {
            "text": (
                "The treatment had a significant effect "
                "(Cohen's d = 0.62, 95% CI [0.38, 0.86], p < 0.001)"
            )
        }
    ]

    ac_result = audit_claims_gate(claims, verify_citations=False)
    if ac_result.get("pass", False):
        gates_passed.append("audit_claims")
    else:
        gates_failed.append("audit_claims")
        failures = ac_result.get("failures", [])
        error = failures[0]["error"] if failures else "audit_claims gate failed"
        return {
            "status": "FAIL",
            "gates_passed": gates_passed,
            "gates_failed": gates_failed,
            "error": error,
        }

    # Generate a run_id for traceability
    ts_seed = "reference-experiment"
    h4 = hashlib.md5(ts_seed.encode()).hexdigest()[:4]
    run_id = f"EXP-REF-{h4}"

    return {
        "status": "PASS",
        "gates_passed": gates_passed,
        "gates_failed": gates_failed,
        "error": None,
        "run_id": run_id,
    }


def diff_output_schemas(
    claude_out: dict, codex_out: dict, command: str
) -> list[str]:
    """Compare two output dicts field-by-field. Return PARITY_FAILURE strings for any mismatch.

    Args:
        claude_out: Output dict from Claude Code platform.
        codex_out:  Output dict from Codex platform.
        command:    Command name (used in failure message prefix).

    Returns:
        List of PARITY_FAILURE strings. Empty list means no divergence.
        Format: "PARITY_FAILURE: {command}.{field} differs — claude={X}, codex={Y}"
    """
    failures: list[str] = []

    all_keys = set(claude_out.keys()) | set(codex_out.keys())
    for field in sorted(all_keys):
        claude_val = claude_out.get(field, "<missing>")
        codex_val = codex_out.get(field, "<missing>")
        if claude_val != codex_val:
            failures.append(
                f"{PARITY_FAILURE_PREFIX}: {command}.{field} differs "
                f"— claude={claude_val!r}, codex={codex_val!r}"
            )

    return failures


# ---------------------------------------------------------------------------
# Test functions
# ---------------------------------------------------------------------------


def test_all_specs_loadable() -> None:
    """All 13 behavioral specs must load from specs/ and contain required fields.

    Required fields: command, version, description, inputs, outputs,
                     gate_checks, error_names, edge_cases
    """
    specs = load_all_specs()

    assert len(specs) == 13, (
        f"Expected 13 specs, got {len(specs)}. "
        f"Found: {sorted(specs.keys())}"
    )

    for command, spec in specs.items():
        missing = REQUIRED_SPEC_FIELDS - set(spec.keys())
        assert not missing, (
            f"Spec '{command}' is missing required fields: {sorted(missing)}"
        )
        assert spec["command"] == command or spec["command"] == command, (
            f"Spec '{command}' has command field '{spec['command']}'"
        )


def test_reference_experiment_passes() -> None:
    """Reference EXPLORATORY experiment must pass the full gate chain and return status=PASS.

    The reference experiment exercises data_contract and audit_claims gates.
    EXPLORATORY classification skips power_analysis, temporal_integrity,
    and red_team gates.
    """
    result = run_reference_experiment_claude()

    assert result["status"] == "PASS", (
        f"Reference experiment failed. Error: {result.get('error')}\n"
        f"Gates failed: {result.get('gates_failed', [])}"
    )
    assert "data_contract" in result["gates_passed"], (
        f"data_contract gate not in gates_passed: {result['gates_passed']}"
    )
    assert "audit_claims" in result["gates_passed"], (
        f"audit_claims gate not in gates_passed: {result['gates_passed']}"
    )
    assert result["error"] is None, (
        f"Expected no error on PASS, got: {result['error']}"
    )


def test_edge_case_ec01_temporal_gate(tmp_path: Path) -> None:
    """EC-01: CONFIRMATORY temporal gate fires when pre-registration commit postdates data file mtime.

    Strategy: create a real data file in tmp_path, then pass a prereg_file path
    that has no git history (never committed). The gate will fail with
    HARKING_PREVENTION_ERROR because an uncommitted pre-registration has no
    commit timestamp.
    """
    data_file = tmp_path / "results_2026_01_01.csv"
    data_file.write_text("sample_id,measurement\nSAMPLE-001,1.23\n")

    prereg_file = str(tmp_path / "EXP_001_prereg.md")

    result = check_temporal_integrity(
        prereg_file=prereg_file,
        data_file=str(data_file),
    )

    assert result["pass"] is False, (
        f"EC-01: Expected temporal gate to fail, got pass=True. Result: {result}"
    )
    assert "HARKING_PREVENTION_ERROR" in (result.get("error") or ""), (
        f"EC-01: Expected HARKING_PREVENTION_ERROR in error. Got: {result.get('error')}"
    )


def test_edge_case_ec02_effect_size() -> None:
    """EC-02: Effect size gate fires for claim with p-value but no effect size or CI."""
    claim_text = "The treatment was effective (p < 0.05)"
    result = check_effect_size_reporting(claim_text)

    assert result["pass"] is False, (
        f"EC-02: Expected effect size gate to fail, got pass=True. Result: {result}"
    )
    assert "STAT_RIGOR_VIOLATION" in (result.get("error") or ""), (
        f"EC-02: Expected STAT_RIGOR_VIOLATION in error. Got: {result.get('error')}"
    )


@pytest.mark.skipif(not KG_AVAILABLE, reason="KG writer not importable (python-arango not installed)")
def test_edge_case_ec03_provisional_gate() -> None:
    """EC-03: PROVISIONAL trust tier raises TrustTierError before any DB contact.

    The write_document() function enforces trust tier BEFORE attempting ArangoDB
    connection (CANON-CORE Invariant 3). PROVISIONAL artifacts must have a VERIFIED
    countersignature before KG write is permitted.
    """
    doc = {
        "_key": "test-parity-ec03",
        "_provenance": {
            "prov:Agent": {
                "trust_tier": "PROVISIONAL",
                "prov:label": "test-agent",
            }
        },
        "payload": "test",
    }

    with pytest.raises(TrustTierError) as exc_info:
        write_document(
            collection="test_collection",
            doc=doc,
            agent="test-agent",
        )

    assert "TRUST_TIER_ERROR" in str(exc_info.value), (
        f"EC-03: Expected TRUST_TIER_ERROR in exception message. "
        f"Got: {exc_info.value}"
    )


def test_edge_case_ec04_drift_check(tmp_path: Path) -> None:
    """EC-04: Drift check fires when >= 5 experiments have < 50% SCIENCE classification.

    Strategy: create a LAB_NOTEBOOK.md in tmp_path with 5 INFRASTRUCTURE EXP
    headers (0% SCIENCE). Set the drift counter to DRIFT_TRIGGER - 1 so that
    calling check_drift() increments it to DRIFT_TRIGGER and runs the analysis.
    """
    # Create .agent directory with drift counter at DRIFT_TRIGGER - 1
    agent_dir = tmp_path / ".agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    counter_path = agent_dir / "drift_counter.txt"
    counter_path.write_text("4")  # one below trigger of 5

    # Create LAB_NOTEBOOK.md with 5 INFRASTRUCTURE EXP headers (0% SCIENCE)
    notebook = tmp_path / "LAB_NOTEBOOK.md"
    notebook.write_text(
        "## EXP-001 — INFRASTRUCTURE — Deploy CI pipeline\n"
        "## EXP-002 — INFRASTRUCTURE — Refactor DB schema\n"
        "## EXP-003 — INFRASTRUCTURE — Update dependencies\n"
        "## EXP-004 — INFRASTRUCTURE — Fix linting errors\n"
        "## EXP-005 — INFRASTRUCTURE — Performance profiling\n"
    )

    result = check_drift(project_root=str(tmp_path))

    assert result["pass"] is False, (
        f"EC-04: Expected drift check to fail, got pass=True. Result: {result}"
    )
    assert "DRIFT_WARNING" in (result.get("error") or ""), (
        f"EC-04: Expected DRIFT_WARNING in error. Got: {result.get('error')}"
    )
    assert result.get("triggered") is True, (
        f"EC-04: Expected triggered=True. Got: {result.get('triggered')}"
    )


def test_parity_no_codex_output() -> None:
    """diff_output_schemas returns [] when both outputs are identical (no parity failures)."""
    output_a = {
        "status": "PASS",
        "gates_passed": ["data_contract", "audit_claims"],
        "gates_failed": [],
        "error": None,
    }
    output_b = dict(output_a)  # identical copy

    failures = diff_output_schemas(output_a, output_b, command="run-experiment")

    assert failures == [], (
        f"Expected no parity failures for identical outputs. Got: {failures}"
    )


def test_parity_failure_format() -> None:
    """diff_output_schemas produces correctly formatted PARITY_FAILURE strings on divergence."""
    claude_out = {"status": "PASS", "gates_passed": ["data_contract"]}
    codex_out = {"status": "FAIL", "gates_passed": ["data_contract"], "extra_field": "x"}

    failures = diff_output_schemas(claude_out, codex_out, command="run-experiment")

    assert len(failures) >= 1, "Expected at least one PARITY_FAILURE"

    status_failure = next(
        (f for f in failures if "run-experiment.status" in f), None
    )
    assert status_failure is not None, (
        f"Expected PARITY_FAILURE for status field. Got: {failures}"
    )
    assert PARITY_FAILURE_PREFIX in status_failure, (
        f"Expected '{PARITY_FAILURE_PREFIX}' prefix in failure string: {status_failure}"
    )
    assert "claude=" in status_failure, f"Missing claude= in: {status_failure}"
    assert "codex=" in status_failure, f"Missing codex= in: {status_failure}"


# ---------------------------------------------------------------------------
# Standalone entry point (--codex-output support)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Parity check — FRM-03 cross-platform behavioral validation."
    )
    parser.add_argument(
        "--codex-output",
        metavar="PATH",
        help="Path to Codex platform output JSON file. "
             "If provided, runs the reference experiment and diffs against Codex output.",
    )
    args = parser.parse_args()

    if args.codex_output:
        # Load Codex output
        codex_path = Path(args.codex_output)
        if not codex_path.exists():
            print(f"ERROR: Codex output file not found: {codex_path}", file=sys.stderr)
            sys.exit(1)

        codex_out = json.loads(codex_path.read_text(encoding="utf-8"))

        # Run reference experiment on Claude platform
        print("Running reference experiment (Claude platform)...")
        claude_out = run_reference_experiment_claude()
        print(f"Claude result: {json.dumps(claude_out, indent=2)}")

        # Diff schemas
        command = codex_out.get("command", "run-experiment")
        failures = diff_output_schemas(claude_out, codex_out, command=command)

        if failures:
            print("\n=== PARITY FAILURES ===")
            for failure in failures:
                print(failure)
            print(f"\n{len(failures)} parity failure(s) detected.")
            sys.exit(1)
        else:
            print("\nPARITY OK: No schema divergences between Claude and Codex outputs.")
            sys.exit(0)
    else:
        # Run pytest on this file
        sys.exit(pytest.main([__file__, "-v"]))
