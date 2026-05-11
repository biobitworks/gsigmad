"""Tests for W5 ledger append and verification helpers."""
from __future__ import annotations

import json
from pathlib import Path

from gsigmad.connectors import get_connector
from gsigmad.hub.ledger import append_w5, verify_ledger_chain
from gsigmad.scaffold.templates import default_config


def _init_connector(tmp_path: Path):
    connector = get_connector(tmp_path)
    config = default_config()
    config["project_name"] = tmp_path.name
    connector.initialize(tmp_path, config)
    return connector


def test_append_w5_first_entry(tmp_path: Path):
    """First ledger entry has no previous hash and contains W5 fields."""
    _init_connector(tmp_path)

    entry = append_w5(
        tmp_path,
        who={"actor": "tester"},
        what={"command": "init"},
        where={"project_root": str(tmp_path)},
        why={"action": "initialize"},
    )

    assert entry["prev_hash"] is None
    assert entry["hash"]
    assert set(("who", "what", "where", "when", "why")).issubset(entry)


def test_append_w5_links_previous_hash(tmp_path: Path):
    """Second append links to the hash of the first record."""
    _init_connector(tmp_path)

    first = append_w5(
        tmp_path,
        who={"actor": "tester"},
        what={"command": "register"},
        where={"project_root": str(tmp_path), "exp_id": "EXP-1.1"},
        why={"action": "pre_register"},
    )
    second = append_w5(
        tmp_path,
        who={"actor": "tester"},
        what={"command": "run"},
        where={"project_root": str(tmp_path), "exp_id": "EXP-1.1"},
        why={"action": "execute"},
    )

    assert second["prev_hash"] == first["hash"]


def test_verify_ledger_chain_detects_tampering(tmp_path: Path):
    """Chain verification fails after a ledger entry is modified post hoc."""
    connector = _init_connector(tmp_path)
    append_w5(
        tmp_path,
        who={"actor": "tester"},
        what={"command": "register"},
        where={"project_root": str(tmp_path), "exp_id": "EXP-1.1"},
        why={"action": "pre_register"},
    )
    append_w5(
        tmp_path,
        who={"actor": "tester"},
        what={"command": "run"},
        where={"project_root": str(tmp_path), "exp_id": "EXP-1.1"},
        why={"action": "execute"},
    )

    ledger_file = tmp_path / ".gsigmad" / "ledger" / "governance.jsonl"
    entries = connector.load_ledger_entries()
    entries[0]["why"]["action"] = "tampered"
    ledger_file.write_text(
        "\n".join(json.dumps(entry) for entry in entries) + "\n",
        encoding="utf-8",
    )

    result = verify_ledger_chain(tmp_path)
    assert result["pass"] is False
    assert result["error"] == "HASH_MISMATCH"
