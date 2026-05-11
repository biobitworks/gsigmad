"""Runtime adapter helpers for coexistence with legacy GSD projects."""

from gsigmad.governance.adapters.runtime import (
    ADAPTER_MANIFEST_NAME,
    KNOWN_COMMANDS,
    build_compatibility_report,
    command_mode_for,
    discover_registry_root,
    ensure_command_supported,
    inspect_payload,
    load_runtime_manifest,
    load_runtime_registry,
    resolve_project_target,
)

__all__ = [
    "ADAPTER_MANIFEST_NAME",
    "KNOWN_COMMANDS",
    "build_compatibility_report",
    "command_mode_for",
    "discover_registry_root",
    "ensure_command_supported",
    "inspect_payload",
    "load_runtime_manifest",
    "load_runtime_registry",
    "resolve_project_target",
]
