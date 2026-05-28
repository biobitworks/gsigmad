"""Tests for the local npm package smoke command."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_npm_package_smoke_help() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, "scripts/npm_package_smoke.py", "--help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0
    assert "Local npm package smoke test" in result.stdout
    assert "--workspace" in result.stdout
