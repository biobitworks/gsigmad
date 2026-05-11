"""Typed canonical anchor validation and file-backed loading helpers."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter, ValidationError
import yaml

ANCHOR_SCHEMA_NAME = "gsigmad-anchor-pack"
ANCHOR_SCHEMA_VERSION = 1


class AnchorValidationError(ValueError):
    """Raised when anchor configuration or document validation fails."""


class BaseAnchor(BaseModel):
    """Common fields shared by all canonical anchor references."""

    anchor_type: str
    anchor_id: str
    title: str
    source_path: str | None = None


class PaperAnchor(BaseAnchor):
    anchor_type: Literal["paper"]
    doi: str


class DatasetAnchor(BaseAnchor):
    anchor_type: Literal["dataset"]
    dataset_name: str
    field_name: str


class FigshareAnchor(BaseAnchor):
    anchor_type: Literal["figshare"]
    record_id: str
    file_name: str


class SupplementAnchor(BaseAnchor):
    anchor_type: Literal["supplement"]
    parent_anchor_id: str
    locator: str


class ZenodoAnchor(BaseAnchor):
    anchor_type: Literal["zenodo"]
    record_id: str
    resource_path: str


Anchor = Annotated[
    PaperAnchor | DatasetAnchor | FigshareAnchor | SupplementAnchor | ZenodoAnchor,
    Field(discriminator="anchor_type"),
]


class AnchorDocumentModel(BaseModel):
    """Top-level file-backed anchor document."""

    schema_name: Literal[ANCHOR_SCHEMA_NAME]
    schema_version: Literal[ANCHOR_SCHEMA_VERSION]
    anchors: list[Anchor]


@dataclass(frozen=True)
class LoadedAnchorDocument:
    """Normalized, typed anchor document returned by the loader."""

    path: Path
    relative_path: Path
    schema_name: str
    schema_version: int
    anchors: list[PaperAnchor | DatasetAnchor | FigshareAnchor | SupplementAnchor | ZenodoAnchor]


_ANCHOR_DOCUMENT_ADAPTER = TypeAdapter(AnchorDocumentModel)


def resolve_project_anchor_schema(config: dict[str, Any] | None) -> int | None:
    """Return the configured anchor schema version or ``None`` when opt-in is absent."""
    if not isinstance(config, dict):
        return None

    version = config.get("anchor_schema_version")
    if version is None:
        return None
    if not isinstance(version, int) or isinstance(version, bool):
        raise AnchorValidationError("anchor_schema_version must be an integer")
    if version != ANCHOR_SCHEMA_VERSION:
        raise AnchorValidationError(
            f"Unsupported anchor schema version: {version}. "
            f"Supported versions: [{ANCHOR_SCHEMA_VERSION}]"
        )
    return version


def load_anchor_document(project_root: Path, anchors_file: str | Path) -> LoadedAnchorDocument:
    """Load and validate one file-backed anchor document beneath ``project_root``."""
    root = project_root.resolve()
    relative_path = _normalize_anchor_path(root, anchors_file)
    full_path = root / relative_path

    if not full_path.is_file():
        raise AnchorValidationError(f"Anchor file not found: {relative_path}")

    try:
        payload = _load_anchor_payload(full_path)
    except AnchorValidationError:
        raise
    except Exception as exc:  # pragma: no cover - defensive fallback
        raise AnchorValidationError(
            f"Failed to load anchor file {relative_path}: {exc}"
        ) from exc

    try:
        document = _ANCHOR_DOCUMENT_ADAPTER.validate_python(payload)
    except ValidationError as exc:
        raise AnchorValidationError(_format_validation_error(exc)) from exc

    return LoadedAnchorDocument(
        path=full_path,
        relative_path=relative_path,
        schema_name=document.schema_name,
        schema_version=document.schema_version,
        anchors=document.anchors,
    )


def _normalize_anchor_path(project_root: Path, anchors_file: str | Path) -> Path:
    raw_path = Path(anchors_file)
    candidate = raw_path if raw_path.is_absolute() else (project_root / raw_path)
    resolved = candidate.resolve()

    try:
        relative = resolved.relative_to(project_root)
    except ValueError as exc:
        raise AnchorValidationError(
            f"Anchor file must stay within the project root: {raw_path}"
        ) from exc

    return relative


def _load_anchor_payload(path: Path) -> Any:
    suffix = path.suffix.lower()
    content = path.read_text(encoding="utf-8")

    if suffix in {".yaml", ".yml"}:
        return yaml.safe_load(content) or {}
    if suffix == ".json":
        return json.loads(content)
    raise AnchorValidationError(
        f"Unsupported anchor file format for {path.name}. Use .yaml, .yml, or .json."
    )


def _format_validation_error(exc: ValidationError) -> str:
    problems: list[str] = []
    for error in exc.errors():
        loc = ".".join(str(part) for part in error.get("loc", ()))
        message = error.get("msg", "Validation error")
        problems.append(f"{loc}: {message}")
    return "Anchor validation failed: " + "; ".join(problems)
