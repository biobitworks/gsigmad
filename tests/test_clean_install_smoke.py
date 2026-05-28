"""Tests for the clean wheel-install smoke command."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_clean_install_smoke_help() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, "scripts/clean_install_smoke.py", "--help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0
    assert "Clean wheel-install smoke test" in result.stdout
    assert "--wheel" in result.stdout
