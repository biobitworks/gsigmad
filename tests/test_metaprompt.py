"""Tests for FRM-02: budget-aware metaprompt compiler."""
import os
import pytest

from gsigmad.governance.compiler.metaprompt import assemble_metaprompt, BLOCK_REGISTRY
from gsigmad.governance.compiler.block_registry import CONTEXT_WINDOW, CONTEXT_BUDGET_FRACTION


def _write_required_blocks(tmp_path: pytest.TempPathFactory, mission_content: str = None, canon_content: str = None):
    """Helper: write the two required governance blocks into tmp_path."""
    agent_dir = tmp_path / ".agent"
    agent_dir.mkdir()
    gov_dir = tmp_path / "src" / "gsigmad" / "governance"
    gov_dir.mkdir(parents=True)

    mission_text = mission_content or "Thesis: Validate the budget enforcement system.\n"
    (agent_dir / "MISSION_ANCHOR.md").write_text(mission_text, encoding="utf-8")

    canon_text = canon_content or (
        "# CANON-CORE (Compact)\n\n"
        "## Universal Invariants\n\n"
        "### Invariant 1: No Fabricated Data\n"
        "Every datum must trace to a verifiable source.\n"
    )
    (gov_dir / "CANON-CORE-compact.md").write_text(canon_text, encoding="utf-8")


def test_block_assembly(tmp_path):
    """Compiler assembles all required blocks into a single prompt string."""
    _write_required_blocks(tmp_path)

    result = assemble_metaprompt(str(tmp_path))

    assert result["pass"] is True, f"Expected pass=True, got error: {result.get('error')}"
    assert "prompt" in result
    assert "token_counts" in result
    assert "MISSION_ANCHOR" in result["prompt"]
    assert "CANON_CORE" in result["prompt"]
    assert isinstance(result["token_counts"], dict)
    assert "MISSION_ANCHOR" in result["token_counts"]
    assert "CANON_CORE" in result["token_counts"]


def test_budget_exceeded(tmp_path):
    """Compiler aborts with METAPROMPT_CONTEXT_OVERFLOW when total governance blocks exceed 60% context window."""
    agent_dir = tmp_path / ".agent"
    agent_dir.mkdir()
    gov_dir = tmp_path / "src" / "gsigmad" / "governance"
    gov_dir.mkdir(parents=True)
    (agent_dir / "MISSION_ANCHOR.md").write_text("Thesis: test.\n", encoding="utf-8")
    (gov_dir / "CANON-CORE-compact.md").write_text(
        "# CANON-CORE (Compact)\n### Invariant 1\nTest invariant text here.\n", encoding="utf-8"
    )

    import gsigmad.governance.compiler.metaprompt as mp
    original_mp_window = mp.CONTEXT_WINDOW

    try:
        mp.CONTEXT_WINDOW = 10
        result = assemble_metaprompt(str(tmp_path))
    finally:
        mp.CONTEXT_WINDOW = original_mp_window

    assert result["pass"] is False, "Expected pass=False for overflow"
    assert result["error"].startswith("METAPROMPT_CONTEXT_OVERFLOW"), (
        f"Expected METAPROMPT_CONTEXT_OVERFLOW, got: {result['error']}"
    )


def test_block_budget_violation(tmp_path):
    """Compiler aborts with METAPROMPT_BUDGET_EXCEEDED when a single block exceeds its per-block token limit."""
    agent_dir = tmp_path / ".agent"
    agent_dir.mkdir()
    gov_dir = tmp_path / "src" / "gsigmad" / "governance"
    gov_dir.mkdir(parents=True)
    (agent_dir / "MISSION_ANCHOR.md").write_text("Thesis: test.\n", encoding="utf-8")

    import hashlib
    over_budget_content = " ".join(
        hashlib.md5(str(i).encode()).hexdigest() for i in range(100)
    )
    (gov_dir / "CANON-CORE-compact.md").write_text(over_budget_content, encoding="utf-8")

    result = assemble_metaprompt(str(tmp_path))

    assert result["pass"] is False, "Expected pass=False for budget violation"
    assert result["error"].startswith("METAPROMPT_BUDGET_EXCEEDED"), (
        f"Expected METAPROMPT_BUDGET_EXCEEDED, got: {result['error']}"
    )
    assert "CANON_CORE" in result["error"]


def test_missing_required_block(tmp_path):
    """Compiler aborts with METAPROMPT_MISSING_BLOCK when a required block file is absent."""
    result = assemble_metaprompt(str(tmp_path))

    assert result["pass"] is False, "Expected pass=False for missing required block"
    assert result["error"].startswith("METAPROMPT_MISSING_BLOCK"), (
        f"Expected METAPROMPT_MISSING_BLOCK, got: {result['error']}"
    )
    assert "MISSION_ANCHOR" in result["error"]


def test_optional_block_skipped_when_absent(tmp_path):
    """Compiler skips optional blocks gracefully (no error) when their file is absent."""
    _write_required_blocks(tmp_path)

    chain_digest_path = tmp_path / ".agent" / "CHAIN_DIGEST.md"
    assert not chain_digest_path.exists()

    result = assemble_metaprompt(str(tmp_path))

    assert result["pass"] is True, (
        f"Expected pass=True when optional blocks absent, got error: {result.get('error')}"
    )
    assert "CHAIN_DIGEST" not in result["token_counts"]
