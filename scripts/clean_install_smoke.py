#!/usr/bin/env python3
"""Clean wheel-install smoke test for public gsigmad releases.

This smoke builds or accepts a wheel, installs it into a disposable virtual
environment, and runs the offline CLI lifecycle outside the source tree. It is
the closest local equivalent to a PyPI install check before a public package is
uploaded.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import venv
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


def _venv_script(venv_dir: Path, name: str) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / f"{name}.exe"
    return venv_dir / "bin" / name


def _check_path(name: str, path: Path, checks: list[dict[str, Any]]) -> None:
    checks.append({"name": name, "status": "PASS" if path.exists() else "FAIL", "path": str(path)})


def _registered_exp_id(receipt: Receipt) -> str | None:
    try:
        payload = json.loads(receipt.stdout_tail)
    except json.JSONDecodeError:
        return None
    exp_id = payload.get("exp_id")
    return str(exp_id) if exp_id else None


def _clean_install_env() -> dict[str, str]:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    return env


def _build_wheel(repo: Path, dist: Path) -> tuple[Path | None, Receipt]:
    if dist.exists():
        shutil.rmtree(dist)
    dist.mkdir(parents=True, exist_ok=True)

    python = sys.executable
    if importlib.util.find_spec("build") is not None:
        command = [python, "-m", "build", "--wheel", "--outdir", str(dist)]
    elif shutil.which("uv"):
        command = ["uv", "run", "--with", "build", "python", "-m", "build", "--wheel", "--outdir", str(dist)]
    else:
        command = [python, "-m", "build", "--wheel", "--outdir", str(dist)]

    receipt = _run("package_build_wheel", command, cwd=repo, timeout=240)
    wheels = sorted(dist.glob("*.whl"))
    return (wheels[-1] if wheels else None), receipt


def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    repo = _repo_root()
    workspace = args.workspace.resolve() if args.workspace else Path(tempfile.mkdtemp(prefix="gsigmad-clean-install-"))
    workspace.mkdir(parents=True, exist_ok=True)
    dist = workspace / "dist"
    venv_dir = workspace / "venv"
    project = workspace / "project"
    commands: list[Receipt] = []
    checks: list[dict[str, Any]] = []

    if project.exists():
        shutil.rmtree(project)
    if venv_dir.exists():
        shutil.rmtree(venv_dir)

    wheel = args.wheel.resolve() if args.wheel else None
    if wheel is None:
        wheel, build_receipt = _build_wheel(repo, dist)
        commands.append(build_receipt)
    elif not wheel.exists():
        checks.append({"name": "input_wheel_exists", "status": "FAIL", "path": str(wheel)})

    checks.append({"name": "wheel_available", "status": "PASS" if wheel and wheel.exists() else "FAIL", "path": str(wheel) if wheel else None})

    venv.EnvBuilder(with_pip=True, clear=True).create(venv_dir)
    python = _venv_python(venv_dir)
    gsigmad = _venv_script(venv_dir, "gsigmad")
    clean_env = _clean_install_env()
    _check_path("venv_python_created", python, checks)

    if wheel and wheel.exists():
        commands.append(_run("pip_upgrade", [str(python), "-m", "pip", "install", "--upgrade", "pip"], cwd=workspace, env=clean_env, timeout=240))
        commands.append(_run("pip_install_wheel", [str(python), "-m", "pip", "install", str(wheel)], cwd=workspace, env=clean_env, timeout=300))

    _check_path("console_script_created", gsigmad, checks)

    commands.append(_run("installed_cli_version", [str(gsigmad), "--version"], cwd=workspace, env=clean_env))
    commands.append(_run("installed_module_help", [str(python), "-m", "gsigmad", "--help"], cwd=workspace, env=clean_env))
    commands.append(
        _run(
            "installed_asset_probe",
            [
                str(python),
                "-c",
                "from importlib.resources import files; "
                "assert files('gsigmad.skill_bundle').joinpath('skills/gsigmad/SKILL.md').is_file(); "
                "assert files('gsigmad').joinpath('release_assets/docs/SCOPE_AND_ETHICS.md').is_file()",
            ],
            cwd=workspace,
            env=clean_env,
        )
    )

    commands.append(_run("init_project", [str(gsigmad), "--json", "init", str(project)], cwd=workspace, env=clean_env))
    commands.append(_run("status_project", [str(gsigmad), "--json", "status"], cwd=project, env=clean_env))
    commands.append(
        _run(
            "register_exploratory",
            [
                str(gsigmad),
                "--json",
                "register",
                "-t",
                "exploratory",
                "-H",
                "H0: clean wheel install has no effect.",
                "--title",
                "Clean wheel install smoke",
            ],
            cwd=project,
            env=clean_env,
        )
    )
    exp_id = _registered_exp_id(commands[-1]) or "EXP-1.1"
    commands.append(_run("run_dry", [str(gsigmad), "--json", "run", "--dry-run", exp_id], cwd=project, env=clean_env))
    commands.append(_run("audit_registered", [str(gsigmad), "--json", "audit", exp_id, "--skip-citations"], cwd=project, env=clean_env))

    env = _clean_install_env()
    env["GSIGMAD_PYTHON"] = str(python)
    commands.append(_run("npm_shim_installed_python", ["node", "npm/bin/gsigmad.js", "--version"], cwd=repo, env=env))

    _check_path("config_created", project / ".gsigmad" / "config.yaml", checks)
    _check_path("lab_notebook_created", project / ".gsigmad" / "LAB_NOTEBOOK.md", checks)
    _check_path("codex_skill_installed", project / ".agents" / "skills" / "gsigmad" / "SKILL.md", checks)
    _check_path("claude_skill_installed", project / ".claude" / "skills" / "gsigmad" / "SKILL.md", checks)
    _check_path("experiment_created", project / ".gsigmad" / "experiments" / f"{exp_id}.yaml", checks)

    passed = all(item.status == "PASS" for item in commands) and all(item.get("status") == "PASS" for item in checks)
    receipt = {
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo": str(repo),
        "workspace": str(workspace),
        "wheel": str(wheel) if wheel else None,
        "passed": passed,
        "commands": [asdict(item) for item in commands],
        "checks": checks,
    }
    (workspace / "clean_install_smoke_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    return receipt


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, help="Directory for venv, disposable project, and receipt output.")
    parser.add_argument("--wheel", type=Path, help="Existing wheel to install instead of building one.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    receipt = run_smoke(parse_args(argv or sys.argv[1:]))
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
