"""Cross-model command parity runtime for bounded governance smoke checks."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from shutil import which
from typing import Any

import yaml

from gsigmad import __version__
from gsigmad.governance.adapters import load_runtime_manifest

SCHEMA_VERSION = "1.0"
DEFAULT_SCENARIO = "command-parity"
TRUST_HANDOFF_SCENARIO = "trust-handoff"
SCENARIO_MATRIX_VERSIONS = {
    DEFAULT_SCENARIO: "phase14-v1",
    TRUST_HANDOFF_SCENARIO: "phase15-v1",
}
MATRIX_VERSION = SCENARIO_MATRIX_VERSIONS[DEFAULT_SCENARIO]
SCENARIO_REQUIREMENTS = {
    DEFAULT_SCENARIO: "PARITY-01",
    TRUST_HANDOFF_SCENARIO: "PARITY-02",
}
SANITIZER_VERSION = "1.0"
CLASSIFIER_VERSION = "1.0"
DEFAULT_LOCAL_MODEL = "qwen2.5-coder:7b"
DEFAULT_LANES = ("claude", "codex", "ollama")
DEFAULT_TIMEOUT_SECONDS = 90
DEFAULT_ARTIFACT_ROOT = Path(".artifacts") / "parity"
TRUST_HANDOFF_ARTIFACT_ROOT = DEFAULT_ARTIFACT_ROOT / "trust-handoff"
REPLAY_FIXTURE_DIR = Path(".fixtures/parity/replay")
_RAW_FILE_LIMIT = 16_000
_REDACTION_PATTERNS = (
    re.compile(r"\b(sk-[A-Za-z0-9_-]{8,})\b"),
    re.compile(r"\b(sk-ant-[A-Za-z0-9_-]{8,})\b"),
    re.compile(r"\b(ghp_[A-Za-z0-9]{8,})\b"),
    re.compile(r"\b(AKIA[0-9A-Z]{8,})\b"),
    re.compile(r"(?im)^(authorization:\s*)(.+)$"),
)
_AUTH_MARKERS = (
    "credit balance is too low",
    "not authenticated",
    "authentication required",
    "invalid api key",
    "missing api key",
    "unauthorized",
    "401",
    "403",
    "please run",
    "set openai_api_key",
    "set anthropic_api_key",
)
_NETWORK_MARKERS = (
    "connection refused",
    "timed out",
    "timeout",
    "transport",
    "network",
    "service unavailable",
    "operation not permitted",
    "connection reset",
    "failed to connect",
    "provider",
)
_IGNORE_COPY_PATTERNS = (
    ".git",
    ".venv",
    ".pytest_cache",
    "__pycache__",
    ".artifacts",
    "*.pyc",
)


@dataclass(frozen=True)
class MatrixRow:
    """One parity matrix row."""

    row_id: str
    command: tuple[str, ...]
    target_fixture: str
    expected_outcome: str
    normalized_fields: tuple[str, ...]


@dataclass(frozen=True)
class PreparedFixture:
    """Disposable parity fixture rooted under one parity run."""

    fixture_id: str
    project_root: Path
    registry_root: Path
    manifest_path: Path | None
    source_root: Path
    runtime_mode: str


DEFAULT_MATRIX: tuple[MatrixRow, ...] = (
    MatrixRow(
        row_id="row-01",
        command=("inspect",),
        target_fixture="self_fixture",
        expected_outcome="success",
        normalized_fields=(
            "runtime_mode",
            "source",
            "namespace_prefix",
            "compatibility.commands.status",
            "compatibility.commands.monitor",
        ),
    ),
    MatrixRow(
        row_id="row-02",
        command=("inspect",),
        target_fixture="shadow_seeds_fixture",
        expected_outcome="success",
        normalized_fields=(
            "runtime_mode",
            "source",
            "namespace_prefix",
            "compatibility.commands.status",
            "compatibility.commands.monitor",
        ),
    ),
    MatrixRow(
        row_id="row-03",
        command=("status",),
        target_fixture="self_fixture",
        expected_outcome="success",
        normalized_fields=(
            "routing.runtime_mode",
            "routing.source",
            "experiments.pass",
            "drift.pass",
            "drift.error",
            "closure",
        ),
    ),
    MatrixRow(
        row_id="row-04",
        command=("status",),
        target_fixture="shadow_seeds_fixture",
        expected_outcome="success",
        normalized_fields=(
            "routing.runtime_mode",
            "routing.source",
            "experiments.pass",
            "drift.pass",
            "drift.error",
            "closure",
        ),
    ),
    MatrixRow(
        row_id="row-05",
        command=("monitor", "summary"),
        target_fixture="self_fixture",
        expected_outcome="success",
        normalized_fields=(
            "current.routing.runtime_mode",
            "current.routing.source",
            "current.summary.pass",
            "history.count",
            "open_alert",
        ),
    ),
    MatrixRow(
        row_id="row-06",
        command=("monitor", "summary"),
        target_fixture="shadow_seeds_fixture",
        expected_outcome="success",
        normalized_fields=(
            "current.routing.runtime_mode",
            "current.routing.source",
            "current.summary.pass",
            "history.count",
            "open_alert",
        ),
    ),
    MatrixRow(
        row_id="row-07",
        command=("run",),
        target_fixture="shadow_seeds_fixture",
        expected_outcome="pre_dispatch_failure",
        normalized_fields=(
            "exit_code",
            "failure_class",
            "error_identifier",
            "pre_dispatch_rejection",
        ),
    ),
)

TRUST_HANDOFF_MATRIX: tuple[dict[str, Any], ...] = (
    {
        "row_id": "row-01",
        "display_command": "trust-handoff provisional-write-native self_fixture",
        "probe_kind": "provisional-write",
        "target_fixture": "self_fixture",
        "expected_outcome": "success",
        "normalized_fields": (
            "exit_code",
            "failure_class",
            "error_identifier",
            "trust_tier",
            "write_attempted",
        ),
    },
    {
        "row_id": "row-02",
        "display_command": "trust-handoff provisional-write-routed shadow_seeds_fixture",
        "probe_kind": "provisional-write",
        "target_fixture": "shadow_seeds_fixture",
        "expected_outcome": "success",
        "normalized_fields": (
            "exit_code",
            "failure_class",
            "error_identifier",
            "trust_tier",
            "write_attempted",
        ),
    },
    {
        "row_id": "row-03",
        "display_command": "trust-handoff promotion-without-countersignature self_fixture",
        "probe_kind": "promotion-without-countersignature",
        "target_fixture": "self_fixture",
        "expected_outcome": "success",
        "normalized_fields": (
            "failure_class",
            "error_identifier",
            "validation_pass",
            "pi_countersignature_present",
            "amendment_file",
            "metadata_keys",
        ),
    },
    {
        "row_id": "row-04",
        "display_command": "trust-handoff promotion-with-countersignature self_fixture",
        "probe_kind": "promotion-with-countersignature",
        "target_fixture": "self_fixture",
        "expected_outcome": "success",
        "normalized_fields": (
            "failure_class",
            "error_identifier",
            "validation_pass",
            "pi_countersignature_present",
            "amendment_file",
            "metadata_keys",
        ),
    },
    {
        "row_id": "row-05",
        "display_command": "trust-handoff handoff-round-trip-native self_fixture",
        "probe_kind": "handoff-round-trip",
        "target_fixture": "self_fixture",
        "expected_outcome": "success",
        "normalized_fields": (
            "checkpoint_written",
            "checkpoint_loaded",
            "coordinate",
            "recommended_command",
            "open_chain_count",
        ),
    },
    {
        "row_id": "row-06",
        "display_command": "trust-handoff handoff-round-trip-routed shadow_seeds_fixture",
        "probe_kind": "handoff-round-trip",
        "target_fixture": "shadow_seeds_fixture",
        "expected_outcome": "success",
        "normalized_fields": (
            "checkpoint_written",
            "checkpoint_loaded",
            "coordinate",
            "recommended_command",
            "open_chain_count",
        ),
    },
)


def _load_replay_fixtures(
    lane: str,
    scenario: str,
    *,
    fixture_dir: Path | None = None,
) -> dict[str, Any]:
    """Load pre-authored replay fixtures for one lane+scenario combination.

    Returns the parsed dict (keys: ``preflight``, ``rows``) when the fixture
    file exists, or an empty dict when it does not.
    """
    base = fixture_dir or REPLAY_FIXTURE_DIR
    fixture_path = base / f"{lane}-{scenario}.json"
    if not fixture_path.exists():
        return {}
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def run_parity(
    *,
    repo_root: Path | str | None = None,
    lanes: list[str] | tuple[str, ...] | None = None,
    local_model: str = DEFAULT_LOCAL_MODEL,
    native: str = "self_fixture",
    routed: str = "shadow_seeds_fixture",
    scenario: str = DEFAULT_SCENARIO,
    artifact_root: Path | str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    replay_lanes: set[str] | None = None,
    replay_fixture_dir: Path | None = None,
) -> dict[str, Any]:
    """Run one bounded parity scenario and persist the report artifact."""
    repo = Path(repo_root or Path.cwd()).resolve()
    normalized_scenario = _normalize_scenario(scenario)
    artifact_path = Path(artifact_root or _default_artifact_root(normalized_scenario)).resolve()
    artifact_path.mkdir(parents=True, exist_ok=True)
    run_id = _build_run_id(normalized_scenario)
    run_root = artifact_path / "work" / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    selected_lanes = _normalize_lanes(lanes)
    prepared = prepare_fixtures(
        repo_root=repo,
        native=native,
        routed=routed,
        run_root=run_root,
    )
    matrix = materialize_matrix(
        prepared,
        scenario=normalized_scenario,
        repo_root=repo,
        run_root=run_root,
    )
    lane_binaries = _collect_lane_binaries(local_model=local_model)
    results: dict[str, Any] = {}

    for lane in selected_lanes:
        preflight = preflight_lane(
            lane,
            run_root=run_root,
            local_model=local_model,
            timeout_seconds=min(timeout_seconds, 30),
            lane_binaries=lane_binaries,
            replay_lanes=replay_lanes,
            scenario=normalized_scenario,
            replay_fixture_dir=replay_fixture_dir,
        )
        lane_result = {
            "status": preflight["status"],
            "preflight": preflight,
            "rows": [],
        }
        if preflight["status"] == "ready":
            for row in matrix:
                row_result = execute_matrix_row(
                    lane=lane,
                    row=row,
                    repo_root=repo,
                    run_root=run_root,
                    local_model=local_model,
                    lane_binaries=lane_binaries,
                    artifact_root=artifact_path,
                    timeout_seconds=timeout_seconds,
                    replay_lanes=replay_lanes,
                    replay_fixture_dir=replay_fixture_dir,
                    scenario=normalized_scenario,
                )
                lane_result["rows"].append(row_result)
            if any(item["status"] == "degraded" for item in lane_result["rows"]):
                lane_result["status"] = "degraded"
        results[lane] = lane_result

    mismatches = compare_results(matrix, results)
    degraded_lanes = sorted(
        lane for lane, lane_result in results.items() if lane_result["status"] != "ready"
    )
    git_commit = _git_commit(repo)
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "git_commit": git_commit,
        "gsigmad_version": __version__,
        "scenario": normalized_scenario,
        "phase_requirement": SCENARIO_REQUIREMENTS[normalized_scenario],
        "lanes": selected_lanes,
        "local_model": local_model,
        "lane_binaries": lane_binaries,
        "matrix_version": SCENARIO_MATRIX_VERSIONS[normalized_scenario],
        "matrix": [
            {
                "id": row["id"],
                "command": row["command"],
                "target_fixture": row["target_fixture"],
                "expected_outcome": row["expected_outcome"],
                "normalized_fields": row["normalized_fields"],
            }
            for row in matrix
        ],
        "environment_allowlist": _environment_allowlist(),
        "fixtures": {
            key: {
                "fixture_id": value.fixture_id,
                "project_root": str(value.project_root),
                "registry_root": str(value.registry_root),
                "manifest_path": str(value.manifest_path) if value.manifest_path else None,
                "source_root": str(value.source_root),
                "runtime_mode": value.runtime_mode,
            }
            for key, value in prepared.items()
        },
        "results": results,
        "mismatches": mismatches,
        "degraded_lanes": degraded_lanes,
    }
    write_report(report, artifact_root=artifact_path, run_id=run_id)
    return report


def prepare_fixtures(
    *,
    repo_root: Path,
    native: str,
    routed: str,
    run_root: Path,
) -> dict[str, PreparedFixture]:
    """Materialize disposable fixtures under one parity run root."""
    fixtures_root = run_root / "fixtures"
    registry_root = run_root
    (registry_root / "adapters" / "runtime").mkdir(parents=True, exist_ok=True)

    native_fixture = _prepare_native_fixture(
        repo_root=repo_root,
        native=native,
        fixtures_root=fixtures_root,
        registry_root=registry_root,
    )
    routed_fixture = _prepare_routed_fixture(
        repo_root=repo_root,
        routed=routed,
        fixtures_root=fixtures_root,
        registry_root=registry_root,
    )
    return {
        native_fixture.fixture_id: native_fixture,
        routed_fixture.fixture_id: routed_fixture,
    }


def materialize_matrix(
    fixtures: dict[str, PreparedFixture],
    *,
    scenario: str = DEFAULT_SCENARIO,
    repo_root: Path | None = None,
    run_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Expand one parity scenario with concrete fixture paths."""
    rows: list[dict[str, Any]] = []
    normalized_scenario = _normalize_scenario(scenario)
    runtime_root = run_root or Path.cwd()

    if normalized_scenario == DEFAULT_SCENARIO:
        for spec in DEFAULT_MATRIX:
            fixture = fixtures[spec.target_fixture]
            row_command = ("python3", "-m", "gsigmad", "--json", *spec.command, str(fixture.project_root))
            rows.append(
                {
                    "id": spec.row_id,
                    "command": list(row_command),
                    "display_command": " ".join(spec.command) + f" {spec.target_fixture}",
                    "target_fixture": spec.target_fixture,
                    "expected_outcome": spec.expected_outcome,
                    "normalized_fields": list(spec.normalized_fields),
                    "fixture_project_root": str(fixture.project_root),
                    "registry_root": str(fixture.registry_root),
                    "canonical_spec": {
                        "row_id": spec.row_id,
                        "command": list(spec.command),
                        "target_fixture": spec.target_fixture,
                        "expected_outcome": spec.expected_outcome,
                        "normalized_fields": list(spec.normalized_fields),
                    },
                }
            )
        return rows

    probe_script = _write_temp_file(runtime_root, suffix="-trust-handoff.py", content=_phase15_probe_script())
    for spec in TRUST_HANDOFF_MATRIX:
        fixture = fixtures[spec["target_fixture"]]
        probe_workspace = _phase15_workspace(
            run_root=runtime_root,
            fixture=fixture,
            lane="baseline",
            row_id=spec["row_id"],
        )
        row_command = (
            "python3",
            str(probe_script),
            spec["probe_kind"],
            str(probe_workspace),
            spec["target_fixture"],
            spec["row_id"],
        )
        rows.append(
            {
                "id": spec["row_id"],
                "command": list(row_command),
                "display_command": spec["display_command"],
                "target_fixture": spec["target_fixture"],
                "expected_outcome": spec["expected_outcome"],
                "normalized_fields": list(spec["normalized_fields"]),
                "fixture_project_root": str(fixture.project_root),
                "registry_root": str(fixture.registry_root),
                "probe_kind": spec["probe_kind"],
                "probe_script": str(probe_script),
                "canonical_spec": {
                    "row_id": spec["row_id"],
                    "probe_kind": spec["probe_kind"],
                    "target_fixture": spec["target_fixture"],
                    "expected_outcome": spec["expected_outcome"],
                    "normalized_fields": list(spec["normalized_fields"]),
                },
            }
        )
    return rows


