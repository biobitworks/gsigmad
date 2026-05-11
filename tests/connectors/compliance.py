"""Shared compliance tests for gsigmad connector implementations."""
from __future__ import annotations

from pathlib import Path

import pytest

from gsigmad.connectors.protocol import ConnectorProtocol


class ConnectorComplianceSuite:
    """Shared expectations every connector implementation must satisfy."""

    def make_connector(self, tmp_path: Path) -> ConnectorProtocol:
        """Create a connector instance rooted at tmp_path."""
        raise NotImplementedError

    def initialize_connector(self, tmp_path: Path) -> ConnectorProtocol:
        """Create and initialize a connector for the temporary project."""
        connector = self.make_connector(tmp_path)
        connector.initialize(
            tmp_path,
            {
                "project_name": tmp_path.name,
                "created_at": "2026-01-01T00:00:00+00:00",
                "connector_type": "flat_file",
                "governance": {
                    "canon_path": "CANON.md",
                    "experiment_dir": ".gsigmad/experiments",
                    "ledger_dir": ".gsigmad/ledger",
                },
            },
        )
        return connector

    def test_isinstance_protocol(self, tmp_path: Path):
        connector = self.make_connector(tmp_path)
        assert isinstance(connector, ConnectorProtocol)

    def test_initialize_creates_storage(self, tmp_path: Path):
        connector = self.initialize_connector(tmp_path)
        assert (tmp_path / ".gsigmad").is_dir()
        assert connector.load_config()["project_name"] == tmp_path.name
        assert (tmp_path / ".gsigmad" / "LAB_NOTEBOOK.md").is_file()

    def test_save_and_load_experiment(self, tmp_path: Path):
        connector = self.initialize_connector(tmp_path)
        record = {"exp_id": "EXP-1.1", "classification": "EXPLORATORY", "claims": []}
        connector.save_experiment("EXP-1.1", record)
        loaded = connector.load_experiment("EXP-1.1")
        assert loaded["exp_id"] == "EXP-1.1"
        assert loaded["classification"] == "EXPLORATORY"

    def test_load_missing_experiment_raises_keyerror(self, tmp_path: Path):
        connector = self.initialize_connector(tmp_path)
        with pytest.raises(KeyError):
            connector.load_experiment("EXP-999.1")

    def test_list_experiments(self, tmp_path: Path):
        connector = self.initialize_connector(tmp_path)
        connector.save_experiment("EXP-1.1", {"exp_id": "EXP-1.1"})
        connector.save_experiment("EXP-1.2", {"exp_id": "EXP-1.2"})
        experiments = connector.list_experiments()
        assert [exp["exp_id"] for exp in experiments] == ["EXP-1.1", "EXP-1.2"]

    def test_append_ledger_entry(self, tmp_path: Path):
        connector = self.initialize_connector(tmp_path)
        connector.append_ledger_entry({"action": "register", "exp_id": "EXP-1.1"})
        ledger_file = tmp_path / ".gsigmad" / "ledger" / "governance.jsonl"
        assert ledger_file.is_file()
        assert '"action": "register"' in ledger_file.read_text(encoding="utf-8")

    def test_load_ledger_entries(self, tmp_path: Path):
        connector = self.initialize_connector(tmp_path)
        connector.append_ledger_entry({"action": "register", "exp_id": "EXP-1.1"})
        entries = connector.load_ledger_entries()
        assert entries == [{"action": "register", "exp_id": "EXP-1.1"}]
