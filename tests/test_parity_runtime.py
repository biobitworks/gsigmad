"""Tests for the Phase 14 parity runtime."""
from __future__ import annotations

import json
from pathlib import Path

from gsigmad.governance import parity as parity_mod


def _write_shadow_manifest(repo_root: Path, target_root: Path) -> None:
    registry = repo_root / "adapters" / "runtime"
    registry.mkdir(parents=True)
    (registry / "shadow-seeds.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "project_name: shadow-seeds",
                f"project_root: {target_root}",
                'namespace_prefix: "shadow:"',
                "runtime_mode: legacy",
                "surfaces:",
                "  canon_path: CANON.md",
                "  experiments_dir: experiments",
                "  legacy_state_dir: .agent",
                "command_modes:",
                "  status: legacy",
                "  monitor: legacy",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_native_project(project_root: Path) -> None:
    (project_root / ".gsigmad" / "experiments").mkdir(parents=True)
    (project_root / "src").mkdir(parents=True)
    (project_root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")


def _write_routed_project(project_root: Path) -> None:
    (project_root / "experiments").mkdir(parents=True)
    (project_root / ".agent").mkdir(parents=True)
    (project_root / "CANON.md").write_text("> **Status**: ACTIVE\n> **Version**: 1.0.0\n", encoding="utf-8")


def test_prepare_fixtures_materializes_disposable_registry(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    shadow_root = tmp_path / "shadow-seeds"
    _write_native_project(repo_root)
    _write_routed_project(shadow_root)
    _write_shadow_manifest(repo_root, shadow_root)

    run_root = tmp_path / "parity-run"
    fixtures = parity_mod.prepare_fixtures(
        repo_root=repo_root,
        native="self_fixture",
        routed="shadow_seeds_fixture",
        run_root=run_root,
    )

    assert fixtures["self_fixture"].project_root.exists()
    assert fixtures["shadow_seeds_fixture"].project_root.exists()
    manifest = run_root / "adapters" / "runtime" / "shadow-seeds.yaml"
    assert manifest.exists()
    manifest_text = manifest.read_text(encoding="utf-8")
    assert str(shadow_root) not in manifest_text
    assert str(fixtures["shadow_seeds_fixture"].project_root) in manifest_text


def test_run_parity_writes_report_and_compares_normalized_fields(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    shadow_root = tmp_path / "shadow-seeds"
    artifact_root = tmp_path / "artifacts" / "parity"
    _write_native_project(repo_root)
    _write_routed_project(shadow_root)
    _write_shadow_manifest(repo_root, shadow_root)

    ready = {
        "status": "ready",
        "failure_class": None,
        "error_identifier": None,
        "message": "ok",
        "binary": {"path": "/bin/mock", "version": "1.0"},
    }
    monkeypatch.setattr(parity_mod, "preflight_lane", lambda *args, **kwargs: ready)
    monkeypatch.setattr(
        parity_mod,
        "_collect_lane_binaries",
        lambda local_model: {
            "claude": {"path": "/bin/claude", "version": "1.0"},
            "codex": {"path": "/bin/codex", "version": "1.0"},
        },
    )

    def fake_execute_matrix_row(*, lane, row, **kwargs):
        normalized = {"exit_code": 0, "failure_class": "pass", "pre_dispatch_rejection": False}
        if row["id"] == "row-01":
            normalized["runtime_mode"] = "gsigmad"
        if row["id"] == "row-02":
            normalized["runtime_mode"] = "legacy"
        if row["id"] == "row-07":
            normalized = {
                "exit_code": 1,
                "failure_class": "unsupported_command",
                "error_identifier": "NOT_ROUTED_SAFELY",
                "pre_dispatch_rejection": True,
            }
        return {
            "id": row["id"],
            "command": row["display_command"],
            "target_fixture": row["target_fixture"],
            "status": "pass",
            "exit_code": normalized["exit_code"],
            "failure_class": normalized["failure_class"],
            "error_identifier": normalized.get("error_identifier"),
            "pre_dispatch_rejection": normalized.get("pre_dispatch_rejection"),
            "normalized": normalized,
            "raw_output_path": str(artifact_root / "raw.json"),
            "invocation_hash": "abc",
            "canonical_invocation_spec_hash": "def",
            "sanitizer_version": "1.0",
            "classifier_version": "1.0",
            "model_identifier": lane,
            "target_fixture_identity": row["target_fixture"],
        }

    monkeypatch.setattr(parity_mod, "execute_matrix_row", fake_execute_matrix_row)
    monkeypatch.setattr(parity_mod, "_git_commit", lambda repo_root: "deadbeef")
    monkeypatch.setattr(
        parity_mod,
        "_environment_allowlist",
        lambda: {"OPENAI_API_KEY": "present", "ANTHROPIC_API_KEY": "missing", "OLLAMA_HOST": "http://127.0.0.1:11434"},
    )

    report = parity_mod.run_parity(
        repo_root=repo_root,
        lanes=["claude", "codex"],
        artifact_root=artifact_root,
    )

    latest = artifact_root / "latest.json"
    assert latest.exists()
    written = json.loads(latest.read_text(encoding="utf-8"))
    assert written["git_commit"] == "deadbeef"
    assert written["scenario"] == parity_mod.DEFAULT_SCENARIO
    assert written["phase_requirement"] == "PARITY-01"
    assert written["results"]["claude"]["status"] == "ready"
    assert written["mismatches"] == []
    assert report["matrix_version"] == parity_mod.MATRIX_VERSION


def test_classify_failure_prefers_expected_unsupported_command() -> None:
    row = {
        "expected_outcome": "pre_dispatch_failure",
    }
    output = {
        "exit_code": 1,
        "stdout": json.dumps({"error": "Command 'run' is not routed safely", "pre_dispatch_rejection": True}),
        "stderr": "",
    }
    failure = parity_mod.classify_failure(
        lane="claude",
        row=row,
        command_output=output,
        raw_message=output["stdout"],
    )
    assert failure == "unsupported_command"
