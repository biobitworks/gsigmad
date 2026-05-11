"""Tests for gsigmad register command (CLI-02)."""
import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from gsigmad.cli import app

runner = CliRunner()


def _init_project(path: Path) -> None:
    """Helper: initialize a gsigmad project at path."""
    result = runner.invoke(app, ["init", str(path)])
    assert result.exit_code == 0, f"init failed: {result.output}"


def _enable_anchor_opt_in(project_root: Path) -> None:
    config_path = project_root / ".gsigmad" / "config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["anchor_schema_version"] = 1
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def _write_anchor_file(project_root: Path, *, valid: bool = True) -> Path:
    anchors_path = project_root / "contracts" / "anchors" / "exp-anchors.yaml"
    anchors_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_name": "gsigmad-anchor-pack",
        "schema_version": 1,
        "anchors": [
            {
                "anchor_type": "paper",
                "anchor_id": "paper-main",
                "title": "Main paper",
                "doi": "10.1000/main-paper" if valid else None,
                "source_path": "papers/main.pdf",
            }
        ],
    }
    anchors_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return anchors_path


def test_register_creates_exp(tmp_path: Path, monkeypatch):
    """gsigmad register --type exploratory creates EXP-1.1.yaml in .gsigmad/experiments/."""
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["register", "--type", "exploratory"], catch_exceptions=False)
    assert result.exit_code == 0, f"stdout: {result.output}"
    exp_file = tmp_path / ".gsigmad" / "experiments" / "EXP-1.1.yaml"
    assert exp_file.is_file(), f"Expected {exp_file} to exist"


def test_register_sequential_ids(tmp_path: Path, monkeypatch):
    """Two register calls create EXP-1.1.yaml and EXP-1.2.yaml."""
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["register", "--type", "exploratory"], catch_exceptions=False)
    runner.invoke(app, ["register", "--type", "exploratory"], catch_exceptions=False)

    exps_dir = tmp_path / ".gsigmad" / "experiments"
    assert (exps_dir / "EXP-1.1.yaml").is_file()
    assert (exps_dir / "EXP-1.2.yaml").is_file()


def test_register_types(tmp_path: Path, monkeypatch):
    """--type confirmatory and --type replication set classification field correctly."""
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    runner.invoke(app, ["register", "--type", "confirmatory"], catch_exceptions=False)
    exp1 = yaml.safe_load((tmp_path / ".gsigmad" / "experiments" / "EXP-1.1.yaml").read_text())
    assert exp1["classification"] == "CONFIRMATORY"

    runner.invoke(app, ["register", "--type", "replication"], catch_exceptions=False)
    exp2 = yaml.safe_load((tmp_path / ".gsigmad" / "experiments" / "EXP-1.2.yaml").read_text())
    assert exp2["classification"] == "REPLICATION"


def test_register_with_hypothesis(tmp_path: Path, monkeypatch):
    """--hypothesis flag populates hypothesis.h0 field in YAML."""
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner.invoke(
        app,
        ["register", "--type", "exploratory", "--hypothesis", "H0: no effect"],
        catch_exceptions=False,
    )
    exp = yaml.safe_load((tmp_path / ".gsigmad" / "experiments" / "EXP-1.1.yaml").read_text())
    assert exp["hypothesis"]["h0"] == "H0: no effect"


def test_register_template_fields(tmp_path: Path, monkeypatch):
    """Created YAML contains hypothesis, power_analysis, gates, claims blocks."""
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["register", "--type", "confirmatory"], catch_exceptions=False)
    exp = yaml.safe_load((tmp_path / ".gsigmad" / "experiments" / "EXP-1.1.yaml").read_text())

    assert "hypothesis" in exp
    assert "power_analysis" in exp
    assert "gates" in exp
    assert "claims" in exp


def test_register_requires_init(tmp_path: Path, monkeypatch):
    """register fails with exit code 1 if .gsigmad/ does not exist."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["register", "--type", "exploratory"])
    assert result.exit_code == 1


def test_register_json_output(tmp_path: Path, monkeypatch):
    """--json flag returns valid JSON with exp_id and path fields."""
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app, ["--json", "register", "--type", "exploratory"], catch_exceptions=False,
    )
    assert result.exit_code == 0, f"stdout: {result.output}"
    data = json.loads(result.output)
    assert "exp_id" in data
    assert "path" in data


def test_register_records_prompt_artifact(tmp_path: Path, monkeypatch):
    """register stores a governed prompt artifact with deterministic hash metadata."""
    _init_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        ["register", "--type", "exploratory", "--hypothesis", "H0: no effect"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output

    exp = yaml.safe_load((tmp_path / ".gsigmad" / "experiments" / "EXP-1.1.yaml").read_text())
    artifact = exp["prompt_artifact"]
    assert artifact["hash_standard"] == "RFC8785"
    assert artifact["hash_algorithm"] == "sha256"
    assert artifact["hash"]
    assert exp["prompt_id"].startswith("PROMPT-1.")
    assert exp["task_id"].startswith("TASK-1.")
    assert exp["coordinate_version"].startswith("v")


def test_register_persists_anchor_pointer_only_for_opted_in_projects(tmp_path: Path, monkeypatch):
    """Opted-in projects persist validated anchor pointer metadata without inlining anchor content."""
    _init_project(tmp_path)
    _enable_anchor_opt_in(tmp_path)
    anchors_path = _write_anchor_file(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "--json",
            "register",
            "--type",
            "exploratory",
            "--anchors-file",
            str(anchors_path.relative_to(tmp_path)),
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output

    payload = json.loads(result.output)
    exp = yaml.safe_load((tmp_path / ".gsigmad" / "experiments" / f"{payload['exp_id']}.yaml").read_text())

    assert exp["anchor_schema_version"] == 1
    assert exp["anchors_file"] == "contracts/anchors/exp-anchors.yaml"
    assert "anchors" not in exp


def test_register_rejects_malformed_anchor_file_for_opted_in_projects(tmp_path: Path, monkeypatch):
    """Malformed anchor payloads fail before EXP persistence when the project opts in."""
    _init_project(tmp_path)
    _enable_anchor_opt_in(tmp_path)
    anchors_path = _write_anchor_file(tmp_path, valid=False)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "--json",
            "register",
            "--type",
            "exploratory",
            "--anchors-file",
            str(anchors_path.relative_to(tmp_path)),
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 1
    assert "anchor" in result.output.lower()
    assert not list((tmp_path / ".gsigmad" / "experiments").glob("EXP-*.yaml"))
