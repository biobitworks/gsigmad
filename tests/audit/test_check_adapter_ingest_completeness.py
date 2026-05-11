"""Unit tests for gsigmad.audit.check_adapter_ingest_completeness.

Backs EXP-003 (NOT_CONFIGURED_ADAPTER_STATE_DISTINGUISHABILITY) by exercising
the deterministic harness on the 30 EXP-003 fixtures and asserting:

1. Each fixture maps to the expected state.
2. The four states produce DISTINCT verdict signatures (the H1 measurement —
   registered_no_response and registered_declaration_incomplete must NOT
   collapse onto the not_registered verdict).
3. The verdict-mapping contract holds for every state.
4. The CLI emits valid JSON with the four hard-rail flags untouched.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from gsigmad.audit.check_adapter_ingest_completeness import (
    BLOCK_DECLARATION_INCOMPLETE,
    BLOCK_NOT_REGISTERED,
    BLOCK_RUNTIME_RESPONSE_ABSENT,
    STATE_NOT_REGISTERED,
    STATE_REGISTERED_COMPLETE,
    STATE_REGISTERED_DECLARATION_INCOMPLETE,
    STATE_REGISTERED_NO_RESPONSE,
    STATE_TO_VERDICT,
    VERDICT_PASS,
    VERDICT_PASS_WITH_BLOCKS,
    VERDICT_REJECT,
    analyze_file,
    analyze_root,
    detect_state,
    load_canonical_index,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "adapter_ingest_completeness"
)


# ---------------------------------------------------------------------------
# Contract: verdict mapping.
# ---------------------------------------------------------------------------

def test_verdict_mapping_contract():
    """The four states must map to the contracted verdict tuples."""
    assert STATE_TO_VERDICT[STATE_REGISTERED_COMPLETE] == (VERDICT_PASS, [])
    assert STATE_TO_VERDICT[STATE_REGISTERED_NO_RESPONSE] == (
        VERDICT_REJECT,
        [BLOCK_RUNTIME_RESPONSE_ABSENT],
    )
    assert STATE_TO_VERDICT[STATE_REGISTERED_DECLARATION_INCOMPLETE] == (
        VERDICT_REJECT,
        [BLOCK_DECLARATION_INCOMPLETE],
    )
    assert STATE_TO_VERDICT[STATE_NOT_REGISTERED] == (
        VERDICT_PASS_WITH_BLOCKS,
        [BLOCK_NOT_REGISTERED],
    )


def test_no_response_verdict_differs_from_not_registered():
    """EXP-003 key contract: REJECT vs PASS_WITH_BLOCKS — distinguishable."""
    no_resp_verdict, _ = STATE_TO_VERDICT[STATE_REGISTERED_NO_RESPONSE]
    not_reg_verdict, _ = STATE_TO_VERDICT[STATE_NOT_REGISTERED]
    assert no_resp_verdict != not_reg_verdict


def test_incomplete_verdict_differs_from_not_registered():
    """EXP-003 key contract: REJECT vs PASS_WITH_BLOCKS — distinguishable."""
    incomplete_verdict, _ = STATE_TO_VERDICT[STATE_REGISTERED_DECLARATION_INCOMPLETE]
    not_reg_verdict, _ = STATE_TO_VERDICT[STATE_NOT_REGISTERED]
    assert incomplete_verdict != not_reg_verdict


def test_all_four_states_have_distinct_verdict_signatures():
    """Each state must produce a unique (verdict, blocking_codes) signature."""
    sigs = {
        state: (verdict, tuple(codes))
        for state, (verdict, codes) in STATE_TO_VERDICT.items()
    }
    assert len(set(sigs.values())) == 4, (
        f"Expected 4 distinct verdict signatures; got {sigs}"
    )


# ---------------------------------------------------------------------------
# State detection: per fixture-arm.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n", range(1, 11))
def test_not_registered_arm(n):
    fname = f"_NOT_REGISTERED_synthproj_a{n:02d}.yaml"
    path = FIXTURE_ROOT / "not_registered" / fname
    assert path.exists(), f"fixture missing: {path}"
    assert detect_state(path) == STATE_NOT_REGISTERED


@pytest.mark.parametrize("n", range(1, 11))
def test_registered_no_response_arm(n):
    fname = f"synthproj_b{n:02d}.yaml"
    path = FIXTURE_ROOT / "registered_no_response" / fname
    assert path.exists(), f"fixture missing: {path}"
    assert detect_state(path) == STATE_REGISTERED_NO_RESPONSE


@pytest.mark.parametrize("n", range(1, 11))
def test_registered_declaration_incomplete_arm(n):
    fname = f"synthproj_c{n:02d}.yaml"
    path = FIXTURE_ROOT / "registered_declaration_incomplete" / fname
    assert path.exists(), f"fixture missing: {path}"
    assert detect_state(path) == STATE_REGISTERED_DECLARATION_INCOMPLETE


# ---------------------------------------------------------------------------
# analyze_file end-to-end.
# ---------------------------------------------------------------------------

def test_analyze_file_emits_required_keys():
    sample = FIXTURE_ROOT / "registered_no_response" / "synthproj_b01.yaml"
    result = analyze_file(sample)
    assert set(result.keys()) == {"file", "state", "verdict", "blocking_codes"}
    assert result["verdict"] == VERDICT_REJECT
    assert result["blocking_codes"] == [BLOCK_RUNTIME_RESPONSE_ABSENT]


def test_analyze_root_over_all_fixtures_distinguishes_three_states():
    results = analyze_root(FIXTURE_ROOT)
    assert len(results) == 30
    by_state: dict[str, list[dict]] = {}
    for r in results:
        by_state.setdefault(r["state"], []).append(r)
    assert set(by_state.keys()) == {
        STATE_NOT_REGISTERED,
        STATE_REGISTERED_NO_RESPONSE,
        STATE_REGISTERED_DECLARATION_INCOMPLETE,
    }
    assert len(by_state[STATE_NOT_REGISTERED]) == 10
    assert len(by_state[STATE_REGISTERED_NO_RESPONSE]) == 10
    assert len(by_state[STATE_REGISTERED_DECLARATION_INCOMPLETE]) == 10

    # The three observed verdicts must form at least two distinct values
    # (REJECT vs PASS_WITH_BLOCKS), which is the H1 measurement.
    verdicts = {r["state"]: r["verdict"] for r in results}
    assert verdicts[STATE_REGISTERED_NO_RESPONSE] != verdicts[STATE_NOT_REGISTERED]
    assert (
        verdicts[STATE_REGISTERED_DECLARATION_INCOMPLETE]
        != verdicts[STATE_NOT_REGISTERED]
    )


# ---------------------------------------------------------------------------
# Synthetic edge cases (registered_complete + canonical-index fallback).
# ---------------------------------------------------------------------------

def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_registered_complete_emits_pass(tmp_path):
    body = (
        "project: synthproj_complete\n"
        "knowledge_base:\n"
        "  sources:\n"
        "    - kind: LAB_NOTEBOOK.md\n"
        "      path: synthproj_complete/LAB_NOTEBOOK.md\n"
        "    - kind: CANON.md\n"
        "      path: synthproj_complete/CANON.md\n"
        "    - kind: experiments/\n"
        "      path: synthproj_complete/experiments/\n"
        "    - kind: PROMPT_EXP_MAP.md\n"
        "      path: synthproj_complete/PROMPT_EXP_MAP.md\n"
    )
    p = _write(tmp_path / "synthproj_complete.yaml", body)
    assert detect_state(p) == STATE_REGISTERED_COMPLETE
    result = analyze_file(p)
    assert result["verdict"] == VERDICT_PASS
    assert result["blocking_codes"] == []


def test_canonical_index_loading(tmp_path):
    (tmp_path / "alpha.yaml").write_text("# stub\n", encoding="utf-8")
    (tmp_path / "beta.yaml").write_text("# stub\n", encoding="utf-8")
    idx = load_canonical_index(tmp_path)
    assert idx == {"alpha", "beta"}


def test_canonical_index_absence_marks_not_registered(tmp_path):
    """A complete-looking adapter whose stem is absent from a non-empty
    canonical index must fall back to `not_registered`."""
    body = (
        "project: synthproj_orphan\n"
        "knowledge_base:\n"
        "  sources:\n"
        "    - kind: LAB_NOTEBOOK.md\n"
        "      path: synthproj_orphan/LAB_NOTEBOOK.md\n"
        "    - kind: CANON.md\n"
        "      path: synthproj_orphan/CANON.md\n"
        "    - kind: experiments/\n"
        "      path: synthproj_orphan/experiments/\n"
        "    - kind: PROMPT_EXP_MAP.md\n"
        "      path: synthproj_orphan/PROMPT_EXP_MAP.md\n"
    )
    p = _write(tmp_path / "adapters" / "synthproj_orphan.yaml", body)
    # Canonical index contains different stems, none matching.
    idx_dir = tmp_path / "canonical"
    (idx_dir).mkdir()
    (idx_dir / "different.yaml").write_text("# stub\n", encoding="utf-8")
    idx = load_canonical_index(idx_dir)
    assert detect_state(p, canonical_index=idx) == STATE_NOT_REGISTERED


def test_empty_canonical_index_does_not_force_not_registered(tmp_path):
    """If no canonical index is supplied (empty set), a complete-looking
    file is classified as registered_complete."""
    body = (
        "project: synthproj_x\n"
        "knowledge_base:\n"
        "  sources:\n"
        "    - kind: LAB_NOTEBOOK.md\n"
        "      path: x/LAB_NOTEBOOK.md\n"
        "    - kind: CANON.md\n"
        "      path: x/CANON.md\n"
        "    - kind: experiments/\n"
        "      path: x/experiments/\n"
        "    - kind: PROMPT_EXP_MAP.md\n"
        "      path: x/PROMPT_EXP_MAP.md\n"
    )
    p = _write(tmp_path / "synthproj_x.yaml", body)
    assert detect_state(p, canonical_index=set()) == STATE_REGISTERED_COMPLETE


def test_filename_marker_overrides_body(tmp_path):
    """`_NOT_REGISTERED_` prefix wins even if body looks complete."""
    body = (
        "project: synthproj_marked\n"
        "_runtime_response: present\n"
        "knowledge_base:\n"
        "  sources:\n"
        "    - kind: LAB_NOTEBOOK.md\n"
        "      path: marked/LAB_NOTEBOOK.md\n"
        "    - kind: CANON.md\n"
        "      path: marked/CANON.md\n"
        "    - kind: experiments/\n"
        "      path: marked/experiments/\n"
        "    - kind: PROMPT_EXP_MAP.md\n"
        "      path: marked/PROMPT_EXP_MAP.md\n"
    )
    p = _write(tmp_path / "_NOT_REGISTERED_synthproj_marked.yaml", body)
    assert detect_state(p) == STATE_NOT_REGISTERED


# ---------------------------------------------------------------------------
# CLI smoke.
# ---------------------------------------------------------------------------

def test_cli_json_output_against_fixtures():
    cmd = [
        sys.executable,
        "-m",
        "gsigmad.audit.check_adapter_ingest_completeness",
        "--root",
        str(FIXTURE_ROOT),
        "--json",
    ]
    out = subprocess.run(
        cmd, capture_output=True, text=True, cwd=str(REPO_ROOT), check=True
    )
    data = json.loads(out.stdout)
    assert isinstance(data, list)
    assert len(data) == 30
    states = {row["state"] for row in data}
    assert STATE_NOT_REGISTERED in states
    assert STATE_REGISTERED_NO_RESPONSE in states
    assert STATE_REGISTERED_DECLARATION_INCOMPLETE in states


def test_cli_missing_root_is_safe(tmp_path):
    missing = tmp_path / "does_not_exist"
    cmd = [
        sys.executable,
        "-m",
        "gsigmad.audit.check_adapter_ingest_completeness",
        "--root",
        str(missing),
        "--json",
    ]
    out = subprocess.run(
        cmd, capture_output=True, text=True, cwd=str(REPO_ROOT), check=True
    )
    assert json.loads(out.stdout) == []
