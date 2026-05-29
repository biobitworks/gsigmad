#!/usr/bin/env python3
"""Out-of-the-box adoption matrix smoke for public gsigmad releases.

The smoke creates fresh disposable repos for multiple project shapes and runs
the local-first governance lifecycle in two modes:

* standalone gsigmad
* get-shit-done local install plus gsigmad

It writes sanitized receipts suitable for public docs. No live writeback,
network upload, or external database is required. If optional local runtimes are
unavailable, the receipt records not_configured with startup instructions.
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

import yaml


VERSION = "1.2.0b1"
MATRIX_VERSION = f"v{VERSION}"
PROJECT_TYPES: list[dict[str, str]] = [
    {
        "id": "generic_python_science",
        "label": "Generic Python science",
        "hypothesis": "H0: the toy measurement distribution is unchanged.",
        "title": "Toy Python measurement check",
        "failure_mode": "missing seed, missing data contract, or causal wording in results",
    },
    {
        "id": "computational_biology",
        "label": "Computational biology",
        "hypothesis": "H0: marker expression is unchanged between toy cell groups.",
        "title": "Toy marker expression check",
        "failure_mode": "unverified DOI, unsupported biological mechanism, or missing provenance",
    },
    {
        "id": "bioinformatics_pipeline",
        "label": "Bioinformatics pipeline",
        "hypothesis": "H0: read-count summaries are unchanged after toy filtering.",
        "title": "Toy read-count filter check",
        "failure_mode": "pipeline step drift, missing manifest, or unrecorded reference data",
    },
    {
        "id": "math_modeling_notebook",
        "label": "Math/modeling notebook",
        "hypothesis": "H0: fitted toy model residuals are unchanged.",
        "title": "Toy model residual check",
        "failure_mode": "non-identifiable model, unpinned solver seed, or notebook-only replay",
    },
    {
        "id": "data_analysis_only",
        "label": "Data-analysis-only",
        "hypothesis": "H0: summary statistic is unchanged after deterministic cleaning.",
        "title": "Toy tabular summary check",
        "failure_mode": "implicit cleaning, undocumented exclusion, or missing environment",
    },
    {
        "id": "non_science_software",
        "label": "Non-science software repo",
        "hypothesis": "H0: latency is unchanged after a toy refactor.",
        "title": "Toy software latency check",
        "failure_mode": "claim framed as scientific evidence instead of engineering evidence",
    },
]
ADOPTION_PATHS = ("standalone", "gsd_plus_gsigmad")


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


def _tail(text: str, limit: int = 400) -> str:
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


def _registered_exp_id(receipt: Receipt) -> str | None:
    try:
        payload = json.loads(receipt.stdout_tail)
    except json.JSONDecodeError:
        return None
    exp_id = payload.get("exp_id")
    return str(exp_id) if exp_id else None


def _probe_json(url: str, *, timeout: float = 1.0) -> dict[str, Any] | None:
    del timeout
    try:
        result = subprocess.run(
            ["curl", "-fsS", "--max-time", "1", url],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"raw": result.stdout}
    return payload if isinstance(payload, dict) else {"payload": payload}


def _runtime_matrix() -> dict[str, Any]:
    ollama = _probe_json("http://127.0.0.1:11434/api/tags")
    ollarma = _probe_json("http://127.0.0.1:8484/health")
    ollarma_start = [
        "ollarma serve",
        "curl -sS http://127.0.0.1:8484/health | jq '.status, .startup_readiness.status'",
    ]
    return {
        "chatgpt_codex": {
            "status": "supported",
            "skill_path": ".agents/skills/gsigmad/SKILL.md",
            "authority": "repo edits and local governance only; no truth authority",
        },
        "claude_code": {
            "status": "supported",
            "skill_path": ".claude/skills/gsigmad/SKILL.md",
            "authority": "repo edits and local governance only; no truth authority",
        },
        "ollama": {
            "status": "configured" if ollama is not None else "not_configured",
            "probe": "http://127.0.0.1:11434/api/tags",
            "model_count": len(ollama.get("models", [])) if ollama else 0,
            "startup": ["ollama serve"],
            "authority": "local model backend only; no governance authority",
        },
        "ollarma": {
            "status": "configured" if ollarma is not None else "not_configured",
            "probe": "http://127.0.0.1:8484/health",
            "health_status": ollarma.get("status") if ollarma else None,
            "startup": ollarma_start,
            "authority": "bounded local bridge with receipts only; no claim promotion authority",
        },
    }


def _seed_project(root: Path, project: dict[str, str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text(
        f"# {project['label']} example\n\n"
        "Synthetic adoption fixture for gsigmad public release testing.\n",
        encoding="utf-8",
    )
    (root / "data").mkdir(exist_ok=True)
    (root / "data" / "toy.csv").write_text("sample,value\nA,1\nB,2\n", encoding="utf-8")
    (root / "scripts").mkdir(exist_ok=True)
    (root / "scripts" / "analyze.py").write_text(
        "from pathlib import Path\n"
        "rows = Path('data/toy.csv').read_text().strip().splitlines()[1:]\n"
        "values = [float(row.split(',')[1]) for row in rows]\n"
        "print({'mean': sum(values) / len(values), 'n': len(values)})\n",
        encoding="utf-8",
    )
    if project["id"] == "bioinformatics_pipeline":
        (root / "Snakefile").write_text(
            "rule all:\n    input: 'results/counts.txt'\n\n"
            "rule counts:\n    output: 'results/counts.txt'\n"
            "    shell: 'mkdir -p results && echo toy-counts > {output}'\n",
            encoding="utf-8",
        )
    if project["id"] == "math_modeling_notebook":
        (root / "notebook.ipynb").write_text(
            json.dumps(
                {
                    "cells": [
                        {
                            "cell_type": "markdown",
                            "metadata": {},
                            "source": ["# Toy model notebook\n", "Replay requires frozen data.\n"],
                        }
                    ],
                    "metadata": {},
                    "nbformat": 4,
                    "nbformat_minor": 5,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    if project["id"] == "non_science_software":
        (root / "src").mkdir(exist_ok=True)
        (root / "src" / "app.py").write_text("def latency_ms():\n    return 1.0\n", encoding="utf-8")


def _write_not_configured_adapter(root: Path) -> Path:
    adapter = root / "adapters" / "runtime" / "optional-overwatch.yaml"
    adapter.parent.mkdir(parents=True, exist_ok=True)
    adapter.write_text(
        "schema_version: 1\n"
        "project_name: optional-overwatch\n"
        "runtime_mode: gsigmad\n"
        "knowledge_base:\n"
        "  status: not_configured\n"
        "writeback:\n"
        "  status: not_configured\n"
        "  live_writeback_performed: false\n",
        encoding="utf-8",
    )
    return adapter


def _scan_no_writeback(root: Path) -> bool:
    scan_roots = [root / ".gsigmad", root / "adapters", root / "README.md"]
    candidates: list[Path] = []
    for item in scan_roots:
        if item.is_file():
            candidates.append(item)
        elif item.is_dir():
            candidates.extend(path for path in item.rglob("*") if path.is_file() and not path.is_symlink())
    for path in candidates:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "live_writeback_performed: true" in text:
            return False
        if '"live_writeback_performed": true' in text:
            return False
    return True


def _check_artifacts(root: Path, exp_id: str, adapter_path: Path, *, combined: bool) -> dict[str, Any]:
    exp_path = root / ".gsigmad" / "experiments" / f"{exp_id}.yaml"
    exp_record = yaml.safe_load(exp_path.read_text(encoding="utf-8"))
    checks = {
        "config": (root / ".gsigmad" / "config.yaml").is_file(),
        "lab_notebook": (root / ".gsigmad" / "LAB_NOTEBOOK.md").is_file(),
        "codex_skill": (root / ".agents" / "skills" / "gsigmad" / "SKILL.md").is_file(),
        "claude_skill": (root / ".claude" / "skills" / "gsigmad" / "SKILL.md").is_file(),
        "experiment_yaml": exp_path.is_file(),
        "prompt_artifact": bool(exp_record.get("prompt_artifact")),
        "prompt_id": str(exp_record.get("prompt_id", "")).startswith("PROMPT-"),
        "task_id": str(exp_record.get("task_id", "")).startswith("TASK-"),
        "adapter_not_configured": "not_configured" in adapter_path.read_text(encoding="utf-8"),
        "no_live_writeback": _scan_no_writeback(root),
    }
    if combined:
        checks["gsd_codex_install"] = (root / ".codex" / "get-shit-done" / "VERSION").is_file()
        checks["gsd_claude_install"] = (root / ".claude" / "get-shit-done" / "VERSION").is_file()
        checks["gsd_config"] = (root / ".planning" / "config.json").is_file()
    return checks


def _case_readme(case: dict[str, Any]) -> str:
    commands = "\n".join(f"- `{item}`" for item in case["command_sequence"])
    artifacts = "\n".join(f"- `{item}`" for item in case["expected_artifacts"])
    return (
        f"# {case['project_label']} - {case['adoption_path']}\n\n"
        f"Matrix version: `{MATRIX_VERSION}`\n\n"
        f"Returned experiment id: `{case['returned_exp_id']}`\n\n"
        "## Commands\n\n"
        f"{commands}\n\n"
        "## Expected Artifacts\n\n"
        f"{artifacts}\n\n"
        "## Failure Modes To Watch\n\n"
        f"- {case['failure_mode']}\n"
        "- missing adapters must remain `not_configured`, never PASS\n"
        "- no live writeback is performed by this example\n"
    )


def _run_case(
    *,
    repo: Path,
    workspace: Path,
    project: dict[str, str],
    adoption_path: str,
    skip_gsd_install: bool,
) -> dict[str, Any]:
    case_id = f"{project['id']}__{adoption_path}"
    root = workspace / case_id
    if root.exists():
        shutil.rmtree(root)
    _seed_project(root, project)
    commands: list[Receipt] = []
    checks: dict[str, Any] = {}
    python = sys.executable

    commands.append(_run("git_init", ["git", "init", "-q"], cwd=root))

    combined = adoption_path == "gsd_plus_gsigmad"
    gsd_status = "not_applicable"
    if combined:
        if skip_gsd_install or shutil.which("get-shit-done-cc") is None:
            gsd_status = "not_configured"
        else:
            commands.append(
                _run(
                    "get_shit_done_local_install",
                    ["get-shit-done-cc", "--codex", "--claude", "--local", "--profile=core"],
                    cwd=root,
                    timeout=300,
                )
            )
            commands.append(_run("gsd_config_new_project", ["gsd", "config-new-project"], cwd=root))
            gsd_status = "configured" if commands[-2].status == "PASS" else "failed"

    commands.append(_run("gsigmad_init", [python, "-m", "gsigmad", "--json", "init", str(root)], cwd=repo, timeout=240))
    adapter_path = _write_not_configured_adapter(root)
    commands.append(_run("status_before", [python, "-m", "gsigmad", "--json", "status"], cwd=root))
    commands.append(
        _run(
            "register",
            [
                python,
                "-m",
                "gsigmad",
                "--json",
                "register",
                "--type",
                "exploratory",
                "--hypothesis",
                project["hypothesis"],
                "--title",
                project["title"],
            ],
            cwd=root,
        )
    )
    exp_id = _registered_exp_id(commands[-1]) or "UNPARSED_EXP_ID"
    commands.append(_run("run_dry", [python, "-m", "gsigmad", "--json", "run", "--dry-run", exp_id], cwd=root))
    commands.append(_run("audit", [python, "-m", "gsigmad", "--json", "audit", exp_id, "--skip-citations"], cwd=root))
    commands.append(_run("redteam", [python, "-m", "gsigmad", "--json", "redteam", exp_id], cwd=root))
    commands.append(_run("status_after", [python, "-m", "gsigmad", "--json", "status"], cwd=root))

    if exp_id != "UNPARSED_EXP_ID":
        checks = _check_artifacts(root, exp_id, adapter_path, combined=combined)

    passed = all(item.status == "PASS" for item in commands) and all(checks.values())
    expected_artifacts = [
        ".gsigmad/config.yaml",
        ".gsigmad/LAB_NOTEBOOK.md",
        ".agents/skills/gsigmad/SKILL.md",
        ".claude/skills/gsigmad/SKILL.md",
        f".gsigmad/experiments/{exp_id}.yaml",
        "adapters/runtime/optional-overwatch.yaml",
    ]
    if combined:
        expected_artifacts.extend(
            [
                ".codex/get-shit-done/VERSION",
                ".claude/get-shit-done/VERSION",
                ".planning/config.json",
            ]
        )
    command_sequence = [
        "git init",
        "get-shit-done-cc --codex --claude --local --profile=core" if combined else "standalone gsigmad path",
        "gsigmad init .",
        "gsigmad status",
        "gsigmad register --type exploratory --hypothesis <project hypothesis>",
        f"gsigmad run --dry-run {exp_id}",
        f"gsigmad audit {exp_id} --skip-citations",
        f"gsigmad redteam {exp_id}",
    ]
    return {
        "case_id": case_id,
        "matrix_version": MATRIX_VERSION,
        "project_type": project["id"],
        "project_label": project["label"],
        "adoption_path": adoption_path,
        "passed": passed,
        "gsd_status": gsd_status,
        "returned_exp_id": exp_id,
        "returned_exp_id_used": all(exp_id in " ".join(item.command) for item in commands if item.name in {"run_dry", "audit", "redteam"}),
        "command_sequence": command_sequence,
        "expected_artifacts": expected_artifacts,
        "artifact_checks": checks,
        "failure_mode": project["failure_mode"],
        "commands": [asdict(item) for item in commands],
    }


def _kb_index(cases: list[dict[str, Any]], runtime: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "matrix_version": MATRIX_VERSION,
        "generated_for": "gsigmad public beta adoption examples",
        "use_cases": [
            {
                "use_case": case["project_type"],
                "adoption_path": case["adoption_path"],
                "commands": case["command_sequence"],
                "expected_artifacts": case["expected_artifacts"],
                "failure_modes": [
                    case["failure_mode"],
                    "missing adapters are not_configured, never PASS",
                    "no live writeback by default",
                    "use the returned EXP id",
                ],
            }
            for case in cases
        ],
        "runtime_examples": runtime,
    }


def _public_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        "created_at": receipt["created_at"],
        "matrix_version": receipt["matrix_version"],
        "passed": receipt["passed"],
        "case_count": receipt["case_count"],
        "workspace": receipt["workspace"],
        "cases": [
            {
                "case_id": case["case_id"],
                "passed": case["passed"],
                "returned_exp_id": case["returned_exp_id"],
                "returned_exp_id_used": case["returned_exp_id_used"],
                "gsd_status": case["gsd_status"],
                "command_statuses": [
                    {
                        "name": command["name"],
                        "returncode": command["returncode"],
                        "status": command["status"],
                    }
                    for command in case["commands"]
                ],
            }
            for case in receipt["cases"]
        ],
        "runtime_examples": receipt["runtime_examples"],
    }


def _write_corpus(repo: Path, cases: list[dict[str, Any]], runtime: dict[str, Any], receipt: dict[str, Any]) -> None:
    root = repo / "examples" / "projects"
    version_dir = root / MATRIX_VERSION
    if version_dir.exists():
        shutil.rmtree(version_dir)
    version_dir.mkdir(parents=True, exist_ok=True)

    public_cases = [
        {
            key: case[key]
            for key in [
                "case_id",
                "matrix_version",
                "project_type",
                "project_label",
                "adoption_path",
                "passed",
                "gsd_status",
                "returned_exp_id",
                "returned_exp_id_used",
                "command_sequence",
                "expected_artifacts",
                "artifact_checks",
                "failure_mode",
            ]
        }
        for case in cases
    ]
    matrix = {
        "schema_version": 1,
        "matrix_version": MATRIX_VERSION,
        "package_version": VERSION,
        "project_type_count": len(PROJECT_TYPES),
        "adoption_path_count": len(ADOPTION_PATHS),
        "case_count": len(public_cases),
        "runtime_examples": runtime,
        "cases": public_cases,
    }
    (root / "adoption_matrix.v1.2.0b1.json").write_text(json.dumps(matrix, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (root / "kb_index.v1.2.0b1.json").write_text(json.dumps(_kb_index(public_cases, runtime), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (root / "adoption_matrix_receipt.v1.2.0b1.json").write_text(
        json.dumps(_public_receipt(receipt), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    rows = "\n".join(
        f"| `{case['project_type']}` | `{case['adoption_path']}` | `{case['returned_exp_id']}` | {case['gsd_status']} | {'PASS' if case['passed'] else 'FAIL'} |"
        for case in public_cases
    )
    (root / "README.md").write_text(
        "# Project Adoption Examples\n\n"
        "Versioned public adoption corpus for `gsigmad 1.2.0b1`.\n\n"
        "These are sanitized receipts from fresh disposable repos. They prove the\n"
        "out-of-the-box local lifecycle and document expected artifacts; they are\n"
        "not scientific benchmark data.\n\n"
        "| Project type | Path | Returned EXP id | GSD status | Result |\n"
        "| --- | --- | --- | --- | --- |\n"
        f"{rows}\n\n"
        "- `adoption_matrix.v1.2.0b1.json` - machine-readable case matrix.\n"
        "- `kb_index.v1.2.0b1.json` - local KB index mapping use cases to commands, artifacts, and failure modes.\n"
        "- `v1.2.0b1/*/README.md` - per-case operator walkthroughs.\n",
        encoding="utf-8",
    )
    for case in public_cases:
        case_dir = version_dir / case["case_id"]
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "README.md").write_text(_case_readme(case), encoding="utf-8")


def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    repo = _repo_root()
    workspace = args.workspace.resolve() if args.workspace else Path(tempfile.mkdtemp(prefix="gsigmad-adoption-matrix-"))
    workspace.mkdir(parents=True, exist_ok=True)
    selected_projects = {args.project_filter} if args.project_filter else {item["id"] for item in PROJECT_TYPES}
    selected_paths = {args.path_filter} if args.path_filter else set(ADOPTION_PATHS)
    cases = [
        _run_case(
            repo=repo,
            workspace=workspace,
            project=project,
            adoption_path=path,
            skip_gsd_install=args.skip_gsd_install,
        )
        for project in PROJECT_TYPES
        if project["id"] in selected_projects
        for path in ADOPTION_PATHS
        if path in selected_paths
    ]
    runtime = _runtime_matrix()
    passed = all(case["passed"] for case in cases)
    receipt = {
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo": str(repo),
        "workspace": str(workspace),
        "matrix_version": MATRIX_VERSION,
        "passed": passed,
        "case_count": len(cases),
        "cases": cases,
        "runtime_examples": runtime,
    }
    (workspace / "adoption_matrix_smoke_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    if args.update_corpus:
        _write_corpus(repo, cases, runtime, receipt)
    return receipt


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, help="Directory for disposable repos and receipt output.")
    parser.add_argument("--update-corpus", action="store_true", help="Write sanitized examples/projects corpus into the repo.")
    parser.add_argument("--skip-gsd-install", action="store_true", help="Record GSD path as not_configured instead of invoking get-shit-done-cc.")
    parser.add_argument("--project-filter", choices=[item["id"] for item in PROJECT_TYPES], help="Run only one project type.")
    parser.add_argument("--path-filter", choices=list(ADOPTION_PATHS), help="Run only one adoption path.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    receipt = run_smoke(parse_args(argv or sys.argv[1:]))
    print(json.dumps(_public_receipt(receipt), indent=2, sort_keys=True))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
