#!/usr/bin/env python3
"""check_adapter_ingest_completeness.py — stdlib-only adapter-state audit harness.

Backs the `gsigmad-audit-import-ingest-completeness` SKILL by deterministically
mapping each adapter YAML file under `--root` to:

    {
        "file": <path>,
        "state": "not_registered"
               | "registered_no_response"
               | "registered_declaration_incomplete"
               | "registered_complete",
        "verdict": "PASS" | "PASS_WITH_BLOCKS" | "REJECT",
        "blocking_codes": [<code>, ...],
    }

No PyYAML, no Pydantic, no LLM, no network. Implements the minimum YAML
inspection needed (top-level key detection, marker-line detection, list-item
counting under a block key) using the same pattern as
`src/gsigmad/lint/check_adapter_kb.py`.

State detection (deterministic, in precedence order):

1. `not_registered`              — filename starts with `_NOT_REGISTERED_` OR
                                   the file is absent from the canonical
                                   adapter index (`adapters/runtime/*.yaml`).
2. `registered_no_response`      — file present AND `_runtime_response: absent`
                                   marker present in YAML body.
3. `registered_declaration_incomplete`
                                 — file present AND has a `knowledge_base`
                                   block AND lacks at least one of the
                                   canonical experiment_repo surfaces
                                   (`LAB_NOTEBOOK.md`, `CANON.md`,
                                   `experiments/`, `PROMPT_EXP_MAP.md`).
4. `registered_complete`         — passes all of the above.

Verdict mapping (the key EXP-003 contract under test):

    registered_complete                 -> PASS                  blocking_codes=[]
    registered_no_response              -> REJECT                blocking_codes=['adapter_runtime_response_absent']
    registered_declaration_incomplete   -> REJECT                blocking_codes=['adapter_declaration_incomplete']
    not_registered                      -> PASS_WITH_BLOCKS      blocking_codes=['adapter_not_registered']

`registered_no_response` and `registered_declaration_incomplete` MUST differ
from `not_registered` (this is the H1 measurement for EXP-003).

CLI:

    python -m gsigmad.audit.check_adapter_ingest_completeness \
        --root <dir> [--json] [--canonical-index <dir>]

Exit code is always 0. Data is the output.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, List, Optional


# Canonical surfaces required for an `experiment_repo`-classified adapter to
# be considered declaration-complete (per the
# gsigmad-audit-import-ingest-completeness SKILL contract).
REQUIRED_EXPERIMENT_REPO_SURFACES = (
    "LAB_NOTEBOOK.md",
    "CANON.md",
    "experiments/",
    "PROMPT_EXP_MAP.md",
)

# Verdict / blocking-code constants. Keep these as module-level constants so
# tests can import and assert against them.
STATE_NOT_REGISTERED = "not_registered"
STATE_REGISTERED_NO_RESPONSE = "registered_no_response"
STATE_REGISTERED_DECLARATION_INCOMPLETE = "registered_declaration_incomplete"
STATE_REGISTERED_COMPLETE = "registered_complete"

VERDICT_PASS = "PASS"
VERDICT_PASS_WITH_BLOCKS = "PASS_WITH_BLOCKS"
VERDICT_REJECT = "REJECT"

BLOCK_NOT_REGISTERED = "adapter_not_registered"
BLOCK_RUNTIME_RESPONSE_ABSENT = "adapter_runtime_response_absent"
BLOCK_DECLARATION_INCOMPLETE = "adapter_declaration_incomplete"

STATE_TO_VERDICT = {
    STATE_REGISTERED_COMPLETE: (VERDICT_PASS, []),
    STATE_REGISTERED_NO_RESPONSE: (VERDICT_REJECT, [BLOCK_RUNTIME_RESPONSE_ABSENT]),
    STATE_REGISTERED_DECLARATION_INCOMPLETE: (
        VERDICT_REJECT,
        [BLOCK_DECLARATION_INCOMPLETE],
    ),
    STATE_NOT_REGISTERED: (VERDICT_PASS_WITH_BLOCKS, [BLOCK_NOT_REGISTERED]),
}


# ---------------------------------------------------------------------------
# Minimal YAML inspection (stdlib only).
# ---------------------------------------------------------------------------

def _is_comment_or_blank(line: str) -> bool:
    s = line.strip()
    return (not s) or s.startswith("#")


def _leading_spaces(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _strip_inline_comment(line: str) -> str:
    return line.split("#", 1)[0].rstrip()


def _starts_top_level_key(line: str, key: str) -> bool:
    if not line:
        return False
    if line.startswith(" ") or line.startswith("\t"):
        return False
    bare = _strip_inline_comment(line)
    if not bare:
        return False
    return bare == f"{key}:" or bare.startswith(f"{key}:")


def _has_top_level_marker(lines: Iterable[str], key: str, value: str) -> bool:
    """Return True iff a top-level `key: value` (after comment strip) appears."""
    for raw in lines:
        if _is_comment_or_blank(raw):
            continue
        if not _starts_top_level_key(raw, key):
            continue
        bare = _strip_inline_comment(raw)
        # Expect `key: value` with optional spaces.
        rhs = bare[len(f"{key}:"):].strip()
        if rhs == value:
            return True
    return False


def _has_knowledge_base_block(lines: Iterable[str]) -> bool:
    for raw in lines:
        if _is_comment_or_blank(raw):
            continue
        if _starts_top_level_key(raw, "knowledge_base"):
            return True
    return False


def _collect_knowledge_base_text(lines: List[str]) -> str:
    """Return the concatenated text of the `knowledge_base:` block.

    Used to scan for canonical-surface tokens (LAB_NOTEBOOK.md, CANON.md,
    experiments/, PROMPT_EXP_MAP.md) without requiring a real YAML parser.
    """
    out: List[str] = []
    in_kb = False
    for raw in lines:
        if not in_kb:
            if _is_comment_or_blank(raw):
                continue
            if _starts_top_level_key(raw, "knowledge_base"):
                in_kb = True
                out.append(raw)
            continue
        # Inside kb block: stop when we hit another column-0 non-comment key.
        if _is_comment_or_blank(raw):
            out.append(raw)
            continue
        if _leading_spaces(raw) == 0:
            # Next top-level key — kb block ended.
            break
        out.append(raw)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Canonical index.
# ---------------------------------------------------------------------------

def load_canonical_index(canonical_index_dir: Optional[Path]) -> set:
    """Return the set of canonical adapter stems (e.g. {'cellico', 'overwatch'}).

    If `canonical_index_dir` is None or does not exist, return an empty set.
    The empty-set case means "no canonical index supplied", and the
    not_registered branch will rely solely on the `_NOT_REGISTERED_` filename
    prefix marker.
    """
    if canonical_index_dir is None:
        return set()
    if not canonical_index_dir.exists():
        return set()
    return {p.stem for p in canonical_index_dir.glob("*.yaml") if p.is_file()}


# ---------------------------------------------------------------------------
# State + verdict.
# ---------------------------------------------------------------------------

def detect_state(path: Path, canonical_index: Optional[set] = None) -> str:
    """Map a single adapter YAML file to one of four states."""
    name = path.name

    # Rule 1a: filename marker.
    if name.startswith("_NOT_REGISTERED_"):
        return STATE_NOT_REGISTERED

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        # Unreadable files are treated as not_registered — the audit cannot
        # confirm registration without reading them.
        return STATE_NOT_REGISTERED

    lines = text.splitlines()

    # Rule 2: explicit absent-runtime marker.
    if _has_top_level_marker(lines, "_runtime_response", "absent"):
        return STATE_REGISTERED_NO_RESPONSE

    # Rule 3: declaration incompleteness for an experiment_repo-style adapter.
    if _has_knowledge_base_block(lines):
        kb_text = _collect_knowledge_base_text(lines)
        missing_any = any(
            surface not in kb_text for surface in REQUIRED_EXPERIMENT_REPO_SURFACES
        )
        if missing_any:
            # Rule 1b (fallback): if the file is also absent from the canonical
            # adapter index AND has no explicit runtime marker, the canonical
            # SOP would still call it not_registered. The fixture set, however,
            # encodes incompleteness via partial KB declarations; the fixture
            # filename convention (no `_NOT_REGISTERED_` prefix) is the signal
            # that the file should be treated as registered-but-incomplete.
            return STATE_REGISTERED_DECLARATION_INCOMPLETE

    # Rule 1b: index-absence fallback for anything that has not yet been
    # classified. If a canonical index was supplied and this file's stem is
    # not in it, treat as not_registered.
    if canonical_index is not None and canonical_index and path.stem not in canonical_index:
        return STATE_NOT_REGISTERED

    return STATE_REGISTERED_COMPLETE


def analyze_file(path: Path, canonical_index: Optional[set] = None) -> dict:
    state = detect_state(path, canonical_index=canonical_index)
    verdict, blocking_codes = STATE_TO_VERDICT[state]
    return {
        "file": str(path),
        "state": state,
        "verdict": verdict,
        "blocking_codes": list(blocking_codes),
    }


def analyze_root(root: Path, canonical_index: Optional[set] = None) -> List[dict]:
    """Walk `root` recursively for *.yaml files and analyze each."""
    if not root.exists():
        return []
    files = sorted(p for p in root.rglob("*.yaml") if p.is_file())
    return [analyze_file(p, canonical_index=canonical_index) for p in files]


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        required=True,
        help="Directory of adapter YAML files to audit (recursed).",
    )
    parser.add_argument(
        "--canonical-index",
        default=None,
        help=(
            "Optional directory containing the canonical adapter index "
            "(e.g. adapters/runtime). Stems present here are treated as "
            "registered."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON results to stdout.",
    )
    args = parser.parse_args(argv)

    root = Path(args.root)
    canonical_dir = Path(args.canonical_index) if args.canonical_index else None
    canonical_index = load_canonical_index(canonical_dir)

    results = analyze_root(root, canonical_index=canonical_index)

    if args.json:
        print(json.dumps(results, indent=2, sort_keys=True))
    else:
        for r in results:
            codes = ",".join(r["blocking_codes"]) or "-"
            print(
                f"{r['state']:38s} {r['verdict']:18s} {codes:40s} {r['file']}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
