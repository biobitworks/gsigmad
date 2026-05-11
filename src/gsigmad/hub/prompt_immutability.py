"""Prompt immutability helpers for governed prompt-like artifacts."""
from __future__ import annotations

from typing import Any

from gsigmad.hub.ledger import hash_payload


def hash_prompt_artifact(payload: dict[str, Any]) -> str:
    """Return a deterministic hash for a prompt-like payload."""
    return hash_payload(payload)


def verify_prompt_hash(payload: dict[str, Any], expected_hash: str) -> dict[str, Any]:
    """Verify a prompt-like payload against a recorded hash."""
    actual_hash = hash_prompt_artifact(payload)
    return {
        "pass": actual_hash == expected_hash,
        "expected_hash": expected_hash,
        "actual_hash": actual_hash,
        "error": None if actual_hash == expected_hash else "PROMPT_HASH_MISMATCH",
    }


def build_prompt_artifact(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Build a governed prompt artifact with deterministic hash metadata."""
    return {
        "kind": kind,
        "hash_standard": "RFC8785",
        "hash_algorithm": "sha256",
        "hash": hash_prompt_artifact(payload),
        "payload": payload,
    }
