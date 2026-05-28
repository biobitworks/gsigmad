"""Tests for the Hugging Face artifact smoke command."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_huggingface_artifact_smoke_help() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, "scripts/huggingface_artifact_smoke.py", "--help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0
    assert "Local Hugging Face artifact smoke test" in result.stdout
    assert "--workspace" in result.stdout


def test_huggingface_artifact_smoke_creates_dry_run_bundle(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    workspace = tmp_path / "hf-smoke"
    result = subprocess.run(
        [sys.executable, "scripts/huggingface_artifact_smoke.py", "--workspace", str(workspace)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads((workspace / "huggingface_artifact_smoke_receipt.json").read_text(encoding="utf-8"))
    assert receipt["passed"] is True
    bundle = workspace / "huggingface-publish-dry-run"
    assert (bundle / "dataset" / "README.md").is_file()
    assert (bundle / "dataset" / "gate_traces.jsonl").is_file()
    assert (bundle / "dataset" / "bad_science_fixtures.jsonl").is_file()
    assert (bundle / "space" / "README.md").is_file()
    assert (bundle / "space" / "index.html").is_file()
