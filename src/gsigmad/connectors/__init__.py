"""Connector exports and factory helpers for gsigmad."""
from __future__ import annotations

from pathlib import Path

from gsigmad.connectors.flat_file import FlatFileConnector
from gsigmad.connectors.protocol import ConnectorProtocol


def get_connector(project_path: Path | None = None) -> ConnectorProtocol:
    """Resolve the active connector for a project.

    Phase 03 defaults to the offline flat-file backend. Future phases may use
    config-driven selection here when MCP connectors are added.
    """
    root = (project_path or Path.cwd()).resolve()
    return FlatFileConnector(root_path=root)


__all__ = ["ConnectorProtocol", "FlatFileConnector", "get_connector"]
