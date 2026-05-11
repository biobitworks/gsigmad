"""Runtime manifest loading and project resolution for coexistence mode."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, Optional, Union

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from gsigmad.governance.control_plane_contract import (
    MUTATING_COMMANDS,
    RepoClass,
    infer_repo_class,
    validate_repo_class,
)
from gsigmad.governance.execution_contract import (
    DEFAULT_EXECUTION_CONTRACT_VERSION,
    validate_portfolio_role,
)

ADAPTER_MANIFEST_NAME = "gsigmad.adapter.yaml"
ADAPTER_REGISTRY_DIR = Path("adapters") / "runtime"
KNOWN_COMMANDS = (
    "status",
    "monitor",
    "register",
    "run",
    "audit",
    "redteam",
    "classify",
    "drift",
    "fair",
    "export",
    "report",
    "pause",
    "resume",
)
_MANIFEST_MODES = ("legacy", "gsigmad", "hybrid")
_COMMAND_MODES = ("legacy", "gsigmad", "hybrid", "unsupported")


class AdapterSurfaces(BaseModel):
    """Filesystem surfaces exposed by a coexistence target."""

    model_config = ConfigDict(extra="forbid")

    canon_path: Optional[str] = None
    experiments_dir: Optional[str] = None
    legacy_state_dir: Optional[str] = None
    lab_notebook_path: Optional[str] = None
    gsigmad_dir: Optional[str] = None


class RuntimeAdapterManifest(BaseModel):
    """Machine-readable coexistence manifest for one project."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    project_name: str
    project_root: str
    namespace_prefix: str
    runtime_mode: Literal["legacy", "gsigmad", "hybrid"]
    repo_class: Optional[str] = None
    portfolio_role: Optional[str] = None
    contract_version: Optional[str] = None
    surfaces: AdapterSurfaces = Field(default_factory=AdapterSurfaces)
    command_modes: dict[str, Literal["legacy", "gsigmad", "hybrid", "unsupported"]] = Field(
        default_factory=dict
    )
    notes: list[str] = Field(default_factory=list)

    @field_validator("project_root")
    @classmethod
    def _validate_project_root(cls, value: str) -> str:
        root = Path(value)
        if not root.is_absolute():
            raise ValueError("project_root must be an absolute path")
        return str(root.resolve())

    @field_validator("namespace_prefix")
    @classmethod
    def _validate_namespace_prefix(cls, value: str) -> str:
        namespace = value.strip()
        if not namespace.endswith(":"):
            raise ValueError("namespace_prefix must end with ':'")
        return namespace

    @field_validator("portfolio_role")
    @classmethod
    def _validate_portfolio_role(cls, value: Optional[str]) -> Optional[str]:
        return validate_portfolio_role(value)

    @field_validator("repo_class")
    @classmethod
    def _validate_repo_class(cls, value: Optional[str]) -> Optional[str]:
        return validate_repo_class(value)

    @field_validator("contract_version")
    @classmethod
    def _validate_contract_version(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        if normalized != DEFAULT_EXECUTION_CONTRACT_VERSION:
            raise ValueError(f"unsupported contract_version '{value}'")
        return normalized

    @field_validator("command_modes")
    @classmethod
    def _validate_command_modes(cls, value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for key, mode in value.items():
            command = str(key).strip()
            if not command:
                raise ValueError("command_modes keys must be non-empty")
            if command == "inspect":
                raise ValueError("inspect is built in and must not be overridden")
            if mode not in _COMMAND_MODES:
                raise ValueError(f"unsupported command mode '{mode}' for '{command}'")
            normalized[command] = mode
        return normalized

    @model_validator(mode="after")
    def _validate_contract_pairing(self) -> "RuntimeAdapterManifest":
        if self.portfolio_role and not self.contract_version:
            raise ValueError("contract_version is required when portfolio_role is set")
        if self.contract_version and not self.portfolio_role:
            raise ValueError("portfolio_role is required when contract_version is set")
        if self.repo_class == RepoClass.FROZEN.value:
            for command, mode in self.command_modes.items():
                if command in MUTATING_COMMANDS and mode != "unsupported":
                    raise ValueError(f"frozen repos cannot opt into mutating command '{command}'")
        return self


@dataclass
class ProjectResolution:
    """Resolved project target plus coexistence metadata."""

    target_path: Path
    project_root: Path
    project_name: str
    source: str
    runtime_mode: str
    repo_class: Optional[str]
    namespace_prefix: Optional[str]
    portfolio_role: Optional[str]
    contract_version: Optional[str]
    manifest_path: Optional[Path]
    command_modes: dict[str, str]
    surfaces: dict[str, Optional[str]]
    issues: list[str]
    notes: list[str]


def discover_registry_root(start: Optional[Union[Path, str]] = None) -> Optional[Path]:
    """Find the nearest ancestor that contains `adapters/runtime/`."""
    path = Path(start or Path.cwd()).resolve()
    candidates = [path] + list(path.parents)
    for candidate in candidates:
        if (candidate / ADAPTER_REGISTRY_DIR).is_dir():
            return candidate
    return None


def load_runtime_manifest(manifest_path: Union[Path, str]) -> RuntimeAdapterManifest:
    """Load and validate one runtime manifest."""
    path = Path(manifest_path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name}: manifest must be a YAML mapping")
    try:
        return RuntimeAdapterManifest.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"{path.name}: {exc}") from exc


def load_runtime_registry(
    registry_root: Optional[Union[Path, str]] = None,
) -> list[tuple[Path, RuntimeAdapterManifest]]:
    """Load all manifests from the runtime registry, if present."""
    root = Path(registry_root).resolve() if registry_root is not None else discover_registry_root()
    if root is None:
        return []

    manifests: list[tuple[Path, RuntimeAdapterManifest]] = []
    registry_dir = root / ADAPTER_REGISTRY_DIR
    for path in sorted(registry_dir.glob("*.yaml")):
        manifests.append((path, load_runtime_manifest(path)))
    return manifests


def resolve_project_target(
    target_path: Optional[Union[Path, str]] = None,
    *,
    registry_root: Optional[Union[Path, str]] = None,
) -> ProjectResolution:
    """Resolve a project target to native gsigmad, runtime manifest, or unresolved."""
    target = Path(target_path or Path.cwd()).resolve()
    if target.is_file():
        target = target.parent

    native_root = _find_native_gsigmad_root(target)
    if native_root is not None:
        return ProjectResolution(
            target_path=target,
            project_root=native_root,
            project_name=native_root.name,
            source="native_gsigmad",
            runtime_mode="gsigmad",
            repo_class=infer_repo_class("native_gsigmad", "gsigmad"),
            namespace_prefix=None,
            portfolio_role=None,
            contract_version=None,
            manifest_path=None,
            command_modes={},
            surfaces={
                "gsigmad_dir": str(native_root / ".gsigmad"),
            },
            issues=[],
            notes=["Native gsigmad project detected from on-disk .gsigmad/ layout."],
        )

    if registry_root is None:
        registry_root = discover_registry_root(target) or discover_registry_root()
    registry = load_runtime_registry(registry_root)
    matches: list[tuple[Path, RuntimeAdapterManifest]] = []
    for manifest_path, manifest in registry:
        project_root = Path(manifest.project_root)
        if target == project_root or _is_within(target, project_root):
            matches.append((manifest_path, manifest))

    if matches:
        matches.sort(key=lambda item: len(Path(item[1].project_root).parts), reverse=True)
        manifest_path, manifest = matches[0]
        issues: list[str] = []
        if len(matches) > 1:
            same_depth = [
                item for item in matches
                if len(Path(item[1].project_root).parts) == len(Path(manifest.project_root).parts)
            ]
            if len(same_depth) > 1:
                issues.append(
                    "Multiple runtime manifests match this target; chose the first manifest after lexical sort."
                )
        return ProjectResolution(
            target_path=target,
            project_root=Path(manifest.project_root),
            project_name=manifest.project_name,
            source="runtime_manifest",
            runtime_mode=manifest.runtime_mode,
            repo_class=infer_repo_class("runtime_manifest", manifest.runtime_mode, manifest.repo_class),
            namespace_prefix=manifest.namespace_prefix,
            portfolio_role=manifest.portfolio_role,
            contract_version=manifest.contract_version,
            manifest_path=manifest_path,
            command_modes=dict(manifest.command_modes),
            surfaces=_resolve_surfaces(manifest),
            issues=issues,
            notes=list(manifest.notes),
        )

    issues = [
        "No .gsigmad directory and no runtime manifest matched this path.",
        "Create adapters/runtime/<project>.yaml to route a legacy or hybrid project.",
    ]
    if (target / "experiments").is_dir():
        issues.insert(0, "Legacy-looking project detected from experiments/ without a coexistence manifest.")
    return ProjectResolution(
        target_path=target,
        project_root=target,
        project_name=target.name,
        source="unresolved",
        runtime_mode="unsupported",
        repo_class=None,
        namespace_prefix=None,
        portfolio_role=None,
        contract_version=None,
        manifest_path=None,
        command_modes={},
        surfaces={},
        issues=issues,
        notes=[],
    )


def command_mode_for(resolution: ProjectResolution, command: str) -> str:
    """Return the resolved runtime mode for a command."""
    normalized = str(command).strip()
    if normalized == "inspect":
        return resolution.runtime_mode
    if resolution.source == "native_gsigmad":
        return "gsigmad"
    if normalized in resolution.command_modes:
        return resolution.command_modes[normalized]
    if resolution.source == "runtime_manifest" and normalized in {"status", "monitor"}:
        return resolution.runtime_mode
    return "unsupported"


def build_compatibility_report(resolution: ProjectResolution) -> dict[str, object]:
    """Build a machine-readable compatibility report for operator inspection."""
    command_modes = {"inspect": resolution.runtime_mode}
    for command in KNOWN_COMMANDS:
        command_modes[command] = command_mode_for(resolution, command)
    supported = {key: value for key, value in command_modes.items() if value != "unsupported"}
    unsupported = sorted(key for key, value in command_modes.items() if value == "unsupported")
    return {
        "commands": command_modes,
        "supported_commands": supported,
        "unsupported_commands": unsupported,
    }


def inspect_payload(resolution: ProjectResolution) -> dict[str, object]:
    """Render a `ProjectResolution` as JSON-safe data."""
    compatibility = build_compatibility_report(resolution)
    return {
        "target_path": str(resolution.target_path),
        "project_root": str(resolution.project_root),
        "project_name": resolution.project_name,
        "source": resolution.source,
        "runtime_mode": resolution.runtime_mode,
        "repo_class": resolution.repo_class,
        "namespace_prefix": resolution.namespace_prefix,
        "portfolio_role": resolution.portfolio_role,
        "contract_version": resolution.contract_version,
        "manifest_path": str(resolution.manifest_path) if resolution.manifest_path else None,
        "surfaces": dict(resolution.surfaces),
        "issues": list(resolution.issues),
        "notes": list(resolution.notes),
        "compatibility": compatibility,
    }


def ensure_command_supported(resolution: ProjectResolution, command: str) -> str:
    """Return the mode for a command or raise an actionable error."""
    mode = command_mode_for(resolution, command)
    if mode != "unsupported":
        return mode

    compatibility = build_compatibility_report(resolution)
    supported = compatibility["supported_commands"]
    if supported:
        supported_text = ", ".join(f"{name}={value}" for name, value in supported.items())
    else:
        supported_text = "none"

    if resolution.manifest_path is not None:
        raise ValueError(
            f"Command '{command}' is not routed safely for {resolution.project_root}. "
            f"Supported commands: {supported_text}. "
            f"Update {resolution.manifest_path} command_modes to opt in."
        )

    raise ValueError(
        f"Command '{command}' is not routed safely for {resolution.project_root}. "
        f"Supported commands: {supported_text}. "
        "Run `gsigmad init` for a native project or add adapters/runtime/<project>.yaml for coexistence."
    )


def _find_native_gsigmad_root(target: Path) -> Optional[Path]:
    for candidate in [target] + list(target.parents):
        if (candidate / ".gsigmad").is_dir():
            return candidate
    return None


def _resolve_surfaces(manifest: RuntimeAdapterManifest) -> dict[str, Optional[str]]:
    root = Path(manifest.project_root)
    resolved: dict[str, Optional[str]] = {}
    for key, value in manifest.surfaces.model_dump().items():
        if value in (None, ""):
            resolved[key] = None
            continue
        path = Path(value)
        resolved[key] = str(path if path.is_absolute() else (root / path))
    return resolved


def _is_within(path: Path, candidate_root: Path) -> bool:
    try:
        path.relative_to(candidate_root)
        return True
    except ValueError:
        return False
