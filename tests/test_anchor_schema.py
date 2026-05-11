"""Tests for file-backed canonical anchor validation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from gsigmad.governance.anchors import (
    AnchorValidationError,
    DatasetAnchor,
    FigshareAnchor,
    PaperAnchor,
    SupplementAnchor,
    ZenodoAnchor,
    load_anchor_document,
    resolve_project_anchor_schema,
)


def _anchor_payload() -> dict:
    return {
        "schema_name": "gsigmad-anchor-pack",
        "schema_version": 1,
        "anchors": [
            {
                "anchor_type": "paper",
                "anchor_id": "paper-main",
                "title": "Main paper",
                "doi": "10.1000/main-paper",
                "source_path": "papers/main.pdf",
            },
            {
                "anchor_type": "dataset",
                "anchor_id": "dataset-main",
                "title": "Primary dataset",
                "dataset_name": "clinical_signals",
                "field_name": "patient_id",
                "source_path": "data/clinical.csv",
            },
            {
                "anchor_type": "figshare",
                "anchor_id": "figshare-main",
                "title": "Figshare asset",
                "record_id": "123456",
                "file_name": "figure-1.csv",
                "source_path": "contracts/anchors/figshare.csv",
            },
            {
                "anchor_type": "supplement",
                "anchor_id": "supp-main",
                "title": "Supplementary appendix",
                "parent_anchor_id": "paper-main",
                "locator": "appendix/table-s1",
                "source_path": "supplements/table-s1.csv",
            },
            {
                "anchor_type": "zenodo",
                "anchor_id": "zenodo-main",
                "title": "Zenodo archive",
                "record_id": "7654321",
                "resource_path": "archive/results.tsv",
                "source_path": "contracts/anchors/zenodo.json",
            },
        ],
    }


@pytest.mark.parametrize("suffix", [".yaml", ".json"])
def test_load_anchor_document_validates_typed_yaml_and_json_payloads(tmp_path: Path, suffix: str) -> None:
    """Valid anchor docs load into typed models with preserved source metadata."""
    anchors_path = tmp_path / "contracts" / "anchors" / f"exp-anchors{suffix}"
    anchors_path.parent.mkdir(parents=True)
    payload = _anchor_payload()

    if suffix == ".json":
        anchors_path.write_text(json.dumps(payload), encoding="utf-8")
    else:
        anchors_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    loaded = load_anchor_document(tmp_path, anchors_path.relative_to(tmp_path))

    assert loaded.relative_path == Path("contracts/anchors") / f"exp-anchors{suffix}"
    assert loaded.schema_version == 1
    assert len(loaded.anchors) == 5
    assert isinstance(loaded.anchors[0], PaperAnchor)
    assert isinstance(loaded.anchors[1], DatasetAnchor)
    assert isinstance(loaded.anchors[2], FigshareAnchor)
    assert isinstance(loaded.anchors[3], SupplementAnchor)
    assert isinstance(loaded.anchors[4], ZenodoAnchor)
    assert loaded.anchors[0].source_path == "papers/main.pdf"
    assert loaded.anchors[4].source_path == "contracts/anchors/zenodo.json"


def test_load_anchor_document_raises_field_level_validation_errors(tmp_path: Path) -> None:
    """Malformed payloads should point at the broken field, not just fail generically."""
    anchors_path = tmp_path / "contracts" / "anchors" / "broken.yaml"
    anchors_path.parent.mkdir(parents=True)
    payload = _anchor_payload()
    payload["anchors"][0].pop("doi")
    payload["anchors"][1]["field_name"] = ["patient_id"]
    anchors_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(AnchorValidationError) as excinfo:
        load_anchor_document(tmp_path, "contracts/anchors/broken.yaml")

    message = str(excinfo.value)
    assert "anchors.0.paper.doi" in message
    assert "anchors.1.dataset.field_name" in message


def test_anchor_schema_version_requires_explicit_supported_metadata() -> None:
    """Missing config opt-in skips at the caller, unsupported config versions fail clearly."""
    assert resolve_project_anchor_schema({}) is None
    assert resolve_project_anchor_schema({"anchor_schema_version": None}) is None
    assert resolve_project_anchor_schema({"anchor_schema_version": 1}) == 1

    with pytest.raises(AnchorValidationError, match="Unsupported anchor schema version"):
        resolve_project_anchor_schema({"anchor_schema_version": 99})

    with pytest.raises(AnchorValidationError, match="anchor_schema_version must be an integer"):
        resolve_project_anchor_schema({"anchor_schema_version": "1"})


def test_load_anchor_document_rejects_missing_or_unsupported_schema_metadata(tmp_path: Path) -> None:
    """File-backed anchor docs must declare a supported schema version."""
    missing_schema_path = tmp_path / "contracts" / "anchors" / "missing-schema.yaml"
    missing_schema_path.parent.mkdir(parents=True)
    payload = _anchor_payload()
    payload.pop("schema_version")
    missing_schema_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(AnchorValidationError) as missing_exc:
        load_anchor_document(tmp_path, "contracts/anchors/missing-schema.yaml")
    assert "schema_version" in str(missing_exc.value)

    unsupported_schema_path = tmp_path / "contracts" / "anchors" / "unsupported-schema.yaml"
    payload = _anchor_payload()
    payload["schema_version"] = 99
    unsupported_schema_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(AnchorValidationError, match="schema_version"):
        load_anchor_document(tmp_path, "contracts/anchors/unsupported-schema.yaml")
