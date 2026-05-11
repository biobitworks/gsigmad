"""Wave 0 template contracts for scaffolded experiment artifacts."""
from __future__ import annotations

import pytest

from gsigmad.scaffold.templates import exp_template


def test_exp_template_sets_record_schema_version_3():
    """Phase 20 EXP templates must identify the new schema version explicitly."""
    record = exp_template("EXP-1.1", "EXPLORATORY", hypothesis="TODO", title="Title")
    assert record["record_schema_version"] == 3


def test_script_template_contains_exp_id_and_main_entrypoint():
    """Analysis script templates mention the EXP id and expose a main() entry point."""
    from gsigmad.scaffold.templates import script_template

    content = script_template("EXP-1.1", "CONFIRMATORY", "Signal check")
    assert "EXP-1.1" in content
    assert "def main()" in content


def test_result_manifest_placeholder_shape():
    """Manifest placeholders are explicit Phase 20 stubs, not immutable run manifests yet."""
    from gsigmad.scaffold.templates import result_manifest_placeholder

    placeholder = result_manifest_placeholder("EXP-1.1")
    assert placeholder["exp_id"] == "EXP-1.1"
    assert placeholder["status"] == "placeholder"
    assert placeholder["phase"] == 20
    assert placeholder["note"] == "Placeholder only; immutable run manifests arrive in Phase 22."
