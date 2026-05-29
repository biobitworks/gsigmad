#!/usr/bin/env python3
"""Public release smoke test for the gsigmad mirror.

The smoke is intentionally local-only: it creates a disposable project, runs
the core CLI lifecycle without external services, verifies packaged skill
assets, builds release archives, and checks the npm shim can delegate to the
active Python package.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class Receipt:
    name: str
    command: list[str]
    cwd: str
    returncode: int
    status: str
    stdout_tail: str
    stderr_tail: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _tail(text: str, limit: int = 2000) -> str:
    return text[-limit:]


def _run(
    name: str,
    command: list[str],
    *,
    cwd: Path,
    expected: tuple[int, ...] = (0,),
    env: dict[str, str] | None = None,
    timeout: int = 120,
) -> Receipt:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return Receipt(
        name=name,
        command=command,
        cwd=str(cwd),
        returncode=result.returncode,
        status="PASS" if result.returncode in expected else "FAIL",
        stdout_tail=_tail(result.stdout),
        stderr_tail=_tail(result.stderr),
    )


def _check_path(name: str, path: Path, checks: list[dict[str, Any]]) -> None:
    checks.append(
        {
            "name": name,
            "status": "PASS" if path.exists() else "FAIL",
            "path": str(path),
        }
    )


def _registered_exp_id(receipt: Receipt) -> str | None:
    try:
        payload = json.loads(receipt.stdout_tail)
    except json.JSONDecodeError:
        return None
    exp_id = payload.get("exp_id")
    return str(exp_id) if exp_id else None


def _archive_names(path: Path) -> set[str]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return set(archive.namelist())
    if path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as archive:
            return {member.name for member in archive.getmembers()}
    raise ValueError(f"unsupported archive type: {path}")


def _check_archive_contains(
    name: str,
    archive: Path,
    required: list[str],
    checks: list[dict[str, Any]],
) -> None:
    names = _archive_names(archive)
    missing = [item for item in required if item not in names]
    checks.append(
        {
            "name": name,
            "status": "PASS" if not missing else "FAIL",
            "archive": str(archive),
            "missing": missing,
        }
    )


PUBLIC_ARTIFACTS = [
    "docs/COMPARISON.md",
    "docs/HOW_TO_USE_GSIGMAD.md",
    "docs/PUBLIC_BENCHMARK_PLAN.md",
    "docs/QUICKSTART.md",
    "docs/RELEASE_DOI_PROCESS.md",
    "docs/RUNTIME_ADOPTION_MATRIX.md",
    "docs/SCOPE_AND_ETHICS.md",
    "examples/benchmark/README.md",
    "examples/benchmark/bad_science_fixtures.jsonl",
    "examples/benchmark/claim_boundary_corpus.jsonl",
    "examples/benchmark/failure_taxonomy.md",
    "examples/huggingface/README.md",
    "examples/huggingface/dataset/README.md",
    "examples/huggingface/dataset/gate_traces.jsonl",
    "examples/huggingface/space/README.md",
    "examples/huggingface/space/index.html",
    "examples/projects/README.md",
    "examples/projects/adoption_matrix.v1.2.0b1.json",
    "examples/projects/kb_index.v1.2.0b1.json",
    "examples/projects/adoption_matrix_receipt.v1.2.0b1.json",
    "scripts/adoption_matrix_smoke.py",
    "scripts/clean_install_smoke.py",
    "scripts/huggingface_artifact_smoke.py",
    "scripts/homebrew_artifact_smoke.py",
    "scripts/npm_package_smoke.py",
]


def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    repo = _repo_root()
    workspace = args.workspace.resolve() if args.workspace else Path(tempfile.mkdtemp(prefix="gsigmad-release-smoke-"))
    workspace.mkdir(parents=True, exist_ok=True)
    project = workspace / "project"
    dist = workspace / "dist"
    python = sys.executable
    commands: list[Receipt] = []
    checks: list[dict[str, Any]] = []

    if project.exists():
        shutil.rmtree(project)

    commands.append(_run("cli_version", [python, "-m", "gsigmad", "--version"], cwd=repo))
    commands.append(_run("cli_help", [python, "-m", "gsigmad", "--help"], cwd=repo))
    commands.append(_run("init_project", [python, "-m", "gsigmad", "--json", "init", str(project)], cwd=repo))
    commands.append(_run("status_project", [python, "-m", "gsigmad", "--json", "status"], cwd=project))
    commands.append(
        _run(
            "register_exploratory",
            [
                python,
                "-m",
                "gsigmad",
                "--json",
                "register",
                "-t",
                "exploratory",
                "-H",
                "H0: release smoke has no effect.",
                "--title",
                "Release smoke experiment",
            ],
            cwd=project,
        )
    )
    exp_id = _registered_exp_id(commands[-1]) or "UNPARSED_EXP_ID"
    commands.append(_run("run_dry", [python, "-m", "gsigmad", "--json", "run", "--dry-run", exp_id], cwd=project))
    commands.append(_run("audit_registered", [python, "-m", "gsigmad", "--json", "audit", exp_id, "--skip-citations"], cwd=project))

    _check_path("config_created", project / ".gsigmad" / "config.yaml", checks)
    _check_path("lab_notebook_created", project / ".gsigmad" / "LAB_NOTEBOOK.md", checks)
    _check_path("codex_skill_installed", project / ".agents" / "skills" / "gsigmad" / "SKILL.md", checks)
    _check_path("claude_skill_installed", project / ".claude" / "skills" / "gsigmad" / "SKILL.md", checks)
    _check_path("experiment_created", project / ".gsigmad" / "experiments" / f"{exp_id}.yaml", checks)
    for artifact in PUBLIC_ARTIFACTS:
        _check_path(f"public_artifact:{artifact}", repo / artifact, checks)

    from importlib.resources import files

    skill_bundle = files("gsigmad.skill_bundle").joinpath("skills/gsigmad/SKILL.md")
    checks.append(
        {
            "name": "packaged_skill_bundle",
            "status": "PASS" if skill_bundle.is_file() else "FAIL",
            "path": str(skill_bundle),
        }
    )

    env = dict(os.environ)
    env["GSIGMAD_PYTHON"] = python
    env["PATH"] = f"{Path(python).parent}{os.pathsep}{env.get('PATH', '')}"
    commands.append(_run("npm_shim", ["node", "npm/bin/gsigmad.js", "--version"], cwd=repo, env=env))
    commands.append(
        _run(
            "huggingface_artifact_smoke",
            [python, "scripts/huggingface_artifact_smoke.py", "--workspace", str(workspace / "huggingface-artifacts")],
            cwd=repo,
        )
    )
    commands.append(
        _run(
            "homebrew_artifact_smoke",
            [python, "scripts/homebrew_artifact_smoke.py", "--workspace", str(workspace / "homebrew-artifacts")],
            cwd=repo,
        )
    )

    if not args.skip_build:
        if dist.exists():
            shutil.rmtree(dist)
        if importlib.util.find_spec("build") is not None:
            build_command = [python, "-m", "build", "--sdist", "--wheel", "--outdir", str(dist)]
        elif shutil.which("uv"):
            build_command = ["uv", "run", "--with", "build", "python", "-m", "build", "--sdist", "--wheel", "--outdir", str(dist)]
        else:
            build_command = [python, "-m", "build", "--sdist", "--wheel", "--outdir", str(dist)]
        commands.append(_run("package_build", build_command, cwd=repo, timeout=180))
        wheels = sorted(dist.glob("*.whl"))
        sdists = sorted(dist.glob("*.tar.gz"))
        if wheels:
            _check_archive_contains(
                "wheel_release_contents",
                wheels[-1],
                [
                    "gsigmad/skill_bundle/skills/gsigmad/SKILL.md",
                    "gsigmad/release_assets/skills/gsigmad/SKILL.md",
                    "gsigmad/release_assets/docs/DASHBOARD.md",
                    "gsigmad/release_assets/docs/COMPARISON.md",
                    "gsigmad/release_assets/docs/HOW_TO_USE_GSIGMAD.md",
                    "gsigmad/release_assets/docs/PUBLIC_BENCHMARK_PLAN.md",
                    "gsigmad/release_assets/docs/QUICKSTART.md",
                    "gsigmad/release_assets/docs/RELEASE_DOI_PROCESS.md",
                    "gsigmad/release_assets/docs/RUNTIME_ADOPTION_MATRIX.md",
                    "gsigmad/release_assets/docs/SCOPE_AND_ETHICS.md",
                    "gsigmad/release_assets/specs/find-experiments.yaml",
                    "gsigmad/release_assets/scripts/adoption_matrix_smoke.py",
                    "gsigmad/release_assets/scripts/clean_install_smoke.py",
                    "gsigmad/release_assets/scripts/huggingface_artifact_smoke.py",
                    "gsigmad/release_assets/scripts/homebrew_artifact_smoke.py",
                    "gsigmad/release_assets/scripts/npm_package_smoke.py",
                    "gsigmad/release_assets/scripts/release_smoke.py",
                    "gsigmad/release_assets/examples/benchmark/README.md",
                    "gsigmad/release_assets/examples/benchmark/bad_science_fixtures.jsonl",
                    "gsigmad/release_assets/examples/benchmark/claim_boundary_corpus.jsonl",
                    "gsigmad/release_assets/examples/benchmark/failure_taxonomy.md",
                    "gsigmad/release_assets/examples/huggingface/dataset/README.md",
                    "gsigmad/release_assets/examples/huggingface/dataset/gate_traces.jsonl",
                    "gsigmad/release_assets/examples/huggingface/space/README.md",
                    "gsigmad/release_assets/examples/huggingface/space/index.html",
                    "gsigmad/release_assets/examples/projects/README.md",
                    "gsigmad/release_assets/examples/projects/adoption_matrix.v1.2.0b1.json",
                    "gsigmad/release_assets/examples/projects/kb_index.v1.2.0b1.json",
                    "gsigmad/release_assets/examples/projects/adoption_matrix_receipt.v1.2.0b1.json",
                    "gsigmad/release_assets/npm/bin/gsigmad.js",
                    "gsigmad/release_assets/homebrew/gsigmad.rb",
                ],
                checks,
            )
        else:
            checks.append({"name": "wheel_release_contents", "status": "FAIL", "missing": ["*.whl"]})
        if sdists:
            prefix = sdists[-1].name.removesuffix(".tar.gz")
            _check_archive_contains(
                "sdist_release_contents",
                sdists[-1],
                [
                    f"{prefix}/skills/gsigmad/SKILL.md",
                    f"{prefix}/docs/DASHBOARD.md",
                    f"{prefix}/docs/COMPARISON.md",
                    f"{prefix}/docs/HOW_TO_USE_GSIGMAD.md",
                    f"{prefix}/docs/PUBLIC_BENCHMARK_PLAN.md",
                    f"{prefix}/docs/QUICKSTART.md",
                    f"{prefix}/docs/RELEASE_DOI_PROCESS.md",
                    f"{prefix}/docs/RUNTIME_ADOPTION_MATRIX.md",
                    f"{prefix}/docs/SCOPE_AND_ETHICS.md",
                    f"{prefix}/specs/find-experiments.yaml",
                    f"{prefix}/scripts/adoption_matrix_smoke.py",
                    f"{prefix}/scripts/clean_install_smoke.py",
                    f"{prefix}/scripts/huggingface_artifact_smoke.py",
                    f"{prefix}/scripts/homebrew_artifact_smoke.py",
                    f"{prefix}/scripts/npm_package_smoke.py",
                    f"{prefix}/scripts/release_smoke.py",
                    f"{prefix}/examples/benchmark/README.md",
                    f"{prefix}/examples/benchmark/bad_science_fixtures.jsonl",
                    f"{prefix}/examples/benchmark/claim_boundary_corpus.jsonl",
                    f"{prefix}/examples/benchmark/failure_taxonomy.md",
                    f"{prefix}/examples/huggingface/dataset/README.md",
                    f"{prefix}/examples/huggingface/dataset/gate_traces.jsonl",
                    f"{prefix}/examples/huggingface/space/README.md",
                    f"{prefix}/examples/huggingface/space/index.html",
                    f"{prefix}/examples/projects/README.md",
                    f"{prefix}/examples/projects/adoption_matrix.v1.2.0b1.json",
                    f"{prefix}/examples/projects/kb_index.v1.2.0b1.json",
                    f"{prefix}/examples/projects/adoption_matrix_receipt.v1.2.0b1.json",
                    f"{prefix}/npm/bin/gsigmad.js",
                    f"{prefix}/homebrew/gsigmad.rb",
                ],
                checks,
            )
        else:
            checks.append({"name": "sdist_release_contents", "status": "FAIL", "missing": ["*.tar.gz"]})

    passed = all(item.status == "PASS" for item in commands) and all(item.get("status") == "PASS" for item in checks)
    receipt = {
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo": str(repo),
        "workspace": str(workspace),
        "passed": passed,
        "commands": [asdict(item) for item in commands],
        "checks": checks,
    }
    (workspace / "release_smoke_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    return receipt


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, help="Directory for disposable project and receipt output.")
    parser.add_argument("--skip-build", action="store_true", help="Skip sdist/wheel build checks.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    receipt = run_smoke(parse_args(argv or sys.argv[1:]))
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
