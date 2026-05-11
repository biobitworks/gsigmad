"""Tests for gsigmad init command (CLI-01) + scaffold + upgrade (SCAFFOLD-01/02)."""
import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from gsigmad.cli import app

runner = CliRunner()


# ---- Original tests (unchanged) ----


def test_init_creates_gsigmad_dir(tmp_path: Path):
    """gsigmad init creates .gsigmad/ with config.yaml, experiments/, ledger/, LAB_NOTEBOOK.md."""
    result = runner.invoke(app, ["init", str(tmp_path)])
    assert result.exit_code == 0, f"stdout: {result.output}"

    gsigmad_dir = tmp_path / ".gsigmad"
    assert gsigmad_dir.is_dir()
    assert (gsigmad_dir / "config.yaml").is_file()
    assert (gsigmad_dir / "experiments").is_dir()
    assert (gsigmad_dir / "ledger").is_dir()
    assert (gsigmad_dir / "LAB_NOTEBOOK.md").is_file()


def test_init_creates_canon(tmp_path: Path):
    """gsigmad init creates CANON.md in the project root."""
    result = runner.invoke(app, ["init", str(tmp_path)])
    assert result.exit_code == 0, f"stdout: {result.output}"
    assert (tmp_path / "CANON.md").is_file()


def test_init_json_output(tmp_path: Path):
    """gsigmad --json init returns valid JSON with initialized: true."""
    result = runner.invoke(app, ["--json", "init", str(tmp_path)])
    assert result.exit_code == 0, f"stdout: {result.output}"
    data = json.loads(result.output)
    assert data["initialized"] is True


def test_init_config_yaml_contents(tmp_path: Path):
    """config.yaml has project_name, created_at, governance keys."""
    runner.invoke(app, ["init", str(tmp_path)])
    config_path = tmp_path / ".gsigmad" / "config.yaml"
    config = yaml.safe_load(config_path.read_text())

    assert "project_name" in config
    assert "created_at" in config
    assert "governance" in config
    assert "canon_path" in config["governance"]
    assert "experiment_dir" in config["governance"]
    assert "ledger_dir" in config["governance"]


# ---- New scaffold tests (SCAFFOLD-01) ----


def test_init_scaffolds_working_tree(tmp_path: Path):
    """Fresh init creates all scaffold files that skills and downstream phases expect."""
    result = runner.invoke(app, ["init", str(tmp_path)])
    assert result.exit_code == 0, result.output

    # All 15 directories
    for d in [
        "prompts",
        "experiments",
        "experiments/reviews",
        "experiments/fair",
        "experiments/pre-reg",
        "results",
        "scripts",
        ".agent",
        ".agent/conversation_digests",
        ".agent/drift_reports",
        ".agent/locks",
        "contracts",
        "notebooks",
        "null_models",
        "calibration",
    ]:
        assert (tmp_path / d).is_dir(), f"Missing directory: {d}"

    # All scaffold files
    assert (tmp_path / "PROMPT_EXP_MAP.md").is_file()
    assert (tmp_path / ".agent" / "task.md").is_file()
    assert (tmp_path / ".agent" / "MISSION_ANCHOR.md").is_file()
    assert (tmp_path / ".agent" / "OLLARMA_CONTINUATION.md").is_file()
    assert (tmp_path / ".agent" / "next_prompt.txt").is_file()
    assert (tmp_path / ".agent" / "next_exp.txt").is_file()
    assert (tmp_path / ".agent" / "registered_reports.json").is_file()
    task_text = (tmp_path / ".agent" / "task.md").read_text(encoding="utf-8")
    assert "## Ollarma Continuation" in task_text
    assert "Suitable: no" in task_text
    assert (tmp_path / "experiments" / "NEGATIVE_RESULTS_REGISTRY.md").is_file()
    assert (tmp_path / "LAB_NOTEBOOK.md").is_file()

    # registered_reports.json is valid empty JSON object (keyed by EXP id)
    rr = json.loads((tmp_path / ".agent" / "registered_reports.json").read_text())
    assert rr == {}


