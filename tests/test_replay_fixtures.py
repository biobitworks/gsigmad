"""Tests for the replay fixture mechanism in the parity runtime."""
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


def _write_fixture_file(fixture_dir: Path, lane: str, scenario: str, data: dict) -> Path:
    fixture_dir.mkdir(parents=True, exist_ok=True)
    path = fixture_dir / f"{lane}-{scenario}.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


# -- Test 1: _load_replay_fixtures returns parsed dict for existing fixture file --

def test_load_replay_fixtures_returns_parsed_dict(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "replay"
    fixture_data = {
        "preflight": {
            "status": "ready",
            "failure_class": None,
            "error_identifier": None,
            "message": "replay fixture",
            "binary": {"path": "/replay/claude", "version": "replay-fixture-v1"},
        },
        "rows": {
            "row-01": {"exit_code": 0, "stdout": '{"runtime_mode":"gsigmad"}', "stderr": ""},
        },
    }
    _write_fixture_file(fixture_dir, "claude", "command-parity", fixture_data)

    result = parity_mod._load_replay_fixtures("claude", "command-parity", fixture_dir=fixture_dir)

    assert result == fixture_data
    assert result["preflight"]["status"] == "ready"
    assert "row-01" in result["rows"]


# -- Test 2: _load_replay_fixtures returns empty dict when file does not exist --

def test_load_replay_fixtures_returns_empty_dict_when_missing(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "replay"
    fixture_dir.mkdir(parents=True, exist_ok=True)

    result = parity_mod._load_replay_fixtures("claude", "nonexistent-scenario", fixture_dir=fixture_dir)

    assert result == {}


# -- Test 3: preflight_lane returns ready with replay data when lane is in replay_lanes --

def test_preflight_lane_returns_ready_for_replay_lane(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "replay"
    preflight_data = {
        "status": "ready",
        "failure_class": None,
        "error_identifier": None,
        "message": "replay fixture -- deterministic preflight",
        "binary": {"path": "/replay/claude", "version": "replay-fixture-v1"},
    }
    fixture_data = {"preflight": preflight_data, "rows": {}}
    _write_fixture_file(fixture_dir, "claude", "command-parity", fixture_data)

    run_root = tmp_path / "run"
    run_root.mkdir(parents=True, exist_ok=True)

    result = parity_mod.preflight_lane(
        "claude",
        run_root=run_root,
        local_model="qwen2.5-coder:7b",
        timeout_seconds=30,
        replay_lanes={"claude"},
        scenario="command-parity",
        replay_fixture_dir=fixture_dir,
    )

    assert result["status"] == "ready"
    assert result["binary"]["version"] == "replay-fixture-v1"


# -- Test 4: preflight_lane falls through to normal probe when not in replay_lanes --

def test_preflight_lane_falls_through_when_not_replay(tmp_path: Path, monkeypatch) -> None:
    """When lane is NOT in replay_lanes, normal preflight probe runs."""
    run_root = tmp_path / "run"
    run_root.mkdir(parents=True, exist_ok=True)

    # Mock a degraded result from the normal binary probe
    monkeypatch.setattr(
        parity_mod,
        "_run_process",
        lambda command, cwd, timeout_seconds: {
            "exit_code": 1,
            "stdout": "",
            "stderr": "not authenticated",
        },
    )

    result = parity_mod.preflight_lane(
        "claude",
        run_root=run_root,
        local_model="qwen2.5-coder:7b",
        timeout_seconds=30,
        lane_binaries={"claude": {"path": "/usr/bin/claude", "version": "2.0"}},
        replay_lanes={"codex"},  # claude is NOT in replay_lanes
    )

    # Should fall through to normal probe, which will fail
    assert result["status"] != "ready" or result.get("failure_class") is not None


# -- Test 5: invoke_lane_command returns replay_response directly --

def test_invoke_lane_command_returns_replay_response(tmp_path: Path) -> None:
    replay_response = {
        "exit_code": 0,
        "stdout": '{"runtime_mode":"gsigmad","source":"pyproject.toml"}',
        "stderr": "",
    }

    result = parity_mod.invoke_lane_command(
        lane="claude",
        shell_command="PYTHONPATH=src python3 -m gsigmad --json inspect /path",
        cwd=tmp_path,
        local_model="qwen2.5-coder:7b",
        timeout_seconds=30,
        lane_binaries={"claude": {"path": "/bin/claude", "version": "1.0"}},
        replay_response=replay_response,
    )

    assert result == replay_response


# -- Test 6: run_parity with replay_lanes produces report with replay lane ready --

def test_run_parity_with_replay_lanes_produces_ready_report(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    shadow_root = tmp_path / "shadow-seeds"
    artifact_root = tmp_path / "artifacts" / "parity"
    fixture_dir = tmp_path / "replay"

    _write_native_project(repo_root)
    _write_routed_project(shadow_root)
    _write_shadow_manifest(repo_root, shadow_root)

    # Create replay fixture for claude lane with all 7 rows
    claude_fixture = {
        "preflight": {
            "status": "ready",
            "failure_class": None,
            "error_identifier": None,
            "message": "replay fixture -- deterministic preflight",
            "binary": {"path": "/replay/claude", "version": "replay-fixture-v1"},
        },
        "rows": {},
    }
    for i in range(1, 8):
        row_id = f"row-{i:02d}"
        if i == 7:
            claude_fixture["rows"][row_id] = {
                "exit_code": 1,
                "stdout": json.dumps({
                    "failure_class": "unsupported_command",
                    "error_identifier": "NOT_ROUTED_SAFELY",
                    "pre_dispatch_rejection": True,
                }),
                "stderr": "",
            }
        else:
            claude_fixture["rows"][row_id] = {
                "exit_code": 0,
                "stdout": json.dumps({"runtime_mode": "gsigmad", "source": "pyproject.toml"}),
                "stderr": "",
            }
    _write_fixture_file(fixture_dir, "claude", "command-parity", claude_fixture)

    # Mock external dependencies
    monkeypatch.setattr(
        parity_mod,
        "_collect_lane_binaries",
        lambda local_model: {
            "claude": {"path": "/bin/claude", "version": "1.0"},
            "codex": {"path": "/bin/codex", "version": "1.0"},
        },
    )
    monkeypatch.setattr(parity_mod, "_git_commit", lambda repo_root: "deadbeef")

    report = parity_mod.run_parity(
        repo_root=repo_root,
        lanes=["claude"],
        artifact_root=artifact_root,
        replay_lanes={"claude"},
        replay_fixture_dir=fixture_dir,
    )

    assert report["results"]["claude"]["status"] == "ready"
    assert report["results"]["claude"]["preflight"]["status"] == "ready"
    assert len(report["results"]["claude"]["rows"]) == 7


# -- Test 7: DEFAULT_LOCAL_MODEL is qwen2.5-coder:7b --

def test_default_local_model_is_available() -> None:
    assert parity_mod.DEFAULT_LOCAL_MODEL == "qwen2.5-coder:7b"
