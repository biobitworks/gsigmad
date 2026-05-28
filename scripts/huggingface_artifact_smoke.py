#!/usr/bin/env python3
"""Local Hugging Face artifact smoke test for public gsigmad releases.

The smoke validates the public-safe dataset-card template, JSONL gate traces,
benchmark seed corpus, and static Space template without uploading anything to
Hugging Face. It writes a dry-run publish bundle and receipt to the workspace.
"""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import yaml


DATASET_REQUIRED_FIELDS = {
    "trial_id",
    "domain",
    "environment",
    "violation_category",
    "input_claim_summary",
    "expected_gate",
    "gate_status",
    "caught",
    "deterministic_replicates",
    "unique_outputs",
    "creative_inference_boundary",
    "claim_ceiling",
    "notes",
}

BENCHMARK_REQUIRED_FIELDS = {
    "fixture_id",
    "domain",
    "synthetic_fixture_text",
    "violation_family",
    "expected_gate",
    "expected_status",
    "observed_public_status",
    "observed_private_status",
    "deterministic_replicates",
    "unique_output_count",
    "runner_limitations",
    "claim_ceiling",
    "pi_ratification_status",
}

CLAIM_BOUNDARY_REQUIRED_FIELDS = {
    "boundary_id",
    "workflow_stage",
    "creative_inference_entry",
    "deterministic_gate_boundary",
    "allowed_claim_ceiling",
    "public_claim_language",
    "unsafe_claim_language",
    "domain",
}

