"""Tests for the Homebrew artifact smoke command."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_homebrew_artifact_smoke_help() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, "scripts/homebrew_artifact_smoke.py", "--help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0
    assert "Local Homebrew artifact smoke test" in result.stdout
    assert "--workspace" in result.stdout


def test_homebrew_artifact_smoke_records_deferred_state(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    workspace = tmp_path / "homebrew-smoke"
    result = subprocess.run(
        [sys.executable, "scripts/homebrew_artifact_smoke.py", "--workspace", str(workspace)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads((workspace / "homebrew_artifact_smoke_receipt.json").read_text(encoding="utf-8"))
    assert receipt["passed"] is True
    assert receipt["publish_ready"] is False
    assert receipt["readiness"] == "deferred_until_pypi_and_resources"
    assert "replace_placeholder_sha256_with_pypi_sdist_hash" in receipt["blockers"]
    assert (workspace / "homebrew-tap-dry-run" / "Formula" / "gsigmad.rb").is_file()
