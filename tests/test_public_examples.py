"""Public documentation and Hugging Face example artifact checks."""
from __future__ import annotations

import json
from pathlib import Path

import yaml


def _frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    _, block, _ = text.split("---", 2)
    data = yaml.safe_load(block)
    assert isinstance(data, dict)
    return data


def test_quickstart_and_huggingface_examples_exist() -> None:
    repo = Path(__file__).resolve().parent.parent
    required = [
        repo / "docs" / "QUICKSTART.md",
        repo / "examples" / "huggingface" / "README.md",
        repo / "examples" / "huggingface" / "dataset" / "README.md",
        repo / "examples" / "huggingface" / "dataset" / "gate_traces.jsonl",
        repo / "examples" / "huggingface" / "space" / "README.md",
        repo / "examples" / "huggingface" / "space" / "index.html",
    ]

    for path in required:
        assert path.is_file(), path


def test_huggingface_dataset_card_and_rows_are_public_safe() -> None:
    repo = Path(__file__).resolve().parent.parent
    card = _frontmatter(repo / "examples" / "huggingface" / "dataset" / "README.md")
    assert card["license"] == "apache-2.0"
    assert "synthetic" in card["tags"]

    rows = [
        json.loads(line)
        for line in (repo / "examples" / "huggingface" / "dataset" / "gate_traces.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert {row["violation_category"] for row in rows} == {
        "citation_laundering",
        "vague_hypothesis",
        "evidence_class_inflation",
        "reproducibility_forgery",
        "post_hoc_h0_swap",
    }
    assert {row["claim_ceiling"] for row in rows} == {"DEMO_SYNTHETIC_ONLY"}
    assert all(row["deterministic_replicates"] == 10 for row in rows)
    assert all(row["unique_outputs"] == 1 for row in rows)


def test_huggingface_static_space_metadata() -> None:
    repo = Path(__file__).resolve().parent.parent
    card = _frontmatter(repo / "examples" / "huggingface" / "space" / "README.md")
    assert card["sdk"] == "static"
    assert card["app_file"] == "index.html"
    assert card["license"] == "apache-2.0"
