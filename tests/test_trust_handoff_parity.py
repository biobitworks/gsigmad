"""Tests for the Phase 15 trust-handoff parity scenario."""
from __future__ import annotations

import json
from pathlib import Path

from gsigmad.governance import parity as parity_mod


def _write_shadow_manifest(repo_root: Path, target_root: Path) -> None:
    registry = repo_root / "adapters" / "runtime"
    registry.mkdir(parents=True)
    (registry / "shadow-seeds.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "project_name: shadow-seeds",
                f"project_root: {target_root}",
                'namespace_prefix: "shadow:"',
                "runtime_mode: legacy",
                "surfaces:",
                "  canon_path: CANON.md",
                "  experiments_dir: experiments",
                "  legacy_state_dir: .agent",
                "command_modes:",
                "  status: legacy",
                "  monitor: legacy",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_native_project(project_root: Path) -> None:
    (project_root / ".gsigmad" / "experiments").mkdir(parents=True)
    (project_root / "src").mkdir(parents=True)
    (project_root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")


def _write_routed_project(project_root: Path) -> None:
    (project_root / "experiments").mkdir(parents=True)
    (project_root / ".agent").mkdir(parents=True)
    (project_root / "CANON.md").write_text("> **Status**: ACTIVE\n> **Version**: 1.0.0\n", encoding="utf-8")


def test_phase15_provisional_write_is_governance_denied(tmp_path: Path) -> None:
    payload = parity_mod._run_phase15_probe(
        "provisional-write",
        fixture_root=tmp_path,
        fixture_id="self_fixture",
        row_id="row-01",
    )

    assert payload["failure_class"] == "governance_denied"
    assert payload["error_identifier"] == "TRUST_TIER_ERROR"
    assert payload["trust_tier"] == "PROVISIONAL"
    assert payload["write_attempted"] is True


def test_phase15_promotion_requires_countersignature_and_persists_metadata(tmp_path: Path) -> None:
    denied = parity_mod._run_phase15_probe(
        "promotion-without-countersignature",
        fixture_root=tmp_path,
        fixture_id="self_fixture",
        row_id="row-03",
    )
    approved = parity_mod._run_phase15_probe(
        "promotion-with-countersignature",
        fixture_root=tmp_path,
        fixture_id="self_fixture",
        row_id="row-04",
    )

    assert denied["validation_pass"] is False
    assert approved["validation_pass"] is True
    assert approved["pi_countersignature_present"] is True
    assert approved["amendment_file"]
    assert "pi_countersignature" in approved["metadata_keys"]
    assert (tmp_path / approved["amendment_file"]).is_file()


def test_phase15_handoff_round_trip_writes_checkpoint(tmp_path: Path) -> None:
    payload = parity_mod._run_phase15_probe(
        "handoff-round-trip",
        fixture_root=tmp_path,
        fixture_id="shadow_seeds_fixture",
        row_id="row-06",
    )

    assert payload["checkpoint_written"] is True
    assert payload["checkpoint_loaded"] is True
    assert payload["coordinate"].startswith("v")
    assert payload["recommended_command"]
    assert payload["open_chain_count"] >= 1


def test_run_parity_trust_handoff_writes_phase15_report(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    shadow_root = tmp_path / "shadow-seeds"
    artifact_root = tmp_path / "artifacts" / "parity" / "trust-handoff"
    _write_native_project(repo_root)
    _write_routed_project(shadow_root)
    _write_shadow_manifest(repo_root, shadow_root)

    ready = {
        "status": "ready",
        "failure_class": None,
        "error_identifier": None,
        "message": "ok",
        "binary": {"path": "/bin/mock", "version": "1.0"},
    }
    monkeypatch.setattr(parity_mod, "preflight_lane", lambda *args, **kwargs: ready)
    monkeypatch.setattr(
        parity_mod,
        "_collect_lane_binaries",
        lambda local_model: {"claude": {"path": "/bin/claude", "version": "1.0"}},
    )
    monkeypatch.setattr(parity_mod, "_git_commit", lambda repo_root: "deadbeef")

    def fake_execute_matrix_row(*, lane, row, **kwargs):
        normalized = {
            "exit_code": 1 if row["id"].startswith("row-0") and "provisional" in row["display_command"] else 0,
            "failure_class": "governance_denied" if "provisional" in row["display_command"] else "pass",
            "error_identifier": "TRUST_TIER_ERROR" if "provisional" in row["display_command"] else None,
            "trust_tier": "PROVISIONAL" if "provisional" in row["display_command"] else None,
            "write_attempted": True if "provisional" in row["display_command"] else None,
            "validation_pass": "without-countersignature" not in row["display_command"],
            "pi_countersignature_present": "with-countersignature" in row["display_command"],
            "amendment_file": ".agent/amendments/EXP-1.1-1.json" if "promotion" in row["display_command"] else None,
            "metadata_keys": ["pi_countersignature"] if "promotion" in row["display_command"] else None,
            "checkpoint_written": "handoff" in row["display_command"],
            "checkpoint_loaded": "handoff" in row["display_command"],
            "coordinate": "v1.1.1.1" if "handoff" in row["display_command"] else None,
            "recommended_command": "gsigmad redteam EXP-1.1" if "handoff" in row["display_command"] else None,
            "open_chain_count": 1 if "handoff" in row["display_command"] else None,
        }
        return {
            "id": row["id"],
            "command": row["display_command"],
            "target_fixture": row["target_fixture"],
            "status": "pass",
            "exit_code": 0,
            "failure_class": normalized["failure_class"],
            "error_identifier": normalized.get("error_identifier"),
            "pre_dispatch_rejection": False,
            "normalized": normalized,
            "raw_output_path": str(artifact_root / "raw.json"),
            "invocation_hash": "abc",
            "canonical_invocation_spec_hash": "def",
            "sanitizer_version": "1.0",
            "classifier_version": "1.0",
            "model_identifier": lane,
            "target_fixture_identity": row["target_fixture"],
        }

    monkeypatch.setattr(parity_mod, "execute_matrix_row", fake_execute_matrix_row)

    report = parity_mod.run_parity(
        repo_root=repo_root,
        lanes=["claude"],
        scenario="trust-handoff",
        artifact_root=artifact_root,
    )

    latest = artifact_root / "latest.json"
    assert latest.exists()
    written = json.loads(latest.read_text(encoding="utf-8"))
    assert report["scenario"] == "trust-handoff"
    assert written["phase_requirement"] == "PARITY-02"
    assert written["matrix_version"] == "phase15-v1"
    assert written["fixtures"]["self_fixture"]["project_root"].startswith(str((artifact_root / "work").resolve()))
    assert written["fixtures"]["shadow_seeds_fixture"]["project_root"].startswith(str((artifact_root / "work").resolve()))
