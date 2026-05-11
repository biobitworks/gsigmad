"""Tests for gsigmad power command (CLI-07)."""
import json
from pathlib import Path

from typer.testing import CliRunner

from gsigmad.cli import app

runner = CliRunner()


def test_power_ttest(tmp_path: Path, monkeypatch):
    """gsigmad power --test ttest_ind --effect-size 0.4 outputs required N and achieved power."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["power", "--test", "ttest_ind", "--effect-size", "0.4"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, f"stdout: {result.output}"
    # Should show required N somewhere in output
    assert "Required N" in result.output or "required_n" in result.output


def test_power_ttest_paired(tmp_path: Path, monkeypatch):
    """gsigmad power --test ttest_paired --effect-size 0.5 outputs required N."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["power", "--test", "ttest_paired", "--effect-size", "0.5"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, f"stdout: {result.output}"


def test_power_anova(tmp_path: Path, monkeypatch):
    """gsigmad power --test anova --effect-size 0.25 --n-groups 3 outputs required N."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["power", "--test", "anova", "--effect-size", "0.25", "--n-groups", "3"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, f"stdout: {result.output}"


def test_power_chi2(tmp_path: Path, monkeypatch):
    """gsigmad power --test chi2 --effect-size 0.3 outputs required N."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["power", "--test", "chi2", "--effect-size", "0.3"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, f"stdout: {result.output}"


def test_power_correlation(tmp_path: Path, monkeypatch):
    """gsigmad power --test correlation --effect-size 0.3 outputs required N."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["power", "--test", "correlation", "--effect-size", "0.3"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, f"stdout: {result.output}"


def test_power_proportion(tmp_path: Path, monkeypatch):
    """gsigmad power --test proportion --effect-size 0.3 outputs required N."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["power", "--test", "proportion", "--effect-size", "0.3"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, f"stdout: {result.output}"


def test_power_custom_alpha(tmp_path: Path, monkeypatch):
    """gsigmad power --test ttest_ind --effect-size 0.5 --alpha 0.01 uses alpha=0.01."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["power", "--test", "ttest_ind", "--effect-size", "0.5", "--alpha", "0.01"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, f"stdout: {result.output}"
    # Should mention alpha 0.01 somewhere
    assert "0.01" in result.output


def test_power_custom_target(tmp_path: Path, monkeypatch):
    """gsigmad power --test ttest_ind --effect-size 0.5 --power 0.90 uses power_target=0.90."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["power", "--test", "ttest_ind", "--effect-size", "0.5", "--power", "0.90"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, f"stdout: {result.output}"
    assert "0.9" in result.output


def test_power_json_output(tmp_path: Path, monkeypatch):
    """--json produces valid JSON with required_n, achieved_power, test_type fields."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["--json", "power", "--test", "ttest_ind", "--effect-size", "0.4"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, f"stdout: {result.output}"
    data = json.loads(result.output)
    assert "required_n" in data
    assert "achieved_power" in data
    assert "test_type" in data
    assert data["test_type"] == "ttest_ind"
    assert data["required_n"] >= 1


def test_power_invalid_test(tmp_path: Path, monkeypatch):
    """gsigmad power --test invalid_test exits 1 with error."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["power", "--test", "invalid_test", "--effect-size", "0.4"],
    )
    assert result.exit_code == 1


def test_power_no_init_required(tmp_path: Path, monkeypatch):
    """power command works without .gsigmad/ initialization (standalone calculator)."""
    monkeypatch.chdir(tmp_path)
    # No init -- should still work
    result = runner.invoke(
        app,
        ["power", "--test", "ttest_ind", "--effect-size", "0.5"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, f"stdout: {result.output}"
