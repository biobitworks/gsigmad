#!/usr/bin/env python3
"""Self-contained public-release guard for the gsigmad mirror.

Runs the BLOCK-class checks that can be enforced *inside* the public repo
without shipping the private upstream sanitization ruleset (which itself names
private portfolio projects and must never be published). It catches the
release blockers that are objective and content-revealing on their own:

* R-01  absolute user-home paths   (e.g. ``/Users/<name>/...``)        -> BLOCK
* internal runtime directories tracked into the public tree            -> BLOCK
* untracked files in the working tree (release must be a clean clone)  -> BLOCK

The full 17-rule scan -- including the private project-name FLAG list -- lives
in the private upstream (``scripts/release_gate_scan.py`` +
``SANITIZATION-RULES.json``) and is run there against this mirror before the
mirror is refreshed. This guard is the public-side backstop wired into CI and
the pre-push hook so a path/dir/untracked leak fails hard before push/tag.

Stdlib only. Usage::

    python3 scripts/release_guard.py [target-repo]   # defaults to repo root

Exit code 1 on any BLOCK finding; 0 when clean.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ABS_USER_PATH = re.compile(r"/Users/[A-Za-z0-9_.-]+")

# Internal runtime/state dirs that must never be tracked in the public mirror.
FORBIDDEN_TRACKED_DIRS = {
    ".planning",
    ".agent",
    ".antigence",
    ".gsigmad",
    ".artifacts",
    "experiments",
}

# Binary / bulky files that are not text-scanned.
SKIP_EXTENSIONS = {".whl", ".tar.gz", ".gz", ".zip", ".pyc", ".so", ".png", ".jpg", ".jpeg", ".pdf"}


def _git(root: Path, *args: str) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line]


def main(argv: list[str]) -> int:
    root = Path(argv[1]).resolve() if len(argv) > 1 else Path(__file__).resolve().parent.parent
    if not (root / ".git").exists():
        print(f"not a git repo: {root}", file=sys.stderr)
        return 2

    findings: list[dict[str, object]] = []

    tracked = _git(root, "ls-files")

    # 1. absolute user-home path leak in tracked text files
    for rel in tracked:
        if any(rel.endswith(ext) for ext in SKIP_EXTENSIONS):
            continue
        try:
            content = (root / rel).read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError):
            continue
        for m in ABS_USER_PATH.finditer(content):
            line_no = content.count("\n", 0, m.start()) + 1
            findings.append(
                {"rule": "R-01-abs-user-path", "file": rel, "line": line_no, "match": m.group(0)}
            )

    # 2. internal runtime dirs tracked into the public tree
    for rel in tracked:
        top = rel.split("/", 1)[0]
        if top in FORBIDDEN_TRACKED_DIRS:
            findings.append(
                {"rule": "internal-runtime-dir", "file": rel, "line": 0, "match": top}
            )

    # 3. untracked, non-ignored files (release must reflect a clean clone)
    for rel in _git(root, "ls-files", "--others", "--exclude-standard"):
        findings.append(
            {"rule": "untracked-release-file", "file": rel, "line": 0, "match": rel}
        )

    report = {"target": str(root), "block": len(findings), "findings": findings}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
