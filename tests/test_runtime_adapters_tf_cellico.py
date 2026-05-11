"""Tests for a legacy coexistence runtime manifest."""
from __future__ import annotations

from pathlib import Path

import pytest

from gsigmad.governance.adapters.runtime import (
    ensure_command_supported,
    load_runtime_manifest,
    resolve_project_target,
)


def _write_legacy_manifest(tmp_path: Path) -> tuple[Path, Path, Path]:
    repo_root = tmp_path / "repo"
    project_root = tmp_path / "legacy-project"
    (project_root / "experiments").mkdir(parents=True)
    registry = repo_root / "adapters" / "runtime"
    registry.mkdir(parents=True)
    manifest_path = registry / "legacy-project.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "project_name: legacy-project",
                f"project_root: {project_root}",
                'namespace_prefix: "legacy:"',
                "runtime_mode: legacy",
                "surfaces:",
                "  experiments_dir: experiments",
                "  legacy_state_dir: .planning",
                "command_modes:",
                "  status: unsupported",
                "  monitor: unsupported",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return repo_root, project_root, manifest_path


def test_legacy_manifest_loads_with_bounded_defaults(tmp_path: Path) -> None:
    _, project_root, manifest_path = _write_legacy_manifest(tmp_path)
    manifest = load_runtime_manifest(manifest_path)

    assert manifest.project_name == "legacy-project"
    assert manifest.runtime_mode == "legacy"
    assert Path(manifest.project_root) == project_root
    assert manifest.command_modes["status"] == "unsupported"
    assert manifest.command_modes["monitor"] == "unsupported"
    assert manifest.surfaces.experiments_dir == "experiments"
    assert manifest.surfaces.legacy_state_dir == ".planning"


def test_legacy_project_resolves_via_runtime_manifest(tmp_path: Path) -> None:
    repo_root, project_root, manifest_path = _write_legacy_manifest(tmp_path)
    manifest = load_runtime_manifest(manifest_path)

    resolution = resolve_project_target(
        Path(manifest.project_root) / "experiments",
        registry_root=repo_root,
    )

    assert resolution.source == "runtime_manifest"
    assert resolution.project_name == "legacy-project"
    assert resolution.runtime_mode == "legacy"
    assert resolution.surfaces["experiments_dir"] == str(project_root / "experiments")
    assert resolution.surfaces["legacy_state_dir"] == str(project_root / ".planning")


def test_legacy_status_is_not_routed_safely(tmp_path: Path) -> None:
    repo_root, _, manifest_path = _write_legacy_manifest(tmp_path)
    manifest = load_runtime_manifest(manifest_path)
    resolution = resolve_project_target(Path(manifest.project_root), registry_root=repo_root)

    with pytest.raises(ValueError) as exc:
        ensure_command_supported(resolution, "status")

    assert "not routed safely" in str(exc.value)
    assert "command_modes" in str(exc.value)
