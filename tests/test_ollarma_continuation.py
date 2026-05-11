"""Tests for Ollarma continuation payload extraction."""
from __future__ import annotations

from pathlib import Path

from gsigmad.governance.ollarma_continuation import load_ollarma_continuation


def test_load_ollarma_continuation_parses_fields(tmp_path: Path):
    agent_dir = tmp_path / ".agent"
    agent_dir.mkdir()
    (agent_dir / "OLLARMA_CONTINUATION.md").write_text(
        "# Ollarma Continuation Policy\n\n"
        "Use Ollarma when a bounded task can finish locally.\n",
        encoding="utf-8",
    )
    (agent_dir / "task.md").write_text(
        "# Current Task\n\n"
        "## Ollarma Continuation\n\n"
        "- Command: `uv run python scripts/continue.py --limit 5`\n"
        "- Expected Artifacts: `results/run.json`, `logs/run.log`\n"
        "- Stop Condition: exit code 0 and artifacts are present\n"
        "- No-Overlap Guards:\n"
        "  - `.agent/locks/exp-001.lock`\n"
        "  - `prompts/PROMPT_12.md`\n"
        "- Human Resume Command: `gsigmad resume --project .`\n",
        encoding="utf-8",
    )

    payload = load_ollarma_continuation(tmp_path)

    assert payload["policy_present"] is True
    assert payload["task_present"] is True
    assert payload["suitable"] is True
    assert payload["task_fields"] == {
        "command": "uv run python scripts/continue.py --limit 5",
        "expected_artifacts": ["results/run.json", "logs/run.log"],
        "stop_condition": "exit code 0 and artifacts are present",
        "no_overlap_guards": [
            ".agent/locks/exp-001.lock",
            "prompts/PROMPT_12.md",
        ],
        "human_resume_command": "gsigmad resume --project .",
    }
    assert payload["missing_fields"] == []


def test_load_ollarma_continuation_flags_missing_policy(tmp_path: Path):
    agent_dir = tmp_path / ".agent"
    agent_dir.mkdir()
    (agent_dir / "task.md").write_text(
        "# Current Task\n\n"
        "## Ollarma Continuation\n\n"
        "- Command: `python -m gsigmad.run`\n"
        "- Expected Artifacts: `results/out.json`\n"
        "- Stop Condition: completion marker written\n"
        "- No-Overlap Guards: `.agent/locks/run.lock`\n"
        "- Human Resume Command: `gsigmad resume`\n",
        encoding="utf-8",
    )

    payload = load_ollarma_continuation(tmp_path)

    assert payload["policy_present"] is False
    assert payload["task_present"] is True
    assert payload["suitable"] is False
    assert payload["missing_fields"] == ["policy"]