def test_init_scaffold_idempotent(tmp_path: Path):
    """Re-scaffolding does NOT overwrite user files."""
    # First init
    result = runner.invoke(app, ["init", str(tmp_path)])
    assert result.exit_code == 0, result.output

    # Write custom content to .agent/task.md
    custom = "# My custom task content"
    (tmp_path / ".agent" / "task.md").write_text(custom, encoding="utf-8")

    # Re-init (upgrade path) -- need to set schema to 1 to trigger upgrade
    config_path = tmp_path / ".gsigmad" / "config.yaml"
    config = yaml.safe_load(config_path.read_text())
    config["schema_version"] = 1
    config_path.write_text(yaml.safe_dump(config, default_flow_style=False, sort_keys=False))

    result = runner.invoke(app, ["init", "--yes", str(tmp_path)])
    assert result.exit_code == 0, result.output

    # Custom content preserved
    assert (tmp_path / ".agent" / "task.md").read_text(encoding="utf-8") == custom


def test_init_upgrade_existing_project(tmp_path: Path):
    """Upgrade older schema creates new scaffold files and updates schema_version."""
    # Fresh init (creates schema 2)
    result = runner.invoke(app, ["init", str(tmp_path)])
    assert result.exit_code == 0, result.output

    # Manually downgrade to schema 1
    config_path = tmp_path / ".gsigmad" / "config.yaml"
    config = yaml.safe_load(config_path.read_text())
    config["schema_version"] = 1
    config_path.write_text(yaml.safe_dump(config, default_flow_style=False, sort_keys=False))

    # Run upgrade
    result = runner.invoke(app, ["init", "--yes", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "upgrading" in result.output.lower() or "upgrade" in result.output.lower()

    # schema_version updated
    config = yaml.safe_load(config_path.read_text())
    assert config["schema_version"] == 3
    assert (tmp_path / ".agent" / "OLLARMA_CONTINUATION.md").is_file()


def test_init_already_current(tmp_path: Path):
    """Second init with current schema returns exit 0 with 'already' in output."""
    result = runner.invoke(app, ["init", str(tmp_path)])
    assert result.exit_code == 0, result.output

    # Second init -- already current
    result = runner.invoke(app, ["init", "--yes", str(tmp_path)])
    assert result.exit_code == 0
    assert "already" in result.output.lower()


def test_init_json_upgrade_diff(tmp_path: Path):
    """--json output for upgrade includes created and skipped lists."""
    # Fresh init
    runner.invoke(app, ["init", str(tmp_path)])

    # Downgrade
    config_path = tmp_path / ".gsigmad" / "config.yaml"
    config = yaml.safe_load(config_path.read_text())
    config["schema_version"] = 1
    config_path.write_text(yaml.safe_dump(config, default_flow_style=False, sort_keys=False))

    # Upgrade with JSON output
    result = runner.invoke(app, ["--json", "init", "--yes", str(tmp_path)])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert "created" in data
    assert "skipped" in data


def test_init_config_has_schema_version(tmp_path: Path):
    """Fresh init produces config.yaml with current schema version."""
    runner.invoke(app, ["init", str(tmp_path)])
    config_path = tmp_path / ".gsigmad" / "config.yaml"
    config = yaml.safe_load(config_path.read_text())
    assert config["schema_version"] == 3


def test_init_banner_new_project(tmp_path: Path):
    """Fresh init shows 'Initializing new project' banner."""
    result = runner.invoke(app, ["init", str(tmp_path)])
    assert result.exit_code == 0
    assert "initializing" in result.output.lower() or "initialized" in result.output.lower()


def test_init_banner_upgrade(tmp_path: Path):
    """Upgrade shows 'Upgrading existing project' banner."""
    runner.invoke(app, ["init", str(tmp_path)])

    # Downgrade
    config_path = tmp_path / ".gsigmad" / "config.yaml"
    config = yaml.safe_load(config_path.read_text())
    config["schema_version"] = 1
    config_path.write_text(yaml.safe_dump(config, default_flow_style=False, sort_keys=False))

    result = runner.invoke(app, ["init", "--yes", str(tmp_path)])
    assert result.exit_code == 0
    assert "upgrading" in result.output.lower() or "upgrade" in result.output.lower()


# SCAFFOLD-06: Shell completions are provided by typer built-in --install-completion.
# No code changes needed. Typer natively handles bash/zsh/fish completions.
