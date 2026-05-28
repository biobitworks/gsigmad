#!/usr/bin/env python3
"""Local npm package smoke test for public gsigmad releases.

This smoke builds the Python wheel, installs it into a disposable virtual
environment, packs the local npm package, installs the generated tarball into a
disposable Node project, and drives the gsigmad CLI through
node_modules/.bin/gsigmad.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
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
    timeout: int = 180,
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


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _npm_bin(project: Path) -> Path:
    if os.name == "nt":
        return project / "node_modules" / ".bin" / "gsigmad.cmd"
    return project / "node_modules" / ".bin" / "gsigmad"


def _clean_env() -> dict[str, str]:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    return env


def _check_path(name: str, path: Path, checks: list[dict[str, Any]]) -> None:
    checks.append({"name": name, "status": "PASS" if path.exists() else "FAIL", "path": str(path)})


def _registered_exp_id(receipt: Receipt) -> str | None:
    try:
        payload = json.loads(receipt.stdout_tail)
    except json.JSONDecodeError:
        return None
    exp_id = payload.get("exp_id")
    return str(exp_id) if exp_id else None


def _latest_tarball(dist: Path) -> Path | None:
    tarballs = sorted(dist.glob("gsigmad-*.tgz"))
    return tarballs[-1] if tarballs else None


def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    repo = _repo_root()
    workspace = args.workspace.resolve() if args.workspace else Path(tempfile.mkdtemp(prefix="gsigmad-npm-package-"))
    workspace.mkdir(parents=True, exist_ok=True)
    clean_workspace = workspace / "python-install"
    npm_dist = workspace / "npm-dist"
    npm_project = workspace / "npm-project"
    fixture = workspace / "npm-fixture"
    commands: list[Receipt] = []
    checks: list[dict[str, Any]] = []

    for path in (npm_dist, npm_project, fixture):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)

    commands.append(
        _run(
            "clean_install_smoke",
            [sys.executable, "scripts/clean_install_smoke.py", "--workspace", str(clean_workspace)],
            cwd=repo,
            env=_clean_env(),
            timeout=600,
        )
    )
    venv_python = _venv_python(clean_workspace / "venv")
    _check_path("clean_install_venv_python", venv_python, checks)
    _check_path("clean_install_receipt", clean_workspace / "clean_install_smoke_receipt.json", checks)

    commands.append(
        _run(
            "npm_pack",
            ["npm", "pack", "--pack-destination", str(npm_dist)],
            cwd=repo / "npm",
            timeout=180,
        )
    )
    tarball = _latest_tarball(npm_dist)
    checks.append(
        {
            "name": "npm_tarball_created",
            "status": "PASS" if tarball and tarball.exists() else "FAIL",
            "path": str(tarball) if tarball else None,
        }
    )

    commands.append(_run("npm_init", ["npm", "init", "-y"], cwd=npm_project, timeout=120))
    if tarball and tarball.exists():
        commands.append(_run("npm_install_tarball", ["npm", "install", str(tarball)], cwd=npm_project, timeout=300))

    bin_path = _npm_bin(npm_project)
    _check_path("npm_bin_created", bin_path, checks)

    cli_env = _clean_env()
    cli_env["GSIGMAD_PYTHON"] = str(venv_python)
    commands.append(_run("npm_cli_version", [str(bin_path), "--version"], cwd=npm_project, env=cli_env))
    commands.append(_run("npm_cli_help", [str(bin_path), "--help"], cwd=npm_project, env=cli_env))
    commands.append(_run("npm_cli_init", [str(bin_path), "--json", "init", str(fixture)], cwd=npm_project, env=cli_env))
    commands.append(_run("npm_cli_status", [str(bin_path), "--json", "status"], cwd=fixture, env=cli_env))
    commands.append(
        _run(
            "npm_cli_register",
            [
                str(bin_path),
                "--json",
                "register",
                "-t",
                "exploratory",
                "-H",
                "H0: local npm package install has no effect.",
                "--title",
                "Local npm package smoke",
            ],
            cwd=fixture,
            env=cli_env,
        )
    )
    exp_id = _registered_exp_id(commands[-1]) or "EXP-1.1"
    commands.append(_run("npm_cli_run_dry", [str(bin_path), "--json", "run", "--dry-run", exp_id], cwd=fixture, env=cli_env))
    commands.append(_run("npm_cli_audit", [str(bin_path), "--json", "audit", exp_id, "--skip-citations"], cwd=fixture, env=cli_env))

    _check_path("fixture_config_created", fixture / ".gsigmad" / "config.yaml", checks)
    _check_path("fixture_lab_notebook_created", fixture / ".gsigmad" / "LAB_NOTEBOOK.md", checks)
    _check_path("fixture_experiment_created", fixture / ".gsigmad" / "experiments" / f"{exp_id}.yaml", checks)

    passed = all(item.status == "PASS" for item in commands) and all(item.get("status") == "PASS" for item in checks)
    receipt = {
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo": str(repo),
        "workspace": str(workspace),
        "npm_tarball": str(tarball) if tarball else None,
        "venv_python": str(venv_python),
        "passed": passed,
        "commands": [asdict(item) for item in commands],
        "checks": checks,
    }
    (workspace / "npm_package_smoke_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    return receipt


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, help="Directory for venv, npm project, and receipt output.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    receipt = run_smoke(parse_args(argv or sys.argv[1:]))
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
