"""Tests for gsigmad classify command."""
import json
from pathlib import Path

from typer.testing import CliRunner

from gsigmad.cli import app

runner = CliRunner()


def test_classify_measured_json_output():
    result = runner.invoke(
        app,
        ["--json", "classify", "Treatment improved outcome. Cohen's d = 0.5 (95% CI: [0.2, 0.8])."],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["classification"] == "MEASURED"


def test_classify_hypothesis_from_file(tmp_path: Path):
    claim_file = tmp_path / "claim.txt"
    claim_file.write_text("We hypothesize this mutation may improve fitness.", encoding="utf-8")
    result = runner.invoke(app, ["classify", "--file", str(claim_file)], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "HYPOTHESIS" in result.output


def test_classify_requires_input():
    result = runner.invoke(app, ["classify"], catch_exceptions=False)
    assert result.exit_code == 1, result.output
