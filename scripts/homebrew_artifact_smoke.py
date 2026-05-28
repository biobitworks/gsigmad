#!/usr/bin/env python3
"""Local Homebrew artifact smoke test for public gsigmad releases.

The current Homebrew surface is a formula template, not a publish-ready tap.
This smoke validates that the formula has the required Python-application
structure, that placeholder state is classified as deferred, and that a dry-run
tap bundle can be assembled without claiming install readiness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


FORMULA_PATH = Path("homebrew/gsigmad.rb")
README_PATH = Path("homebrew/README.md")
SHA256_RE = re.compile(r'^\s*sha256\s+"([0-9a-f]{64}|PLACEHOLDER_SHA256)"', re.MULTILINE)
RESOURCE_RE = re.compile(r'^\s*resource\s+"([^"]+)"\s+do', re.MULTILINE)
URL_RE = re.compile(r'^\s*url\s+"([^"]+)"', re.MULTILINE)


@dataclass
class Check:
    name: str
    status: str
    detail: str | None = None


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _add(checks: list[Check], name: str, condition: bool, detail: str | None = None) -> None:
    checks.append(Check(name=name, status="PASS" if condition else "FAIL", detail=detail))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _extract(pattern: re.Pattern[str], text: str) -> list[str]:
    return [match.group(1) for match in pattern.finditer(text)]


def _copy_tap_bundle(repo: Path, workspace: Path, checks: list[Check]) -> dict[str, Any]:
    bundle = workspace / "homebrew-tap-dry-run"
    if bundle.exists():
        shutil.rmtree(bundle)
    formula_dir = bundle / "Formula"
    formula_dir.mkdir(parents=True)
    copied_formula = formula_dir / "gsigmad.rb"
    copied_readme = bundle / "README.md"
    shutil.copy2(repo / FORMULA_PATH, copied_formula)
    shutil.copy2(repo / README_PATH, copied_readme)
    _add(checks, "bundle_formula_created", copied_formula.is_file(), str(copied_formula))
    _add(checks, "bundle_readme_created", copied_readme.is_file(), str(copied_readme))
    manifest = {
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bundle": str(bundle),
        "network_upload": False,
        "formula_sha256": _sha256(copied_formula),
        "files": [
            "Formula/gsigmad.rb",
            "README.md",
        ],
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    repo = _repo_root()
    workspace = args.workspace.resolve() if args.workspace else Path(tempfile.mkdtemp(prefix="gsigmad-homebrew-"))
    workspace.mkdir(parents=True, exist_ok=True)
    formula = repo / FORMULA_PATH
    readme = repo / README_PATH
    checks: list[Check] = []
    blockers: list[str] = []

    _add(checks, "formula_exists", formula.is_file(), str(formula))
    _add(checks, "readme_exists", readme.is_file(), str(readme))
    text = formula.read_text(encoding="utf-8")
    readme_text = readme.read_text(encoding="utf-8")

    urls = _extract(URL_RE, text)
    sha_values = _extract(SHA256_RE, text)
    resources = _extract(RESOURCE_RE, text)
    placeholder_sha = "PLACEHOLDER_SHA256" in sha_values
    has_real_sha = any(re.fullmatch(r"[0-9a-f]{64}", value) for value in sha_values)
    has_resources = bool(resources)
    pypi_url = any("files.pythonhosted.org/packages/source/g/gsigmad/" in url for url in urls)

    _add(checks, "formula_class", "class Gsigmad < Formula" in text)
    _add(checks, "formula_virtualenv_helper", "include Language::Python::Virtualenv" in text)
    _add(checks, "formula_desc", 'desc "Science governance CLI -- deterministic guardrails for probabilistic AI"' in text)
    _add(checks, "formula_homepage", 'homepage "https://github.com/biobitworks/gsigmad"' in text)
    _add(checks, "formula_license", 'license "Apache-2.0"' in text)
    _add(checks, "formula_python_dependency", 'depends_on "python@3.11"' in text or 'depends_on "python@3.12"' in text)
    _add(checks, "formula_virtualenv_install", "virtualenv_install_with_resources" in text)
    _add(checks, "formula_test_block", "test do" in text and 'system bin/"gsigmad", "--version"' in text)
    _add(checks, "formula_pypi_url_shape", pypi_url, ",".join(urls))
    _add(checks, "formula_sha256_declared", bool(sha_values), ",".join(sha_values))
    _add(checks, "readme_declares_deferred", "not yet published" in readme_text.lower() and "deferred" in readme_text.lower())
    _add(checks, "readme_blocks_live_install_claim", "brew install gsigmad" not in readme_text.lower())

    if placeholder_sha:
        blockers.append("replace_placeholder_sha256_with_pypi_sdist_hash")
    if not has_real_sha:
        blockers.append("publish_or_build_release_sdist_before_homebrew_audit")
    if not has_resources:
        blockers.append("generate_python_resource_stanzas")
    blockers.append("run_brew_audit_new_formula_and_brew_test_after_formula_update")

    publish_ready = pypi_url and has_real_sha and has_resources and not placeholder_sha
    readiness = "publish_ready" if publish_ready else "deferred_until_pypi_and_resources"
    _add(checks, "deferred_state_has_blockers", publish_ready or bool(blockers), ",".join(blockers))

    manifest = _copy_tap_bundle(repo, workspace, checks)
    passed = all(check.status == "PASS" for check in checks)
    receipt = {
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo": str(repo),
        "workspace": str(workspace),
        "passed": passed,
        "readiness": readiness,
        "publish_ready": publish_ready,
        "blockers": blockers if not publish_ready else [],
        "resources": resources,
        "manifest": manifest,
        "checks": [asdict(check) for check in checks],
        "sources": [
            "https://docs.brew.sh/Python-for-Formula-Authors",
            "https://docs.brew.sh/Formula-Cookbook",
        ],
    }
    (workspace / "homebrew_artifact_smoke_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    return receipt


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, help="Directory for dry-run tap and receipt output.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    receipt = run_smoke(parse_args(argv or []))
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
