"""Working tree scaffolding for gsigmad project initialization.

Creates all directories and files that bundled skills reference in Pre-Flight.
Idempotent -- never overwrites existing user files.
"""
from __future__ import annotations

from pathlib import Path

# --- Template content for scaffold files ---

_PROMPT_EXP_MAP_HEADER = """# PROMPT-EXP Map

| PROMPT | EXP | Status | Notes |
|--------|-----|--------|-------|
"""

_NEGATIVE_RESULTS_HEADER = """# Negative Results Registry

| EXP | Hypothesis | Result | Forward-Link |
|-----|-----------|--------|--------------|
"""

_MISSION_ANCHOR_STUB = """# Mission Anchor

> Thesis: [TODO: state your project's central thesis]
> Primary metric: [TODO: define the metric that measures progress]
> Phase: initial
"""

_OLLARMA_CONTINUATION_STUB = """# Ollarma Continuation Policy

Use Ollarma as the bounded local completion lane when context pressure, token
exhaustion, or session interruption would otherwise leave a finishable task
half-done.

## Use Ollarma When

- The remaining task is bounded and operationally clear
- Inputs, constraints, and expected outputs are already known
- The work benefits from deterministic local execution with receipts or logs
- Handing off to another chat session would add more risk than running the
  bounded task locally

## Do Not Use Ollarma When

- The task still needs new strategic judgment or scope decisions
- The task would change thesis, protocol, or governance policy
- The task is irreversible and lacks explicit approval or attestation
- The task is better handled by a normal handoff than by bounded execution

## Required Handoff Fields

Before routing bounded completion to Ollarma, update `.agent/task.md` with:

1. The exact command to run
2. Expected receipt, log, or artifact paths
3. Stop condition / success condition
4. No-overlap guards (what Ollarma must not touch)
5. The exact human resume command after Ollarma finishes

## Fallback Rule

If Ollarma is unavailable or the task fails the suitability checks above, use
the normal `gsigmad-handoff` path instead of forcing execution.
"""

_TASK_STUB = """# Current Task

## Scope

[TODO: describe the current session scope]

## Objectives

- [ ] [TODO: first objective]

## Ollarma Continuation

Suitable: no
Command: not set

Expected artifacts:
- [TODO: artifact path]

Stop condition: [TODO: success condition]
Human resume command: [TODO: resume command]

No-overlap guards:
- [TODO: what Ollarma must not touch]
"""

_LAB_NOTEBOOK_ROOT_STUB = """# Lab Notebook

This file is a convenience pointer. The canonical lab notebook lives at
`.gsigmad/LAB_NOTEBOOK.md`. Append experiment entries there.
"""

# All directories that bundled skills expect
_DIRS = [
    "prompts",
    "experiments",
    "experiments/reviews",
    "experiments/fair",
    "experiments/pre-reg",
    "results",
    "scripts",
    ".agent",
    ".agent/conversation_digests",
    ".agent/drift_reports",
    ".agent/locks",
    "contracts",
    "notebooks",
    "null_models",
    "calibration",
]

# All files that bundled skills expect: (rel_path, content)
_FILES = [
    ("PROMPT_EXP_MAP.md", _PROMPT_EXP_MAP_HEADER),
    (".agent/task.md", _TASK_STUB),
    (".agent/MISSION_ANCHOR.md", _MISSION_ANCHOR_STUB),
    (".agent/OLLARMA_CONTINUATION.md", _OLLARMA_CONTINUATION_STUB),
    (".agent/next_prompt.txt", "1\n"),
    (".agent/next_exp.txt", "1\n"),
    (".agent/registered_reports.json", "{}"),
    ("experiments/NEGATIVE_RESULTS_REGISTRY.md", _NEGATIVE_RESULTS_HEADER),
    ("LAB_NOTEBOOK.md", _LAB_NOTEBOOK_ROOT_STUB),
]


def _ensure_dir(
    project_root: Path, rel_path: str, created: list[str], skipped: list[str]
) -> None:
    """Create directory if missing, track in appropriate list."""
    p = project_root / rel_path
    existed = p.is_dir()
    p.mkdir(parents=True, exist_ok=True)
    if existed:
        skipped.append(rel_path)
    else:
        created.append(rel_path)


def _ensure_file(
    project_root: Path, rel_path: str, content: str, created: list[str], skipped: list[str]
) -> None:
    """Write file only if it does not exist, track in appropriate list."""
    p = project_root / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        skipped.append(rel_path)
    else:
        p.write_text(content, encoding="utf-8")
        created.append(rel_path)


def scaffold_working_tree(project_root: Path) -> dict[str, list[str]]:
    """Create all files/dirs that bundled skills expect.

    Idempotent -- never overwrites existing user files.

    Returns dict with ``"created"`` and ``"skipped"`` lists of relative paths.
    """
    created: list[str] = []
    skipped: list[str] = []

    for rel in _DIRS:
        _ensure_dir(project_root, rel, created, skipped)

    for rel, content in _FILES:
        _ensure_file(project_root, rel, content, created, skipped)

    return {"created": created, "skipped": skipped}