def preflight_lane(
    lane: str,
    *,
    run_root: Path,
    local_model: str,
    timeout_seconds: int,
    lane_binaries: dict[str, Any] | None = None,
    replay_lanes: set[str] | None = None,
    scenario: str = DEFAULT_SCENARIO,
    replay_fixture_dir: Path | None = None,
) -> dict[str, Any]:
    """Classify whether a lane is ready, degraded, or unavailable."""
    binaries = lane_binaries or _collect_lane_binaries(local_model=local_model)
    info = binaries.get(lane, {})
    if lane not in DEFAULT_LANES:
        return {
            "status": "unavailable",
            "failure_class": "operator_misconfiguration",
            "error_identifier": "UNKNOWN_LANE",
            "message": f"Unsupported lane '{lane}'",
            "binary": info,
        }

    if replay_lanes and lane in replay_lanes:
        fixtures = _load_replay_fixtures(lane, scenario, fixture_dir=replay_fixture_dir)
        preflight_data = fixtures.get("preflight")
        if preflight_data:
            return preflight_data
        return {
            "status": "ready",
            "failure_class": None,
            "error_identifier": None,
            "message": f"replay fixture for {lane}",
            "binary": {"path": f"/replay/{lane}", "version": "replay-fixture-v1"},
        }

    if lane == "claude":
        claude_path = info.get("path")
        if not claude_path:
            return _preflight_failure("lane_unavailable", "CLAUDE_MISSING", "claude binary not found", info)
        command = [
            str(claude_path),
            "-p",
            "Reply with OK only.",
            "--output-format",
            "text",
        ]
        proc = _run_process(command, cwd=run_root, timeout_seconds=timeout_seconds)
        return _classify_preflight_result(proc, info, expected_text="ok")

    if lane == "codex":
        codex_path = info.get("path")
        if not codex_path:
            return _preflight_failure("lane_unavailable", "CODEX_MISSING", "codex binary not found", info)
        output_file = run_root / "codex-preflight.txt"
        command = [
            str(codex_path),
            "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            "--sandbox",
            "workspace-write",
            "-C",
            str(run_root),
            "-o",
            str(output_file),
            "Reply with OK only.",
        ]
        proc = _run_process(command, cwd=run_root, timeout_seconds=timeout_seconds)
        if output_file.exists() and not proc["stdout"]:
            proc["stdout"] = output_file.read_text(encoding="utf-8")
        return _classify_preflight_result(proc, info, expected_text="ok")

    ollama_info = info
    ollama_path = ollama_info.get("provider_path")
    codex_path = ollama_info.get("path")
    if not codex_path:
        return _preflight_failure("lane_unavailable", "CODEX_MISSING", "codex binary not found", info)
    if not ollama_path:
        return _preflight_failure("lane_unavailable", "OLLAMA_MISSING", "ollama binary not found", info)

    show_proc = _run_process(
        [str(ollama_path), "show", local_model],
        cwd=run_root,
        timeout_seconds=timeout_seconds,
    )
    if show_proc["exit_code"] != 0:
        message = _combined_output(show_proc)
        failure_class = "lane_unavailable" if "manifest" in message.lower() or "not found" in message.lower() else "network_or_service_failure"
        error_identifier = "LOCAL_MODEL_MISSING" if failure_class == "lane_unavailable" else "OLLAMA_SERVICE_FAILURE"
        return _preflight_failure(failure_class, error_identifier, message, info)

    smoke_proc = _run_process(
        [str(ollama_path), "run", local_model, "Reply with OK only."],
        cwd=run_root,
        timeout_seconds=timeout_seconds,
    )
    return _classify_preflight_result(smoke_proc, info, expected_text="ok")


