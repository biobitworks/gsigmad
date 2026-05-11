"""Tests for gsigmad serve CLI command."""
from __future__ import annotations

from typer.testing import CliRunner

from gsigmad.cli import app

runner = CliRunner()


def test_serve_command_exists():
    """gsigmad serve is a registered command."""
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    assert "transport" in result.output.lower()


def test_serve_help_shows_transport_flag():
    """serve --help shows --transport and --port options."""
    result = runner.invoke(app, ["serve", "--help"])
    assert "--transport" in result.output
    assert "--port" in result.output


def test_serve_help_shows_stdio_default():
    """serve --help indicates stdio is the default transport."""
    result = runner.invoke(app, ["serve", "--help"])
    assert "stdio" in result.output.lower()
