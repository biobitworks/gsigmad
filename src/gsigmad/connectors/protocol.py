"""Storage backend protocol for gsigmad governance data."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class ConnectorProtocol(Protocol):
    """Contract that all gsigmad storage backends must satisfy."""

    def initialize(self, project_path: Path, config: dict) -> None:
        """Create storage structure and project-scoped governance files."""

    def save_experiment(self, exp_id: str, record: dict) -> Path:
        """Persist an experiment record and return its path."""

    def load_experiment(self, exp_id: str) -> dict:
        """Load an experiment record by ID or raise KeyError if missing."""

    def list_experiments(self) -> list[dict]:
        """Return all experiment records sorted by EXP file order."""

    def append_ledger_entry(self, entry: dict) -> None:
        """Append one ledger record to the append-only governance log."""

    def load_ledger_entries(self) -> list[dict]:
        """Load all append-only ledger records in storage order."""

    def load_config(self) -> dict:
        """Load the project config for the active backend."""