def execute_matrix_row(
    *,
    lane: str,
    row: dict[str, Any],
    repo_root: Path,
    run_root: Path,
    local_model: str,
    lane_binaries: dict[str, Any],
    artifact_root: Path,
    timeout_seconds: int,
    replay_lanes: set[str] | None = None,
    replay_fixture_dir: Path | None = None,
    scenario: str = DEFAULT_SCENARIO,
) -> dict[str, Any]:
    """Execute one matrix row through a lane agent and normalize the result."""
    command = list(row["command"])
    if row.get("probe_kind"):
        fixture = PreparedFixture(
            fixture_id=row["target_fixture"],
            project_root=Path(row["fixture_project_root"]),
            registry_root=Path(row["registry_root"]),
            manifest_path=None,
            source_root=Path(row["fixture_project_root"]),
            runtime_mode="probe",
        )
        workspace = _phase15_workspace(
            run_root=run_root,
            fixture=fixture,
            lane=lane,
            row_id=row["id"],
        )
        command = [
            "python3",
            row["probe_script"],
            row["probe_kind"],
            str(workspace),
            row["target_fixture"],
            row["id"],
        ]

    spec_hash = _stable_hash(row["canonical_spec"])
    invocation = {
        "lane": lane,
        "cwd": str(run_root),
        "command": command,
        "local_model": local_model,
    }
    invocation_hash = _stable_hash(invocation)
    command_text = _build_shell_command(repo_root=repo_root, command=command)

    # Resolve replay fixture for this row if the lane is in replay mode.
    replay_response: dict[str, Any] | None = None
    if replay_lanes and lane in replay_lanes:
        fixtures = _load_replay_fixtures(lane, scenario, fixture_dir=replay_fixture_dir)
        replay_response = fixtures.get("rows", {}).get(row["id"])

    agent_payload = invoke_lane_command(
        lane=lane,
        shell_command=command_text,
        cwd=run_root,
        local_model=local_model,
        timeout_seconds=timeout_seconds,
        lane_binaries=lane_binaries,
        replay_response=replay_response,
    )
    command_output = _decode_command_output(agent_payload)
    failure_class = classify_failure(
        lane=lane,
        row=row,
        command_output=command_output,
        raw_message=_combined_output(command_output),
    )
    normalized = normalize_row_result(
        row=row,
        command_output=command_output,
        failure_class=failure_class,
    )
    raw_path = _write_raw_output(
        artifact_root=artifact_root,
        lane=lane,
        row_id=row["id"],
        payload={
            "agent_response": {
                "exit_code": agent_payload.get("exit_code"),
                "stdout": sanitize_text(agent_payload.get("stdout", "")),
                "stderr": sanitize_text(agent_payload.get("stderr", "")),
            },
            "command_output": {
                "exit_code": command_output["exit_code"],
                "stdout": sanitize_text(command_output.get("stdout", "")),
                "stderr": sanitize_text(command_output.get("stderr", "")),
            },
        },
    )

    row_status = "pass"
    if failure_class in {"lane_unavailable", "auth_failure", "network_or_service_failure", "operator_misconfiguration", "internal_error"} and row["expected_outcome"] != "pre_dispatch_failure":
        row_status = "degraded"
    elif row["expected_outcome"] == "success" and command_output["exit_code"] != 0:
        row_status = "fail"
    elif row["expected_outcome"] == "pre_dispatch_failure" and (
        command_output["exit_code"] == 0 or not normalized.get("pre_dispatch_rejection")
    ):
        row_status = "fail"

    return {
        "id": row["id"],
        "command": row["display_command"],
        "target_fixture": row["target_fixture"],
        "status": row_status,
        "exit_code": command_output["exit_code"],
        "failure_class": failure_class,
        "error_identifier": normalized.get("error_identifier"),
        "pre_dispatch_rejection": normalized.get("pre_dispatch_rejection"),
        "normalized": normalized,
        "raw_output_path": str(raw_path),
        "invocation_hash": invocation_hash,
        "canonical_invocation_spec_hash": spec_hash,
        "sanitizer_version": SANITIZER_VERSION,
        "classifier_version": CLASSIFIER_VERSION,
        "model_identifier": local_model if lane == "ollama" else lane,
        "target_fixture_identity": row["target_fixture"],
    }


