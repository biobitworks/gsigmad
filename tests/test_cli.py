"""Tests for gsigmad CLI entry points (CLI-06)."""
from typer.testing import CliRunner
from gsigmad.cli import app

runner = CliRunner()


def test_version_flag():
    """gsigmad --version shows package version."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "gsigmad" in result.output
    assert "1.2.0b1" in result.output


def test_version_command():
    """gsigmad version shows package + coordinate version."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "1.2.0b1" in result.output
    assert "coordinate" in result.output.lower()
    assert "not yet assigned" not in result.output.lower()


def test_help():
    """gsigmad --help shows help with command list."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Science governance CLI" in result.output or "governance" in result.output.lower()
    assert "version" in result.output.lower()


def test_no_args_shows_help():
    """gsigmad with no args shows help (no_args_is_help=True)."""
    result = runner.invoke(app, [])
    # Typer/click no_args_is_help exits 0 or 2 depending on version
    assert result.exit_code in (0, 2)
    assert "--help" in result.output or "Usage" in result.output
