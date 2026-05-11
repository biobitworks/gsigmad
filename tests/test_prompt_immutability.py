"""Tests for prompt immutability helpers."""
from __future__ import annotations

from gsigmad.hub.prompt_immutability import (
    hash_prompt_artifact,
    verify_prompt_hash,
)


def test_hash_prompt_artifact_is_deterministic():
    """Equivalent payloads hash identically after canonicalization."""
    left = {"command": "register", "payload": {"h0": "no effect", "alpha": 0.05}}
    right = {"payload": {"alpha": 0.05, "h0": "no effect"}, "command": "register"}

    assert hash_prompt_artifact(left) == hash_prompt_artifact(right)


def test_verify_prompt_hash_detects_tampering():
    """Modified payloads fail verification against the original hash."""
    original = {"command": "register", "payload": {"h0": "no effect"}}
    expected_hash = hash_prompt_artifact(original)

    result = verify_prompt_hash(
        {"command": "register", "payload": {"h0": "effect exists"}},
        expected_hash,
    )

    assert result["pass"] is False
    assert result["error"] == "PROMPT_HASH_MISMATCH"
