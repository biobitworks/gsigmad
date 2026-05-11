"""Compliance coverage for the offline FlatFileConnector."""
from __future__ import annotations

from pathlib import Path

from gsigmad.connectors.flat_file import FlatFileConnector
from tests.connectors.compliance import ConnectorComplianceSuite


class TestFlatFileConnector(ConnectorComplianceSuite):
    """Run the shared compliance suite against FlatFileConnector."""

    def make_connector(self, tmp_path: Path) -> FlatFileConnector:
        return FlatFileConnector(root_path=tmp_path)
