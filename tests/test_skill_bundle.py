"""Tests for bundled skill installation."""
from pathlib import Path

from typer.testing import CliRunner

from gsigmad.cli import app

runner = CliRunner()


def test_init_installs_bundled_skills(tmp_path: Path):
    result = runner.invoke(app, ["init", str(tmp_path)], catch_exceptions=False)
    assert result.exit_code == 0, result.output

    # Fixed paths: skill dirs are gsigmad-export, not gsigmad/export (Pitfall 7)
    assert (tmp_path / ".claude" / "skills" / "gsigmad-export" / "SKILL.md").is_file()
    assert (tmp_path / ".agents" / "skills" / "gsigmad-fair-check" / "SKILL.md").is_file()


def test_openai_yaml_in_all_skills(tmp_path: Path):
    """SCAFFOLD-03: Every bundled skill has agents/openai.yaml sidecar."""
    skills_dir = Path(__file__).resolve().parent.parent / "src" / "gsigmad" / "skill_bundle" / "skills"
    skill_dirs = [
        d for d in skills_dir.iterdir()
        if d.is_dir() and d.name.startswith("gsigmad-")
    ]
    assert len(skill_dirs) >= 30, (
        f"Expected at least 30 public gsigmad-* skills in bundled source, found {len(skill_dirs)}"
    )
    for skill_dir in skill_dirs:
        yaml_path = skill_dir / "agents" / "openai.yaml"
        assert yaml_path.is_file(), (
            f"Missing agents/openai.yaml in {skill_dir.name}"
        )


def test_upgrade_refreshes_bundled_skills(tmp_path: Path):
    """Upgrade path refreshes bundled skills so retrofit policy changes land in old projects."""
    result = runner.invoke(app, ["init", str(tmp_path)], catch_exceptions=False)
    assert result.exit_code == 0, result.output

    skill_path = tmp_path / ".claude" / "skills" / "gsigmad-handoff" / "SKILL.md"
    skill_path.write_text("stale skill\n", encoding="utf-8")

    config_path = tmp_path / ".gsigmad" / "config.yaml"
    import yaml

    config = yaml.safe_load(config_path.read_text())
    config["schema_version"] = 2
    config_path.write_text(yaml.safe_dump(config, default_flow_style=False, sort_keys=False))

    result = runner.invoke(app, ["init", "--yes", str(tmp_path)], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    refreshed = skill_path.read_text(encoding="utf-8")
    assert "Ollarma continuation" in refreshed


# SCAFFOLD-06: Shell completions are provided by typer built-in --install-completion.
# No code changes needed. Typer natively handles bash/zsh/fish completions.
