"""Tests for the operational monitoring CLI surface."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from typer.testing import CliRunner

from gsigmad.cli import app
from gsigmad.governance import monitoring as monitoring_mod

runner = CliRunner()


def _write_manifest(repo_root: Path, target_root: Path) -> None:
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
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_legacy_project(project_root: Path) -> None:
    (project_root / "experiments").mkdir(parents=True)
    (project_root / ".agent").mkdir(parents=True)
    (project_root / "CANON.md").write_text(
        "> **Status**: ACTIVE\n> **Version**: 1.0.0\n",
        encoding="utf-8",
    )


def _stub_now_factory():
    moments = iter(
        [
            datetime(2026, 4, 5, 15, 10, 0, tzinfo=timezone.utc),
            datetime(2026, 4, 5, 15, 11, 0, tzinfo=timezone.utc),
            datetime(2026, 4, 5, 15, 12, 0, tzinfo=timezone.utc),
            datetime(2026, 4, 5, 15, 13, 0, tzinfo=timezone.utc),
        ]
    )
    return lambda: next(moments)


def test_monitor_scan_native_json(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "native"
    result = runner.invoke(app, ["init", str(project)], catch_exceptions=False)
    assert result.exit_code == 0, result.output

    monkeypatch.setattr(monitoring_mod, "_kg_state", lambda: {"available": True, "error": None})
    monkeypatch.setattr(
        monitoring_mod,
        "_drift_state",
        lambda resolution: {
            "pass": True,
            "drift_detected": False,
            "projects_scanned": 1,
            "report_path": None,
            "event_count": 0,
            "events": [],
        },
    )
    monkeypatch.setattr(monitoring_mod, "_utc_now", _stub_now_factory())

    scan = runner.invoke(app, ["--json", "monitor", "scan", str(project)], catch_exceptions=False)
    assert scan.exit_code == 0, scan.output
    payload = json.loads(scan.output)
    assert payload["routing"]["runtime_mode"] == "gsigmad"
    assert payload["kg"]["available"] is True
    assert payload["summary"]["change_count"] == 0

    latest = project / ".gsigmad" / "monitoring" / "latest.json"
    history_dir = project / ".gsigmad" / "monitoring" / "history"
    assert latest.exists()
    assert len(list(history_dir.glob("SCAN-*.json"))) == 1


def test_monitor_scan_routed_legacy_json(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    target_root = tmp_path / "shadow-seeds"
    _write_legacy_project(target_root)
    _write_manifest(repo_root, target_root)

    monkeypatch.chdir(repo_root)
    monkeypatch.setattr(monitoring_mod, "_kg_state", lambda: {"available": False, "error": "offline"})
    monkeypatch.setattr(
        monitoring_mod,
        "_drift_state",
        lambda resolution: {
            "pass": True,
            "drift_detected": False,
            "projects_scanned": 1,
            "report_path": None,
            "event_count": 0,
            "events": [],
        },
    )
    monkeypatch.setattr(monitoring_mod, "_utc_now", _stub_now_factory())

    scan = runner.invoke(app, ["--json", "monitor", "scan", str(target_root)], catch_exceptions=False)
    assert scan.exit_code == 0, scan.output
    payload = json.loads(scan.output)
    assert payload["routing"]["runtime_mode"] == "legacy"

    latest = target_root / ".agent" / "gsigmad-monitoring" / "latest.json"
    assert latest.exists()


def test_monitor_install_and_uninstall_launchd(tmp_path: Path) -> None:
    project = tmp_path / "native"
    result = runner.invoke(app, ["init", str(project)], catch_exceptions=False)
    assert result.exit_code == 0, result.output

    install = runner.invoke(
        app,
        ["--json", "monitor", "install", str(project), "--scheduler", "launchd", "--interval-minutes", "30"],
        catch_exceptions=False,
    )
    assert install.exit_code == 0, install.output
    install_payload = json.loads(install.output)
    artifact = Path(install_payload["install"]["artifact_path"])
    assert artifact.exists()

    uninstall = runner.invoke(app, ["--json", "monitor", "uninstall", str(project)], catch_exceptions=False)
    assert uninstall.exit_code == 0, uninstall.output
    uninstall_payload = json.loads(uninstall.output)
    assert uninstall_payload["removed"] == ["launchd"]
    assert not artifact.exists()


def test_monitor_install_cron_uses_wrapper_script(tmp_path: Path) -> None:
    project = tmp_path / "native"
    result = runner.invoke(app, ["init", str(project)], catch_exceptions=False)
    assert result.exit_code == 0, result.output

    install = runner.invoke(
        app,
        ["--json", "monitor", "install", str(project), "--scheduler", "cron", "--interval-minutes", "90"],
        catch_exceptions=False,
    )
    assert install.exit_code == 0, install.output
    install_payload = json.loads(install.output)
    cron_artifact = Path(install_payload["install"]["artifact_path"])
    script_artifact = Path(install_payload["install"]["script_path"])

    assert cron_artifact.exists()
    assert script_artifact.exists()
    assert "% 90" in cron_artifact.read_text(encoding="utf-8")
    assert str(project) in script_artifact.read_text(encoding="utf-8")

    uninstall = runner.invoke(app, ["--json", "monitor", "uninstall", str(project)], catch_exceptions=False)
    assert uninstall.exit_code == 0, uninstall.output
    assert not cron_artifact.exists()
    assert not script_artifact.exists()
