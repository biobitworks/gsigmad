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
        repo / "docs" / "COMPARISON.md",
        repo / "docs" / "PUBLIC_BENCHMARK_PLAN.md",
        repo / "docs" / "QUICKSTART.md",
        repo / "docs" / "RELEASE_DOI_PROCESS.md",
        repo / "docs" / "SCOPE_AND_ETHICS.md",
        repo / "examples" / "benchmark" / "README.md",
        repo / "examples" / "benchmark" / "bad_science_fixtures.jsonl",
        repo / "examples" / "benchmark" / "claim_boundary_corpus.jsonl",
        repo / "examples" / "benchmark" / "failure_taxonomy.md",
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


def test_public_benchmark_seed_covers_required_fixture_families() -> None:
    repo = Path(__file__).resolve().parent.parent
    rows = [
        json.loads(line)
        for line in (repo / "examples" / "benchmark" / "bad_science_fixtures.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert {row["violation_family"] for row in rows} == {
        "fake_or_non_resolving_citation",
        "vague_or_non_testable_hypothesis",
        "evidence_class_inflation",
        "reproducibility_declaration_without_replay_material",
        "post_hoc_hypothesis_swap",
        "missing_alpha_or_mesi",
        "bad_or_absent_data_contract",
        "absent_manifest",
        "missing_adapter",
        "drift_or_changed_classification_state",
    }
    assert {row["claim_ceiling"] for row in rows} == {"SYNTHETIC_GOVERNANCE_FIXTURE"}
    assert {row["pi_ratification_status"] for row in rows} == {"draft_public_seed"}
    assert all(row["deterministic_replicates"] == 10 for row in rows)
    assert all(row["unique_output_count"] == 1 for row in rows)


def test_public_claim_boundary_corpus_names_creative_and_deterministic_edges() -> None:
    repo = Path(__file__).resolve().parent.parent
    rows = [
        json.loads(line)
        for line in (repo / "examples" / "benchmark" / "claim_boundary_corpus.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    stages = {row["workflow_stage"] for row in rows}
    assert {
        "prompt_authoring",
        "experiment_design",
        "source_review",
        "results_interpretation",
        "redteam_remediation",
    }.issubset(stages)
    assert all(row["creative_inference_entry"] for row in rows)
    assert all(row["deterministic_gate_boundary"] for row in rows)
    assert all("validates" not in row["public_claim_language"].lower() for row in rows)


def test_huggingface_static_space_metadata() -> None:
    repo = Path(__file__).resolve().parent.parent
    card = _frontmatter(repo / "examples" / "huggingface" / "space" / "README.md")
    assert card["sdk"] == "static"
    assert card["app_file"] == "index.html"
    assert card["license"] == "apache-2.0"


def test_public_scope_docs_keep_claim_boundary() -> None:
    repo = Path(__file__).resolve().parent.parent
    scope = (repo / "docs" / "SCOPE_AND_ETHICS.md").read_text(encoding="utf-8")
    comparison = (repo / "docs" / "COMPARISON.md").read_text(encoding="utf-8")
    doi = (repo / "docs" / "RELEASE_DOI_PROCESS.md").read_text(encoding="utf-8")
    benchmark = (repo / "docs" / "PUBLIC_BENCHMARK_PLAN.md").read_text(encoding="utf-8")

    assert "not a truth machine" in scope
    assert "does not mean the claim is true" in scope
    assert "not a workflow engine" in comparison
    assert "This is not a claim of priority" in comparison
    assert "DOI-free rather than using a\nplaceholder" in doi
    assert "not yet a ratified benchmark dataset" in benchmark
    assert "bad_science_fixtures.jsonl" in benchmark
