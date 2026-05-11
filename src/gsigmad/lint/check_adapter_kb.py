#!/usr/bin/env python3
"""check_adapter_kb.py — stdlib-only adapter knowledge_base lint.

Walks `adapters/runtime/*.yaml` (or any --root) and emits, per file:
    {
        "file": <path>,
        "has_kb_block": <bool>,
        "sources_count": <int>,
        "status": "ok" | "KB_DECLARATION_MISSING" | "KB_SOURCES_EMPTY",
    }

No PyYAML dependency. Implements minimal top-level-key detection:
- Finds non-comment lines whose column-0 character begins `knowledge_base:`.
- If found, scans the indented block that follows for a `sources:` key and
  determines whether that key has a non-empty list under it.

Exit code is always 0; the data is the output. Emit JSON when --json is set;
otherwise emit a human-readable summary.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _is_comment_or_blank(line: str) -> bool:
    s = line.strip()
    return (not s) or s.startswith("#")


def _leading_spaces(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _starts_top_level_key(line: str, key: str) -> bool:
    # Top-level: column 0, not indented, not comment, of form `key:` or `key: ...`.
    if not line:
        return False
    if line.startswith(" ") or line.startswith("\t"):
        return False
    s = line.rstrip("\n")
    if s.startswith("#"):
        return False
    # remove trailing comment
    bare = s.split("#", 1)[0].rstrip()
    return bare == f"{key}:" or bare.startswith(f"{key}:")


def analyze_file(path: Path) -> dict:
    has_kb_block = False
    sources_count = 0
    sources_seen = False
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {
            "file": str(path),
            "has_kb_block": False,
            "sources_count": 0,
            "status": "KB_DECLARATION_MISSING",
        }

    lines = text.splitlines()
    in_kb = False
    kb_indent = None
    in_sources = False
    sources_indent = None

    for line in lines:
        if _is_comment_or_blank(line):
            continue
        indent = _leading_spaces(line)
        if not in_kb:
            if _starts_top_level_key(line, "knowledge_base"):
                has_kb_block = True
                in_kb = True
                kb_indent = indent  # 0
                # Inline form `knowledge_base: []` would be empty.
                bare = line.split("#", 1)[0].rstrip()
                inline = bare[len("knowledge_base:"):].strip()
                if inline in ("[]", "{}"):
                    # empty kb block; sources trivially empty
                    return {
                        "file": str(path),
                        "has_kb_block": True,
                        "sources_count": 0,
                        "status": "KB_SOURCES_EMPTY",
                    }
                continue
        else:
            # Inside the kb block until we hit another column-0 key.
            if indent == 0 and not _is_comment_or_blank(line):
                # Left the kb block.
                break
            # Looking for `sources:` at indent > 0 within kb block.
            if not in_sources:
                bare = line.split("#", 1)[0].rstrip()
                stripped = bare.strip()
                if stripped.startswith("sources:"):
                    sources_seen = True
                    in_sources = True
                    sources_indent = indent
                    inline = stripped[len("sources:"):].strip()
                    if inline == "[]":
                        sources_count = 0
                        in_sources = False
                    elif inline and inline != "":
                        # inline non-empty (rare) — treat as 1
                        sources_count = 1
                        in_sources = False
                    continue
            else:
                # Inside sources list. Count list items: lines whose indent
                # is greater than sources_indent and whose first non-space
                # char is `-`.
                if indent <= sources_indent:
                    in_sources = False
                else:
                    s = line.lstrip(" ")
                    if s.startswith("- "):
                        sources_count += 1

    if not has_kb_block:
        status = "KB_DECLARATION_MISSING"
    elif sources_count == 0:
        status = "KB_SOURCES_EMPTY"
    else:
        status = "ok"

    return {
        "file": str(path),
        "has_kb_block": has_kb_block,
        "sources_count": sources_count,
        "status": status,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="adapters/runtime",
                        help="Directory of adapter YAML files (default: adapters/runtime).")
    parser.add_argument("--json", action="store_true",
                        help="Emit JSON results.")
    args = parser.parse_args(argv)

    root = Path(args.root)
    if not root.exists():
        sys.stderr.write(f"warning: root does not exist: {root}\n")
        if args.json:
            print(json.dumps([], indent=2))
        return 0

    yaml_files = sorted(p for p in root.glob("*.yaml") if p.is_file())
    results = [analyze_file(p) for p in yaml_files]

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            print(f"{r['status']:30s} sources={r['sources_count']:<3d} {r['file']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
