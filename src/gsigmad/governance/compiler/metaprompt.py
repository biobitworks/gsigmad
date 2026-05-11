"""
Budget-aware metaprompt compiler — FRM-02.

Assembles named governance blocks from BLOCK_REGISTRY, enforces per-block token budgets,
and enforces the 60%-context-window total limit. Never truncates silently.

Pattern: gate-function returning {"pass": bool, ...} — consistent with governance/gates/*.py.
Reference: D-01 through D-05 decisions, RESEARCH.md Pattern 2.
"""
import os
import warnings
from pathlib import Path

from gsigmad.governance.compiler.block_registry import (
    BLOCK_REGISTRY,
    CONTEXT_WINDOW,
    CONTEXT_BUDGET_FRACTION,
)

# tiktoken with 4-char fallback (D-03)
try:
    import tiktoken
    _ENC = tiktoken.get_encoding("cl100k_base")

    def _count_tokens(text: str) -> int:
        return len(_ENC.encode(text))

    TIKTOKEN_AVAILABLE = True
except ImportError:
    warnings.warn(
        "tiktoken not installed — using 4-char/token approximation for budget enforcement",
        RuntimeWarning,
        stacklevel=2,
    )

    def _count_tokens(text: str) -> int:
        return max(1, len(text) // 4)

    TIKTOKEN_AVAILABLE = False


def assemble_metaprompt(
    project_root: str,
    phase: str = "default",
    classification: str = "SCIENCE",
) -> dict:
    """
    Load named governance blocks, enforce per-block token budgets,
    enforce 60% context window limit, return compiled text.

    Args:
        project_root: Absolute or relative path to the project root directory.
                      Block paths relative to the registry are resolved against this root.
        phase: Phase label included in the compiled prompt header (default: "default").
        classification: Classification label included in the compiled prompt header (default: "SCIENCE").

    Returns:
        {"pass": True, "prompt": str, "token_counts": dict}
        {"pass": False, "error": str}
    """
    blocks: dict = {}
    token_counts: dict = {}

    for block_name, config in BLOCK_REGISTRY.items():
        path_tmpl = config["path_template"]

        # Resolve {project_root} placeholder for project_extension block
        path = path_tmpl.format(project_root=project_root)

        # Resolve relative paths against project_root
        if not os.path.isabs(path):
            path = os.path.join(project_root, path)
        path = os.path.normpath(path)

        if not os.path.exists(path):
            if config["required"]:
                return {
                    "pass": False,
                    "error": (
                        f"METAPROMPT_MISSING_BLOCK: Required block '{block_name}' "
                        f"not found at '{config['path_template']}'. "
                        f"Create this file before running."
                    ),
                }
            continue  # optional block — skip silently

        with open(path, encoding="utf-8") as f:
            content = f.read()

        tokens = _count_tokens(content)
        limit = config["max_tokens"]
        if tokens > limit:
            return {
                "pass": False,
                "error": (
                    f"METAPROMPT_BUDGET_EXCEEDED: {block_name} used {tokens} tokens, "
                    f"limit is {limit}. Compress or summarize '{config['path_template']}' "
                    f"before assembly."
                ),
            }

        blocks[block_name] = content
        token_counts[block_name] = tokens

    total_governance_tokens = sum(token_counts.values())
    max_allowed = int(CONTEXT_WINDOW * CONTEXT_BUDGET_FRACTION)
    if total_governance_tokens > max_allowed:
        return {
            "pass": False,
            "error": (
                f"METAPROMPT_CONTEXT_OVERFLOW: governance blocks total "
                f"{total_governance_tokens} tokens exceeds 60% of context window "
                f"({max_allowed} tokens). Block counts: {token_counts}"
            ),
        }

    prompt = _format_prompt(blocks, phase, classification)
    return {"pass": True, "prompt": prompt, "token_counts": token_counts}


def _format_prompt(blocks: dict, phase: str, classification: str) -> str:
    """Format assembled blocks into a single prompt string with section headers."""
    sections = [
        f"<!-- Metaprompt compiled by Getting Science Done — phase={phase}, classification={classification} -->",
    ]
    for block_name, content in blocks.items():
        sections.append(f"\n## {block_name}\n\n{content}")
    return "\n".join(sections)
