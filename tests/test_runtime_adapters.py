"""Tests for coexistence runtime adapter loading and resolution."""
from __future__ import annotations

from pathlib import Path

import pytest

from gsigmad.governance.adapters.runtime import (
    ensure_command_supported,
    load_runtime_manifest,
    resolve_project_target,
)


def _write_manifest(
    repo_root: Path,
    target_root: Path,
    *,
    status_mode: str = "legacy",
    portfolio_role: str | None = None,
    contract_version: str | None = None,
    repo_class: str | None = None,
    run_mode: str = "legacy",
) -> Path:
    registry = repo_root / "adapters" / "runtime"
    registry.mkdir(parents=True)
    extra = []
    if portfolio_role is not None:
        extra.append(f"portfolio_role: {portfolio_role}")
    if contract_version is not None:
        extra.append(f'contract_version: "{contract_version}"')
    if repo_class is not None:
        extra.append(f"repo_class: {repo_class}")
    manifest = registry / "shadow-seeds.yaml"
    manifest.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "project_name: shadow-seeds",
                f"project_root: {target_root}",
                'namespace_prefix: "shadow:"',
                f"runtime_mode: {run_mode}",
                "surfaces:",
                "  canon_path: CANON.md",
                "  experiments_dir: experiments",
                "  legacy_state_dir: .agent",
                "  lab_notebook_path: LAB_NOTEBOOK.md",
                "command_modes:",
                f"  status: {status_mode}",
                *extra,
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest


def test_load_runtime_manifest_requires_absolute_root(tmp_path: Path) -> None:
    manifest = tmp_path / "bad.yaml"
    manifest.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "project_name: bad",
                "project_root: relative/path",
                'namespace_prefix: "bad:"',
                "runtime_mode: legacy",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_runtime_manifest(manifest)


def test_resolve_project_target_prefers_native_gsigmad(tmp_path: Path) -> None:
    native = tmp_path / "native"
    (native / ".gsigmad").mkdir(parents=True)

    resolution = resolve_project_target(native)

    assert resolution.source == "native_gsigmad"
    assert resolution.runtime_mode == "gsigmad"
    assert resolution.project_root == native


def test_resolve_project_target_uses_runtime_manifest(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    target_root = tmp_path / "shadow-seeds"
    (target_root / "experiments").mkdir(parents=True)
    manifest = _write_manifest(repo_root, target_root)

    resolution = resolve_project_target(target_root / "experiments", registry_root=repo_root)

    assert resolution.source == "runtime_manifest"
    assert resolution.runtime_mode == "legacy"
    assert resolution.manifest_path == manifest
    assert resolution.namespace_prefix == "shadow:"
    assert resolution.repo_class == "legacy"
    assert resolution.portfolio_role is None
    assert resolution.contract_version is None
    assert resolution.surfaces["experiments_dir"] == str(target_root / "experiments")


def test_ensure_command_supported_raises_actionable_error(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    target_root = tmp_path / "shadow-seeds"
    target_root.mkdir(parents=True)
    _write_manifest(repo_root, target_root, status_mode="unsupported")

    resolution = resolve_project_target(target_root, registry_root=repo_root)

    with pytest.raises(ValueError) as exc:
        ensure_command_supported(resolution, "status")

    assert "not routed safely" in str(exc.value)
    assert "command_modes" in str(exc.value)


def test_load_runtime_manifest_accepts_portfolio_role_and_contract_version(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    target_root = tmp_path / "shadow-seeds"
    target_root.mkdir(parents=True)
    manifest_path = _write_manifest(
        repo_root,
        target_root,
        portfolio_role="project-execution",
        contract_version="1.0",
    )

    manifest = load_runtime_manifest(manifest_path)

    assert manifest.portfolio_role == "project-execution"
    assert manifest.contract_version == "1.0"


def test_load_runtime_manifest_rejects_unknown_portfolio_role(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    target_root = tmp_path / "shadow-seeds"
    target_root.mkdir(parents=True)
    manifest_path = _write_manifest(
        repo_root,
        target_root,
        portfolio_role="unsupported-role",
        contract_version="1.0",
    )

    with pytest.raises(ValueError, match="unsupported portfolio_role"):
        load_runtime_manifest(manifest_path)


def test_load_runtime_manifest_rejects_unsupported_contract_version(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    target_root = tmp_path / "shadow-seeds"
    target_root.mkdir(parents=True)
    manifest_path = _write_manifest(
        repo_root,
        target_root,
        portfolio_role="project-execution",
        contract_version="9.9",
    )

    with pytest.raises(ValueError, match="unsupported contract_version"):
        load_runtime_manifest(manifest_path)


def test_load_runtime_manifest_requires_contract_version_when_role_is_set(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    target_root = tmp_path / "shadow-seeds"
    target_root.mkdir(parents=True)
    manifest_path = _write_manifest(
        repo_root,
        target_root,
        portfolio_role="project-execution",
    )

    with pytest.raises(ValueError, match="contract_version is required"):
        load_runtime_manifest(manifest_path)


def test_load_runtime_manifest_requires_role_when_contract_version_is_set(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    target_root = tmp_path / "shadow-seeds"
    target_root.mkdir(parents=True)
    manifest_path = _write_manifest(
        repo_root,
        target_root,
        contract_version="1.0",
    )

    with pytest.raises(ValueError, match="portfolio_role is required"):
        load_runtime_manifest(manifest_path)


def test_load_runtime_manifest_rejects_runtime_lane_overrides(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    target_root = tmp_path / "shadow-seeds"
    target_root.mkdir(parents=True)
    manifest_path = _write_manifest(
        repo_root,
        target_root,
        portfolio_role="project-execution",
        contract_version="1.0",
    )
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8")
        + "lane_overrides:\n"
        + "  execute: gpu-fleet\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        load_runtime_manifest(manifest_path)


def test_resolve_project_target_marks_native_project_as_active_repo_class(tmp_path: Path) -> None:
    native = tmp_path / "native"
    (native / ".gsigmad").mkdir(parents=True)

    resolution = resolve_project_target(native)

    assert resolution.repo_class == "active"


def test_load_runtime_manifest_rejects_unknown_repo_class(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    target_root = tmp_path / "shadow-seeds"
    target_root.mkdir(parents=True)
    manifest_path = _write_manifest(repo_root, target_root, repo_class="unknown")

    with pytest.raises(ValueError, match="unsupported repo_class"):
        load_runtime_manifest(manifest_path)


def test_load_runtime_manifest_rejects_mutating_commands_for_frozen_repo(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    target_root = tmp_path / "shadow-seeds"
    target_root.mkdir(parents=True)
    manifest_path = _write_manifest(repo_root, target_root, repo_class="frozen")
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8")
        + "command_modes:\n"
        + "  run: legacy\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="frozen repos cannot opt into mutating command"):
        load_runtime_manifest(manifest_path)
