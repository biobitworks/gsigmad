"""Tests for gsigmad serve CLI command."""
from __future__ import annotations

from click import unstyle
from typer.testing import CliRunner

from gsigmad.cli import app

runner = CliRunner()


def test_serve_command_exists():
    """gsigmad serve is a registered command."""
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    output = unstyle(result.output)
    assert "transport" in output.lower()


def test_serve_help_shows_transport_flag():
    """serve --help shows --transport and --port options."""
    result = runner.invoke(app, ["serve", "--help"])
    output = unstyle(result.output)
    assert "--transport" in output
    assert "--port" in output


def test_serve_help_shows_stdio_default():
    """serve --help indicates stdio is the default transport."""
    result = runner.invoke(app, ["serve", "--help"])
    output = unstyle(result.output)
    assert "stdio" in output.lower()
