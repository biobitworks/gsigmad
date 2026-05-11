"""Offline flat-file connector for gsigmad storage."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from gsigmad.scaffold.templates import lab_notebook_template


@dataclass
class FlatFileConnector:
    """Persist governance data under `.gsigmad/` using YAML and JSONL."""

    root_path: Path
    _config_cache: dict | None = field(default=None, init=False, repr=False)

    @property
    def gsigmad_dir(self) -> Path:
        return self.root_path / ".gsigmad"

    @property
    def experiments_dir(self) -> Path:
        return self.gsigmad_dir / "experiments"

    @property
    def ledger_dir(self) -> Path:
        return self.gsigmad_dir / "ledger"

    @property
    def config_path(self) -> Path:
        return self.gsigmad_dir / "config.yaml"

    @property
    def notebook_path(self) -> Path:
        return self.gsigmad_dir / "LAB_NOTEBOOK.md"

    @property
    def ledger_file(self) -> Path:
        return self.ledger_dir / "governance.jsonl"

    def initialize(self, project_path: Path, config: dict) -> None:
        """Create the `.gsigmad/` directory structure and baseline files."""
        self.gsigmad_dir.mkdir(parents=True)
        self.experiments_dir.mkdir()
        self.ledger_dir.mkdir()
        self.config_path.write_text(
            yaml.safe_dump(config, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
        self.notebook_path.write_text(lab_notebook_template(), encoding="utf-8")
        self._config_cache = dict(config)

    def save_experiment(self, exp_id: str, record: dict) -> Path:
        """Persist one experiment record using exclusive create semantics."""
        exp_path = self.experiments_dir / f"{exp_id}.yaml"
        with exp_path.open("x", encoding="utf-8") as handle:
            yaml.safe_dump(record, handle, default_flow_style=False, sort_keys=False)
        return exp_path

    def load_experiment(self, exp_id: str) -> dict:
        """Load one experiment record or raise KeyError if it does not exist."""
        exp_path = self.experiments_dir / f"{exp_id}.yaml"
        if not exp_path.is_file():
            raise KeyError(f"Experiment not found: {exp_id}")
        record = yaml.safe_load(exp_path.read_text(encoding="utf-8")) or {}
        if not isinstance(record, dict):
            raise KeyError(f"Experiment record invalid: {exp_id}")
        return record

    def list_experiments(self) -> list[dict]:
        """Return all experiment records sorted by file name."""
        records: list[dict] = []
        for yaml_file in sorted(self.experiments_dir.glob("EXP-*.yaml")):
            record = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
            if isinstance(record, dict):
                records.append(record)
        return records

    def append_ledger_entry(self, entry: dict) -> None:
        """Append one JSONL ledger entry."""
        self.ledger_dir.mkdir(parents=True, exist_ok=True)
        with self.ledger_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def load_ledger_entries(self) -> list[dict]:
        """Load ledger entries from the append-only JSONL file."""
        if not self.ledger_file.is_file():
            return []

        entries: list[dict] = []
        with self.ledger_file.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                entry = json.loads(stripped)
                if not isinstance(entry, dict):
                    raise ValueError(
                        f"Ledger entry on line {line_number} is not a JSON object"
                    )
                entries.append(entry)
        return entries

    def load_config(self) -> dict:
        """Load project config from `.gsigmad/config.yaml`."""
        if self._config_cache is not None:
            return self._config_cache
        config = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(config, dict):
            return {}
        self._config_cache = config
        return config