REQUIRED_BENCHMARK_FAMILIES = {
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


@dataclass
class Check:
    name: str
    status: str
    detail: str | None = None


class _HTMLProbe(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.h1_count = 0
        self.table_count = 0
        self.external_scripts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if tag == "h1":
            self.h1_count += 1
        if tag == "table":
            self.table_count += 1
        if tag == "script" and attr_map.get("src"):
            self.external_scripts.append(attr_map["src"] or "")


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{path} does not start with YAML frontmatter")
    _, block, body = text.split("---", 2)
    data = yaml.safe_load(block)
    if not isinstance(data, dict):
        raise ValueError(f"{path} frontmatter is not a mapping")
    return data, body


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{lineno} is not a JSON object")
        rows.append(row)
    return rows


def _add(checks: list[Check], name: str, condition: bool, detail: str | None = None) -> None:
    checks.append(Check(name=name, status="PASS" if condition else "FAIL", detail=detail))


def _copy_publish_bundle(repo: Path, workspace: Path, checks: list[Check]) -> dict[str, Any]:
    bundle = workspace / "huggingface-publish-dry-run"
    if bundle.exists():
        shutil.rmtree(bundle)
    dataset = bundle / "dataset"
    space = bundle / "space"
    dataset.mkdir(parents=True)
    space.mkdir(parents=True)

    mappings = [
        (repo / "examples" / "huggingface" / "dataset" / "README.md", dataset / "README.md"),
        (repo / "examples" / "huggingface" / "dataset" / "gate_traces.jsonl", dataset / "gate_traces.jsonl"),
        (repo / "examples" / "benchmark" / "bad_science_fixtures.jsonl", dataset / "bad_science_fixtures.jsonl"),
        (repo / "examples" / "benchmark" / "claim_boundary_corpus.jsonl", dataset / "claim_boundary_corpus.jsonl"),
        (repo / "examples" / "benchmark" / "failure_taxonomy.md", dataset / "failure_taxonomy.md"),
        (repo / "examples" / "huggingface" / "space" / "README.md", space / "README.md"),
        (repo / "examples" / "huggingface" / "space" / "index.html", space / "index.html"),
    ]
    for source, target in mappings:
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        _add(checks, f"bundle_file:{target.relative_to(bundle)}", target.is_file(), str(target))

    manifest = {
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bundle": str(bundle),
        "network_upload": False,
        "dataset_files": sorted(path.name for path in dataset.iterdir() if path.is_file()),
        "space_files": sorted(path.name for path in space.iterdir() if path.is_file()),
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    repo = _repo_root()
    workspace = args.workspace.resolve() if args.workspace else Path(tempfile.mkdtemp(prefix="gsigmad-hf-artifacts-"))
    workspace.mkdir(parents=True, exist_ok=True)
    checks: list[Check] = []

    dataset_card = repo / "examples" / "huggingface" / "dataset" / "README.md"
    gate_traces_path = repo / "examples" / "huggingface" / "dataset" / "gate_traces.jsonl"
    space_card = repo / "examples" / "huggingface" / "space" / "README.md"
    space_index = repo / "examples" / "huggingface" / "space" / "index.html"
    benchmark_path = repo / "examples" / "benchmark" / "bad_science_fixtures.jsonl"
    boundary_path = repo / "examples" / "benchmark" / "claim_boundary_corpus.jsonl"

    dataset_meta, dataset_body = _frontmatter(dataset_card)
    _add(checks, "dataset_card_license", dataset_meta.get("license") == "apache-2.0")
    _add(checks, "dataset_card_synthetic_tag", "synthetic" in dataset_meta.get("tags", []))
    _add(checks, "dataset_card_has_configs", bool(dataset_meta.get("configs")))
    config_files = {
        item.get("path")
        for config in dataset_meta.get("configs", [])
        for item in config.get("data_files", [])
        if isinstance(item, dict)
    }
    _add(checks, "dataset_card_references_gate_traces", "gate_traces.jsonl" in config_files)
    _add(checks, "dataset_card_states_not_truth_machine", "validates scientific truth" in dataset_body)

    gate_rows = _jsonl(gate_traces_path)
    _add(checks, "gate_trace_rows_present", len(gate_rows) >= 5, str(len(gate_rows)))
    _add(checks, "gate_trace_schema", all(DATASET_REQUIRED_FIELDS <= row.keys() for row in gate_rows))
    _add(checks, "gate_trace_deterministic", all(row.get("deterministic_replicates") == 10 and row.get("unique_outputs") == 1 for row in gate_rows))
    _add(checks, "gate_trace_claim_ceiling", {row.get("claim_ceiling") for row in gate_rows} == {"DEMO_SYNTHETIC_ONLY"})

    benchmark_rows = _jsonl(benchmark_path)
    _add(checks, "benchmark_seed_rows_present", len(benchmark_rows) >= 10, str(len(benchmark_rows)))
    _add(checks, "benchmark_seed_schema", all(BENCHMARK_REQUIRED_FIELDS <= row.keys() for row in benchmark_rows))
    _add(checks, "benchmark_seed_family_coverage", {row.get("violation_family") for row in benchmark_rows} == REQUIRED_BENCHMARK_FAMILIES)
    _add(checks, "benchmark_seed_draft_only", {row.get("pi_ratification_status") for row in benchmark_rows} == {"draft_public_seed"})

    boundary_rows = _jsonl(boundary_path)
    _add(checks, "claim_boundary_rows_present", len(boundary_rows) >= 5, str(len(boundary_rows)))
    _add(checks, "claim_boundary_schema", all(CLAIM_BOUNDARY_REQUIRED_FIELDS <= row.keys() for row in boundary_rows))
    _add(checks, "claim_boundary_edges_recorded", all(row.get("creative_inference_entry") and row.get("deterministic_gate_boundary") for row in boundary_rows))

    space_meta, _ = _frontmatter(space_card)
    _add(checks, "space_sdk_static", space_meta.get("sdk") == "static")
    _add(checks, "space_app_file", space_meta.get("app_file") == "index.html")
    _add(checks, "space_license", space_meta.get("license") == "apache-2.0")
    _add(checks, "space_index_exists", (space_card.parent / str(space_meta.get("app_file"))).is_file())

    probe = _HTMLProbe()
    html = space_index.read_text(encoding="utf-8")
    probe.feed(html)
    _add(checks, "space_html_h1", probe.h1_count == 1, str(probe.h1_count))
    _add(checks, "space_html_table", probe.table_count >= 1, str(probe.table_count))
    _add(checks, "space_html_no_external_scripts", not probe.external_scripts, ",".join(probe.external_scripts))
    _add(checks, "space_html_no_network_fetch", "fetch(" not in html and "XMLHttpRequest" not in html)

    manifest = _copy_publish_bundle(repo, workspace, checks)
    passed = all(check.status == "PASS" for check in checks)
    receipt = {
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo": str(repo),
        "workspace": str(workspace),
        "passed": passed,
        "manifest": manifest,
        "checks": [asdict(check) for check in checks],
        "sources": [
            "https://huggingface.co/docs/hub/datasets-cards",
            "https://huggingface.co/docs/hub/main/spaces-sdks-static",
        ],
    }
    (workspace / "huggingface_artifact_smoke_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    return receipt


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, help="Directory for dry-run bundle and receipt output.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    receipt = run_smoke(parse_args(argv or []))
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
