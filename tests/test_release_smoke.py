"""Tests for the public release smoke command."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_release_smoke_skip_build(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [
            sys.executable,
            "scripts/release_smoke.py",
            "--workspace",
            str(tmp_path / "smoke"),
            "--skip-build",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads((tmp_path / "smoke" / "release_smoke_receipt.json").read_text(encoding="utf-8"))
    assert receipt["passed"] is True
    assert {item["name"] for item in receipt["commands"]} >= {
        "cli_version",
        "cli_help",
        "init_project",
        "status_project",
        "register_exploratory",
        "run_dry",
        "audit_registered",
        "npm_shim",
        "huggingface_artifact_smoke",
        "homebrew_artifact_smoke",
    }
    assert {item["name"] for item in receipt["checks"]} >= {
        "config_created",
        "lab_notebook_created",
        "codex_skill_installed",
        "claude_skill_installed",
        "experiment_created",
        "packaged_skill_bundle",
        "public_artifact:docs/COMPARISON.md",
        "public_artifact:docs/QUICKSTART.md",
        "public_artifact:docs/RELEASE_DOI_PROCESS.md",
        "public_artifact:docs/SCOPE_AND_ETHICS.md",
        "public_artifact:examples/benchmark/bad_science_fixtures.jsonl",
        "public_artifact:examples/benchmark/claim_boundary_corpus.jsonl",
        "public_artifact:examples/benchmark/failure_taxonomy.md",
        "public_artifact:examples/huggingface/dataset/README.md",
        "public_artifact:examples/huggingface/space/README.md",
        "public_artifact:scripts/clean_install_smoke.py",
        "public_artifact:scripts/huggingface_artifact_smoke.py",
        "public_artifact:scripts/homebrew_artifact_smoke.py",
        "public_artifact:scripts/npm_package_smoke.py",
    }
