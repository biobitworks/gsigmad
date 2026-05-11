"""Tests for adapter-aware KG routing helpers."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from gsigmad.governance.kg.routed import (
    KGWriteConflict,
    TrustTierError,
    resolve_kg_project_context,
    routed_find_experiments,
    validate_live_kg,
)


def test_resolve_kg_project_context_for_manifest_target(tmp_path):
    """Manifest-backed targets expose project_name and runtime metadata."""
    target = tmp_path / "shadow-seeds"
    target.mkdir()
    registry = tmp_path / "adapters" / "runtime"
    registry.mkdir(parents=True)
    manifest = registry / "shadow-seeds.yaml"
    manifest.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "project_name: shadow-seeds",
                f"project_root: {target}",
                'namespace_prefix: "shadow:"',
                "runtime_mode: legacy",
            ]
        ),
        encoding="utf-8",
    )

    context = resolve_kg_project_context(target)
    assert context.project_name == "shadow-seeds"
    assert context.runtime_mode == "legacy"
    assert context.namespace_prefix == "shadow:"


def test_routed_find_experiments_uses_resolved_project_name(tmp_path):
    """Adapter-aware query routing scopes by resolved project_name when no override is given."""
    target = tmp_path / "shadow-seeds"
    target.mkdir()
    registry = tmp_path / "adapters" / "runtime"
    registry.mkdir(parents=True)
    manifest = registry / "shadow-seeds.yaml"
    manifest.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "project_name: shadow-seeds",
                f"project_root: {target}",
                'namespace_prefix: "shadow:"',
                "runtime_mode: legacy",
            ]
        ),
        encoding="utf-8",
    )

    with patch("gsigmad.governance.kg.routed.find_experiments", return_value=[]) as mock_find:
        routed_find_experiments(target_path=target, limit=5)

    _, kwargs = mock_find.call_args
    assert kwargs["project"] == "shadow-seeds"
    assert kwargs["limit"] == 5


def test_validate_live_kg_replay_uses_hardened_queue_contract(tmp_path):
    """Live KG validation still drives queue fallback and replay through the routed helper."""
    fixed_now = datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc)
    exp_id = f"EXP-KGVAL-{fixed_now.strftime('%Y%m%dT%H%M%SZ')}"
    context = SimpleNamespace(
        project_name="shadow-seeds",
        project_root=tmp_path,
        runtime_mode="legacy",
        resolution_source="manifest",
        namespace_prefix="shadow:",
    )
    mock_db = MagicMock()
    mock_db.collection.return_value.get.return_value = {"_provenance": {"ok": True}, "project": "shadow-seeds"}

    def _write_document_side_effect(*args, **kwargs):
        activity_id = kwargs.get("activity_id", "")
        doc = args[1]
        if activity_id.endswith("-QUEUE"):
            from gsigmad.governance.kg import routed as routed_mod

            queue_path = routed_mod.writer_mod._QUEUE_PATH
            queue_path.write_text('{"queued_at":"2026-04-01T00:00:00Z"}\n', encoding="utf-8")
            return {"pass": True, "queued": True}
        if doc.get("_key", "").endswith("_provisional"):
            raise TrustTierError("blocked")
        if kwargs.get("old_rev") == "_stale_rev_001":
            raise KGWriteConflict("stale")
        return {"pass": True, "result": {"new": doc}}

    fake_datetime = MagicMock()
    fake_datetime.now.return_value = fixed_now

    with patch("gsigmad.governance.kg.routed.resolve_kg_project_context", return_value=context), \
         patch("gsigmad.governance.kg.routed.datetime", fake_datetime), \
         patch("gsigmad.governance.kg.routed.writer_mod._get_db", return_value=mock_db), \
         patch("gsigmad.governance.kg.routed.write_document", side_effect=_write_document_side_effect), \
         patch("gsigmad.governance.kg.routed.replay_queue", return_value={"pass": True, "processed": 1, "failed": 0, "expired": 0, "requeued": 0}) as mock_replay, \
         patch("gsigmad.governance.kg.routed.create_citation_edge", return_value={"pass": True, "result": {"_key": "cite-001"}}), \
         patch("gsigmad.governance.kg.routed.routed_find_experiments", return_value=[{"exp_id": exp_id}]), \
         patch("gsigmad.governance.kg.routed.find_experiments", return_value=[{"exp_id": exp_id}]), \
         patch("gsigmad.governance.kg.routed._cleanup_validation_artifacts"):
        result = validate_live_kg(target_path=tmp_path)

    assert result["pass"] is True
    assert result["checks"]["queue_fallback"] is True
    assert result["checks"]["queue_replay"] is True
    mock_replay.assert_called_once()