def invoke_lane_command(
    *,
    lane: str,
    shell_command: str,
    cwd: Path,
    local_model: str,
    timeout_seconds: int,
    lane_binaries: dict[str, Any],
    replay_response: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Ask a lane CLI to run one shell command and return a JSON envelope."""
    if replay_response is not None:
        return replay_response

    prompt = (
        "Run exactly one shell command from the current working directory.\n"
        "Do not edit files, install dependencies, or run additional commands.\n"
        "Capture the command's exit_code, stdout, and stderr.\n"
        "Return only valid JSON with keys exit_code, stdout, stderr.\n"
        f"Command:\n{shell_command}\n"
    )
    schema = {
        "type": "object",
        "properties": {
            "exit_code": {"type": "integer"},
            "stdout": {"type": "string"},
            "stderr": {"type": "string"},
        },
        "required": ["exit_code", "stdout", "stderr"],
        "additionalProperties": False,
    }

    if lane == "claude":
        binary = lane_binaries["claude"]["path"]
        proc = _run_process(
            [
                str(binary),
                "-p",
                prompt,
                "--output-format",
                "json",
                "--json-schema",
                json.dumps(schema),
            ],
            cwd=cwd,
            timeout_seconds=timeout_seconds,
        )
    else:
        binary = lane_binaries[lane]["path"]
        schema_file = _write_temp_file(cwd, suffix="-schema.json", content=json.dumps(schema))
        output_file = cwd / f"{lane}-last-message-{next(tempfile._get_candidate_names())}.json"
        command = [
            str(binary),
            "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            "--sandbox",
            "workspace-write",
            "-C",
            str(cwd),
            "--output-schema",
            str(schema_file),
            "-o",
            str(output_file),
        ]
        if lane == "ollama":
            command.extend(["--oss", "--local-provider", "ollama", "-m", local_model])
        command.append(prompt)
        proc = _run_process(command, cwd=cwd, timeout_seconds=timeout_seconds)
        if output_file.exists():
            proc["stdout"] = output_file.read_text(encoding="utf-8")

    payload = _coerce_agent_json(proc)
    payload.setdefault("exit_code", proc["exit_code"])
    payload.setdefault("stdout", proc.get("stdout", ""))
    payload.setdefault("stderr", proc.get("stderr", ""))
    return payload


def normalize_row_result(
    *,
    row: dict[str, Any],
    command_output: dict[str, Any],
    failure_class: str,
) -> dict[str, Any]:
    """Normalize one row into stable parity fields."""
    normalized: dict[str, Any] = {
        "exit_code": command_output["exit_code"],
        "failure_class": failure_class,
        "error_identifier": _extract_error_identifier(command_output),
        "pre_dispatch_rejection": False,
    }
    payload = _load_stdout_json(command_output.get("stdout", ""))
    if row["expected_outcome"] == "pre_dispatch_failure":
        if isinstance(payload, dict):
            normalized["pre_dispatch_rejection"] = bool(
                payload.get("pre_dispatch_rejection")
                or payload.get("failure_class") == "unsupported_command"
            )
            normalized["error_identifier"] = payload.get("error_identifier") or normalized["error_identifier"]
            normalized["failure_class"] = payload.get("failure_class") or normalized["failure_class"]
        else:
            normalized["pre_dispatch_rejection"] = command_output["exit_code"] != 0
        return normalized

    if not isinstance(payload, dict):
        return normalized

    for field in row["normalized_fields"]:
        normalized[field] = _deep_get(payload, field)
    return normalized


def compare_results(matrix: list[dict[str, Any]], results: dict[str, Any]) -> list[dict[str, Any]]:
    """Compare ready-lane normalized outcomes and report semantic mismatches."""
    mismatches: list[dict[str, Any]] = []
    ready_lanes = [lane for lane, payload in results.items() if payload["status"] == "ready"]
    if len(ready_lanes) < 2:
        return mismatches

    row_by_lane = {
        lane: {item["id"]: item for item in results[lane]["rows"]}
        for lane in ready_lanes
    }
    baseline_lane = ready_lanes[0]

    for row in matrix:
        baseline = row_by_lane.get(baseline_lane, {}).get(row["id"])
        if baseline is None:
            continue
        for lane in ready_lanes[1:]:
            candidate = row_by_lane.get(lane, {}).get(row["id"])
            if candidate is None:
                mismatches.append(
                    {
                        "row_id": row["id"],
                        "lane": lane,
                        "baseline_lane": baseline_lane,
                        "field": "missing_result",
                        "baseline_value": True,
                        "candidate_value": False,
                    }
                )
                continue
            if baseline["status"] != candidate["status"]:
                mismatches.append(
                    {
                        "row_id": row["id"],
                        "lane": lane,
                        "baseline_lane": baseline_lane,
                        "field": "status",
                        "baseline_value": baseline["status"],
                        "candidate_value": candidate["status"],
                    }
                )
            for field in row["normalized_fields"]:
                base_value = baseline["normalized"].get(field)
                candidate_value = candidate["normalized"].get(field)
                if base_value != candidate_value:
                    mismatches.append(
                        {
                            "row_id": row["id"],
                            "lane": lane,
                            "baseline_lane": baseline_lane,
                            "field": field,
                            "baseline_value": base_value,
                            "candidate_value": candidate_value,
                        }
                    )
    return mismatches


def write_report(report: dict[str, Any], *, artifact_root: Path, run_id: str) -> None:
    """Persist latest and historical parity report artifacts."""
    history_dir = artifact_root / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    latest_path = artifact_root / "latest.json"
    history_path = history_dir / f"{run_id}.json"
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    latest_path.write_text(payload, encoding="utf-8")
    history_path.write_text(payload, encoding="utf-8")


def classify_failure(
    *,
    lane: str,
    row: dict[str, Any],
    command_output: dict[str, Any],
    raw_message: str,
) -> str:
    """Classify one command outcome into the parity failure taxonomy."""
    payload = _load_stdout_json(command_output.get("stdout", ""))
    if isinstance(payload, dict):
        existing = payload.get("failure_class")
        if isinstance(existing, str) and existing:
            return existing
        error_text = str(payload.get("error", ""))
    else:
        error_text = ""

    combined = f"{raw_message}\n{error_text}".lower()
    if command_output["exit_code"] == 0:
        return "pass"
    if row["expected_outcome"] == "pre_dispatch_failure" and (
        "not routed safely" in combined or "not a gsigmad project" in combined
    ):
        return "unsupported_command"
    if any(marker in combined for marker in _AUTH_MARKERS):
        return "auth_failure"
    if any(marker in combined for marker in _NETWORK_MARKERS):
        return "network_or_service_failure"
    if "trust_tier_error" in combined:
        return "governance_denied"
    if "not routed safely" in combined:
        return "unsupported_command"
    if "invalid arguments" in combined or "unknown option" in combined:
        return "operator_misconfiguration"
    return "internal_error"


def sanitize_text(text: str) -> str:
    """Redact obvious credentials before persisting raw outputs."""
    sanitized = text
    for pattern in _REDACTION_PATTERNS:
        sanitized = pattern.sub(r"\1[REDACTED]" if pattern.groups >= 1 else "[REDACTED]", sanitized)
    if len(sanitized) > _RAW_FILE_LIMIT:
        sanitized = sanitized[:_RAW_FILE_LIMIT] + "\n...[truncated]\n"
    return sanitized


def _prepare_native_fixture(
    *,
    repo_root: Path,
    native: str,
    fixtures_root: Path,
    registry_root: Path,
) -> PreparedFixture:
    fixture_id = "self_fixture"
    source_root = repo_root if native == "self_fixture" else Path(native).resolve()
    destination = fixtures_root / fixture_id
    _copy_tree(source_root, destination)
    return PreparedFixture(
        fixture_id=fixture_id,
        project_root=destination,
        registry_root=registry_root,
        manifest_path=None,
        source_root=source_root,
        runtime_mode="gsigmad",
    )


def _prepare_routed_fixture(
    *,
    repo_root: Path,
    routed: str,
    fixtures_root: Path,
    registry_root: Path,
) -> PreparedFixture:
    manifest_path = repo_root / "adapters" / "runtime" / "shadow-seeds.yaml"
    if routed != "shadow_seeds_fixture":
        manifest_path = Path(routed).resolve()
    manifest = load_runtime_manifest(manifest_path)
    source_root = Path(manifest.project_root).resolve()
    destination = fixtures_root / "shadow_seeds_fixture"
    _copy_tree(source_root, destination)

    manifest_payload = manifest.model_dump()
    manifest_payload["project_root"] = str(destination)
    runtime_registry = registry_root / "adapters" / "runtime"
    runtime_registry.mkdir(parents=True, exist_ok=True)
    copied_manifest = runtime_registry / manifest_path.name
    copied_manifest.write_text(
        yaml.safe_dump(manifest_payload, sort_keys=False),
        encoding="utf-8",
    )
    return PreparedFixture(
        fixture_id="shadow_seeds_fixture",
        project_root=destination,
        registry_root=registry_root,
        manifest_path=copied_manifest,
        source_root=source_root,
        runtime_mode=manifest.runtime_mode,
    )


def _copy_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns(*_IGNORE_COPY_PATTERNS),
    )


def _build_shell_command(*, repo_root: Path, command: list[str]) -> str:
    quoted = " ".join(_shell_quote(part) for part in command)
    return f"PYTHONPATH={_shell_quote(str(repo_root / 'src'))} {quoted}"


def _collect_lane_binaries(*, local_model: str) -> dict[str, Any]:
    claude_path = which("claude")
    codex_path = which("codex")
    ollama_path = which("ollama")
    return {
        "claude": {
            "path": claude_path,
            "version": _binary_version(claude_path, ["--version"]),
        },
        "codex": {
            "path": codex_path,
            "version": _binary_version(codex_path, ["--version"]),
        },
        "ollama": {
            "path": codex_path,
            "version": _binary_version(codex_path, ["--version"]),
            "provider_path": ollama_path,
            "provider_version": _binary_version(ollama_path, ["--version"]),
            "provider": "ollama",
            "model": local_model,
        },
    }


def _binary_version(binary: str | None, args: list[str]) -> str | None:
    if not binary:
        return None
    try:
        completed = subprocess.run(
            [binary, *args],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return None
    text = (completed.stdout or completed.stderr).strip().splitlines()
    return text[0] if text else None


def _environment_allowlist() -> dict[str, str]:
    return {
        "ANTHROPIC_API_KEY": "present" if os.environ.get("ANTHROPIC_API_KEY") else "missing",
        "OPENAI_API_KEY": "present" if os.environ.get("OPENAI_API_KEY") else "missing",
        "OLLAMA_HOST": os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
    }


def _git_commit(repo_root: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return None
    return completed.stdout.strip() or None


def _normalize_lanes(lanes: list[str] | tuple[str, ...] | None) -> list[str]:
    if not lanes:
        return list(DEFAULT_LANES)
    normalized: list[str] = []
    for lane in lanes:
        name = lane.strip().lower()
        if name and name not in normalized:
            normalized.append(name)
    return normalized


def _normalize_scenario(scenario: str | None) -> str:
    normalized = (scenario or DEFAULT_SCENARIO).strip().lower()
    if normalized not in SCENARIO_MATRIX_VERSIONS:
        raise ValueError(f"Unsupported parity scenario: {scenario}")
    return normalized


def _default_artifact_root(scenario: str) -> Path:
    if scenario == TRUST_HANDOFF_SCENARIO:
        return TRUST_HANDOFF_ARTIFACT_ROOT
    return DEFAULT_ARTIFACT_ROOT


def _build_run_id(scenario: str = DEFAULT_SCENARIO) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    prefix = "PHASE15" if scenario == TRUST_HANDOFF_SCENARIO else "PARITY"
    return f"{prefix}-{stamp}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _run_process(command: list[str], *, cwd: Path, timeout_seconds: int) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return {
            "exit_code": completed.returncode,
            "stdout": completed.stdout or "",
            "stderr": completed.stderr or "",
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return {
            "exit_code": 124,
            "stdout": stdout,
            "stderr": stderr + "\nTIMEOUT",
        }


def _classify_preflight_result(
    proc: dict[str, Any],
    binary_info: dict[str, Any],
    *,
    expected_text: str,
) -> dict[str, Any]:
    combined = _combined_output(proc).lower()
    if proc["exit_code"] == 0 and expected_text in combined:
        return {
            "status": "ready",
            "failure_class": None,
            "error_identifier": None,
            "message": combined.strip()[:200],
            "binary": binary_info,
        }
    if any(marker in combined for marker in _AUTH_MARKERS):
        return _preflight_failure("auth_failure", "AUTH_FAILURE", combined, binary_info, status="degraded")
    if any(marker in combined for marker in _NETWORK_MARKERS) or proc["exit_code"] == 124:
        return _preflight_failure("network_or_service_failure", "SERVICE_FAILURE", combined, binary_info, status="degraded")
    return _preflight_failure("internal_error", "PRECHECK_FAILED", combined, binary_info, status="degraded")


def _preflight_failure(
    failure_class: str,
    error_identifier: str,
    message: str,
    binary_info: dict[str, Any],
    *,
    status: str = "unavailable",
) -> dict[str, Any]:
    return {
        "status": status,
        "failure_class": failure_class,
        "error_identifier": error_identifier,
        "message": sanitize_text(message),
        "binary": binary_info,
    }


def _coerce_agent_json(proc: dict[str, Any]) -> dict[str, Any]:
    for candidate in (proc.get("stdout", ""), proc.get("stderr", "")):
        parsed = _load_stdout_json(candidate)
        if isinstance(parsed, dict):
            return parsed
    return {
        "exit_code": proc["exit_code"],
        "stdout": proc.get("stdout", ""),
        "stderr": proc.get("stderr", ""),
    }


def _decode_command_output(agent_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "exit_code": int(agent_payload.get("exit_code", 1)),
        "stdout": str(agent_payload.get("stdout", "")),
        "stderr": str(agent_payload.get("stderr", "")),
    }


def _load_stdout_json(text: str) -> dict[str, Any] | list[Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    if stripped.startswith("```"):
        stripped = stripped.strip("`").strip()
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end > start:
        candidate = stripped[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            return None
    return None


def _extract_error_identifier(command_output: dict[str, Any]) -> str | None:
    payload = _load_stdout_json(command_output.get("stdout", ""))
    if isinstance(payload, dict):
        identifier = payload.get("error_identifier")
        if isinstance(identifier, str) and identifier:
            return identifier
    combined = _combined_output(command_output).upper()
    if "NOT_ROUTED_SAFELY" in combined:
        return "NOT_ROUTED_SAFELY"
    if "NOT A GSIGMAD PROJECT" in combined:
        return "NOT_GSIGMAD_PROJECT"
    return None


def _combined_output(payload: dict[str, Any]) -> str:
    return f"{payload.get('stdout', '')}\n{payload.get('stderr', '')}".strip()


def _deep_get(payload: dict[str, Any], dotted_path: str) -> Any:
    current: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _write_raw_output(
    *,
    artifact_root: Path,
    lane: str,
    row_id: str,
    payload: dict[str, Any],
) -> Path:
    raw_dir = artifact_root / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{lane}-{row_id}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_temp_file(root: Path, *, suffix: str, content: str) -> Path:
    path = root / f"tmp-{next(tempfile._get_candidate_names())}{suffix}"
    path.write_text(content, encoding="utf-8")
    return path


def _phase15_workspace(
    *,
    run_root: Path,
    fixture: PreparedFixture,
    lane: str,
    row_id: str,
) -> Path:
    workspace = run_root / "probe-workspaces" / lane / row_id / fixture.fixture_id
    if workspace.exists():
        shutil.rmtree(workspace)
    _copy_tree(fixture.project_root, workspace)
    return workspace


def _run_phase15_probe(
    kind: str,
    *,
    fixture_root: Path,
    fixture_id: str,
    row_id: str,
) -> dict[str, Any]:
    if kind == "provisional-write":
        return _phase15_provisional_write_probe(fixture_id=fixture_id, row_id=row_id)
    if kind == "promotion-without-countersignature":
        return _phase15_promotion_probe(
            fixture_root=fixture_root,
            fixture_id=fixture_id,
            include_signature=False,
        )
    if kind == "promotion-with-countersignature":
        return _phase15_promotion_probe(
            fixture_root=fixture_root,
            fixture_id=fixture_id,
            include_signature=True,
        )
    if kind == "handoff-round-trip":
        return _phase15_handoff_probe(
            fixture_root=fixture_root,
            fixture_id=fixture_id,
            row_id=row_id,
        )
    raise ValueError(f"Unsupported Phase 15 probe kind: {kind}")


def _phase15_provisional_write_probe(*, fixture_id: str, row_id: str) -> dict[str, Any]:
    from gsigmad.governance.kg.writer import TrustTierError, write_document

    doc = {
        "_key": f"{fixture_id}-{row_id}",
        "title": "Phase 15 probe",
        "_provenance": {
            "prov:Agent": {"trust_tier": "PROVISIONAL"},
            "prov:Activity": {"prov:id": row_id, "prov:type": "probe"},
            "prov:Entity": {"prov:id": fixture_id, "prov:type": "artifact"},
        },
    }
    payload = {
        "exit_code": 0,
        "failure_class": "pass",
        "error_identifier": None,
        "trust_tier": "PROVISIONAL",
        "write_attempted": True,
    }
    try:
        write_document("phase15_parity_probe", doc)
    except TrustTierError as exc:
        payload["exit_code"] = 1
        payload["failure_class"] = "governance_denied"
        payload["error_identifier"] = "TRUST_TIER_ERROR"
        payload["error"] = str(exc)
    return payload


def _phase15_promotion_probe(
    *,
    fixture_root: Path,
    fixture_id: str,
    include_signature: bool,
) -> dict[str, Any]:
    from gsigmad.governance.reports.amendment import create_amendment, validate_amendment

    (fixture_root / ".agent").mkdir(parents=True, exist_ok=True)
    amendment = {
        "exp_id": "EXP-1.1",
        "created_by": fixture_id,
        "justification": "Promotion probe justification exceeds twenty characters.",
        "pi_countersignature": "PI-SIGNATURE" if include_signature else "",
        "changed_fields": ["trust_tier", "status"],
        "original_values": {"trust_tier": "PROVISIONAL", "status": "pending"},
        "new_values": {"trust_tier": "VERIFIED", "status": "approved"},
    }
    validation = validate_amendment(amendment, gsd_root=str(fixture_root))
    created = {"pass": False, "amendment_file": None}
    if validation.get("pass"):
        created = create_amendment(amendment, gsd_root=str(fixture_root))
    metadata_keys = sorted(amendment.keys())
    if created.get("pass") and created.get("amendment_file"):
        written = fixture_root / created["amendment_file"]
        metadata_keys = sorted(json.loads(written.read_text(encoding="utf-8")).keys())
    payload = {
        "failure_class": "pass",
        "error_identifier": None,
        "validation_pass": bool(validation.get("pass")),
        "pi_countersignature_present": bool(amendment.get("pi_countersignature")),
        "amendment_file": created.get("amendment_file"),
        "metadata_keys": metadata_keys,
    }
    if not validation.get("pass"):
        payload["failure_class"] = "governance_denied"
        payload["error_identifier"] = "TRUST_TIER_ERROR"
        payload["error"] = validation.get("error")
    return payload


def _phase15_handoff_probe(
    *,
    fixture_root: Path,
    fixture_id: str,
    row_id: str,
) -> dict[str, Any]:
    from gsigmad.governance.closure_chain import list_chain_summaries, record_chain_event
    from gsigmad.governance.context_state import load_latest_checkpoint, write_checkpoint
    from gsigmad.governance.versioning.coordinate import bootstrap_coordination_state

    bootstrap_coordination_state(fixture_root)
    exp_id = "EXP-1.1"
    record_chain_event(fixture_root, exp_id=exp_id, stage="TASK", artifact_id="TASK-1.1")
    record_chain_event(fixture_root, exp_id=exp_id, stage="PROMPT", artifact_id="PROMPT-1.1")
    record_chain_event(fixture_root, exp_id=exp_id, stage="EXP", artifact_id=exp_id)
    record_chain_event(fixture_root, exp_id=exp_id, stage="RESULTS")
    checkpoint = write_checkpoint(fixture_root, note=f"{fixture_id}:{row_id}")
    reloaded = load_latest_checkpoint(fixture_root)
    summaries = list_chain_summaries(fixture_root)
    reference = reloaded or checkpoint
    return {
        "checkpoint_written": bool(checkpoint.get("path") and Path(checkpoint["path"]).is_file()),
        "checkpoint_loaded": bool(reloaded),
        "coordinate": reference.get("coordinate"),
        "recommended_command": reference.get("recommended_command"),
        "open_chain_count": len([item for item in summaries if not item.get("complete")]),
    }


def _phase15_probe_script() -> str:
    return """
from __future__ import annotations

import json
import sys
from pathlib import Path

from gsigmad.governance.parity import _run_phase15_probe


def main(argv: list[str]) -> int:
    kind = argv[1]
    project_root = Path(argv[2]).resolve()
    fixture_id = argv[3]
    row_id = argv[4]
    payload = _run_phase15_probe(
        kind,
        fixture_root=project_root,
        fixture_id=fixture_id,
        row_id=row_id,
    )
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
""".strip() + "\n"


def _stable_hash(payload: Any) -> str:
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _shell_quote(value: str) -> str:
    return shlex.quote(value)
