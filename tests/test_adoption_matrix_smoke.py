"""Adoption matrix smoke and public corpus checks."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent


def test_adoption_matrix_help_names_public_scope() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/adoption_matrix_smoke.py", "--help"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "Out-of-the-box adoption matrix smoke" in result.stdout
    assert "--update-corpus" in result.stdout


def test_adoption_matrix_standalone_case_uses_returned_exp_id(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/adoption_matrix_smoke.py",
            "--workspace",
            str(tmp_path),
            "--project-filter",
            "generic_python_science",
            "--path-filter",
            "standalone",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=90,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["case_count"] == 1
    case = payload["cases"][0]
    assert case["case_id"] == "generic_python_science__standalone"
    assert case["returned_exp_id"].startswith("EXP-")
    assert case["returned_exp_id_used"] is True
    assert case["gsd_status"] == "not_applicable"

    receipt = tmp_path / "adoption_matrix_smoke_receipt.json"
    assert receipt.is_file()
    full = json.loads(receipt.read_text(encoding="utf-8"))
    artifact_checks = full["cases"][0]["artifact_checks"]
    assert artifact_checks["config"] is True
    assert artifact_checks["lab_notebook"] is True
    assert artifact_checks["codex_skill"] is True
    assert artifact_checks["claude_skill"] is True
    assert artifact_checks["prompt_artifact"] is True
    assert artifact_checks["adapter_not_configured"] is True
    assert artifact_checks["no_live_writeback"] is True


def test_public_adoption_corpus_shape() -> None:
    matrix_path = REPO / "examples" / "projects" / "adoption_matrix.v1.2.0b1.json"
    kb_path = REPO / "examples" / "projects" / "kb_index.v1.2.0b1.json"
    receipt_path = REPO / "examples" / "projects" / "adoption_matrix_receipt.v1.2.0b1.json"

    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    kb = json.loads(kb_path.read_text(encoding="utf-8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    assert matrix["matrix_version"] == "v1.2.0b1"
    assert matrix["project_type_count"] == 6
    assert matrix["adoption_path_count"] == 2
    assert matrix["case_count"] == 12
    assert receipt["passed"] is True
    assert len(matrix["cases"]) == 12
    assert {case["adoption_path"] for case in matrix["cases"]} == {"standalone", "gsd_plus_gsigmad"}
    assert len({case["project_type"] for case in matrix["cases"]}) == 6
    assert all(case["passed"] is True for case in matrix["cases"])
    assert all(case["returned_exp_id"].startswith("EXP-") for case in matrix["cases"])
    assert all(case["returned_exp_id_used"] is True for case in matrix["cases"])
    assert all(case["artifact_checks"]["no_live_writeback"] is True for case in matrix["cases"])
    assert all(case["artifact_checks"]["adapter_not_configured"] is True for case in matrix["cases"])

    runtime = matrix["runtime_examples"]
    assert runtime["chatgpt_codex"]["status"] == "supported"
    assert runtime["claude_code"]["status"] == "supported"
    assert runtime["ollama"]["status"] in {"configured", "not_configured"}
    assert runtime["ollarma"]["status"] in {"configured", "not_configured"}
    private_home_marker = "/" + "Users" + "/" + "byron"
    assert private_home_marker not in json.dumps(runtime)

    assert kb["matrix_version"] == "v1.2.0b1"
    assert len(kb["use_cases"]) == 12
    assert all(item["commands"] for item in kb["use_cases"])
    assert all(item["expected_artifacts"] for item in kb["use_cases"])
    assert all(item["failure_modes"] for item in kb["use_cases"])
