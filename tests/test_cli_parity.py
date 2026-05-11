"""CLI tests for the parity command surface."""
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from gsigmad.cli import app
from gsigmad.commands import parity as parity_cmd
from gsigmad.governance.parity import TRUST_HANDOFF_ARTIFACT_ROOT

runner = CliRunner()


def test_parity_run_json_output(monkeypatch, tmp_path: Path) -> None:
    artifact_root = tmp_path / "parity"
    monkeypatch.setattr(
        parity_cmd,
        "run_parity",
        lambda **kwargs: {
            "schema_version": "1.0",
            "generated_at": "2026-04-05T17:00:00Z",
            "git_commit": "deadbeef",
            "gsigmad_version": "1.1.0",
            "scenario": "command-parity",
            "phase_requirement": "PARITY-01",
            "lanes": ["claude", "codex"],
            "local_model": "qwen2.5-coder:7b",
            "lane_binaries": {},
            "matrix_version": "phase14-v1",
            "matrix": [],
            "environment_allowlist": {},
            "fixtures": {},
            "results": {
                "claude": {"status": "ready", "preflight": {}, "rows": []},
                "codex": {"status": "degraded", "preflight": {}, "rows": []},
            },
            "mismatches": [],
            "degraded_lanes": ["codex"],
        },
    )

    result = runner.invoke(
        app,
        ["--json", "parity", "run", "--lanes", "claude,codex", "--artifact-root", str(artifact_root)],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["results"]["claude"]["status"] == "ready"
    assert payload["degraded_lanes"] == ["codex"]


def test_parity_run_trust_handoff_uses_phase15_defaults(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_parity(**kwargs):
        captured.update(kwargs)
        return {
            "schema_version": "1.0",
            "generated_at": "2026-04-05T17:00:00Z",
            "git_commit": "deadbeef",
            "gsigmad_version": "1.1.0",
            "scenario": "trust-handoff",
            "phase_requirement": "PARITY-02",
            "lanes": ["claude"],
            "local_model": "qwen2.5-coder:7b",
            "lane_binaries": {},
            "matrix_version": "phase15-v1",
            "matrix": [],
            "environment_allowlist": {},
            "fixtures": {},
            "results": {"claude": {"status": "ready", "preflight": {}, "rows": []}},
            "mismatches": [],
            "degraded_lanes": [],
        }

    monkeypatch.setattr(parity_cmd, "run_parity", fake_run_parity)

    result = runner.invoke(
        app,
        ["--json", "parity", "run", "--scenario", "trust-handoff", "--lanes", "claude"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    assert captured["scenario"] == "trust-handoff"
    assert captured["artifact_root"] == TRUST_HANDOFF_ARTIFACT_ROOT
    payload = json.loads(result.output)
    assert payload["scenario"] == "trust-handoff"


def test_run_path_probe_rejects_routed_project_pre_dispatch(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    target_root = tmp_path / "shadow-seeds"
    registry = repo_root / "adapters" / "runtime"
    registry.mkdir(parents=True)
    target_root.mkdir(parents=True)
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
                "command_modes:",
                "  status: legacy",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(repo_root)

    result = runner.invoke(app, ["--json", "run", str(target_root)], catch_exceptions=False)

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["failure_class"] == "unsupported_command"
    assert payload["pre_dispatch_rejection"] is True
