"""Role-lane and interaction-provenance contract checks."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def test_role_provenance_contract_declares_replay_loops() -> None:
    repo = Path(__file__).resolve().parent.parent
    contract = (repo / "docs" / "ROLE_AND_PROVENANCE_CONTRACT.md").read_text(encoding="utf-8")

    required = [
        "PI",
        "PM",
        "SWE",
        "Review",
        "Operator",
        "input -> analysis -> interpretation",
        "scope -> sequence -> gate",
        "design -> apply -> verify",
        "input -> analysis -> verdict",
        "request -> approve_or_deny -> receipt",
        "analysis` and `verify` SHOULD be deterministic",
        "Operator approval is intentionally not deterministic",
    ]
    for needle in required:
        assert needle in contract


def test_interaction_receipt_matches_contract_hash_and_slug() -> None:
    repo = Path(__file__).resolve().parent.parent
    contract_path = repo / "docs" / "ROLE_AND_PROVENANCE_CONTRACT.md"
    contract_hash = hashlib.sha256(contract_path.read_bytes()).hexdigest()

    receipts = sorted((repo / "examples" / "interaction_receipts").glob("*.json"))
    assert receipts

    receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert receipt["artifact_path"] == "gsigmad/docs/ROLE_AND_PROVENANCE_CONTRACT.md"
    assert receipt["content_hash"] == f"sha256:{contract_hash}"
    assert receipt["slug"].endswith(contract_hash[:8])
    assert receipts[0].stem == receipt["slug"]
    assert receipt["determinism_note"] == "deterministic"
    assert receipt["role_loop"] == "design -> apply -> verify"
    assert receipt["role_input"]
    assert "input -> analysis -> output" in receipt["role_analysis"]
    assert receipt["role_output"] == receipt["artifact_path"]
    assert receipt["role_header"]["writeback_disposition"] == "blocked"
    assert receipt["role_header"]["claim_ceiling"] == "GOVERNANCE_ONLY"
