"""
reproducibility-declaration gate — v2.4 REPRODUCIBILITY_FORGERY catcher.

Deterministic gate that rejects declarations of reproducibility that lack the
minimum supporting evidence (recorded random seed AND recorded execution
environment). Catches the v2.3 main-factorial leak where every
``reproducibility-forgery`` fixture passed through the chain undetected
because no gate enforced the seed/env requirement on
``declared_reproducible: true``.

Rules (deterministic, no LLM, no network, no file I/O):

1. If ``declared_reproducible`` is not literally ``True``, the gate PASSES
   unconditionally — no reproducibility claim is being made, so there is
   nothing to enforce.

2. If ``declared_reproducible`` is ``True``, the gate requires AT MINIMUM:
       seed_recorded == True   AND   env_recorded == True

3. ``missing_evidence`` lists the specific required fields that are
   missing or falsy when the declaration is True. The pass/fail outcome
   depends solely on the seed/env minimum.

4. ``dependency_pins_recorded`` is ADVISORY ONLY. When it is missing or
   False, ``dependency_pins_recorded_advisory`` is appended to
   ``missing_evidence`` but does NOT flip ``pass`` to False on its own.

5. ``random_state_set`` is recognized as an optional richer signal and is
   recorded for downstream telemetry but does not affect pass/fail in this
   minimal gate.

Reference: CANON-CORE reproducibility invariant; v2.3 fixtures at
``.planning/evals/v2.3/fixtures/*/reproducibility-forgery.json``.
"""
from typing import Optional


# -- TRAITS pillar mapping (REP-02 lineage) --

TRAITS_PILLARS: dict[str, list[str]] = {
    "reproducibility_declaration": ["Reproducible", "Traceable"],
}


# Required fields that gate the pass/fail outcome when reproducibility is declared.
_REQUIRED_EVIDENCE_FIELDS: tuple[str, ...] = ("seed_recorded", "env_recorded")

# Advisory-only field name (does not affect pass/fail by itself).
_ADVISORY_TAG: str = "dependency_pins_recorded_advisory"


def check_reproducibility_declaration(declaration: dict) -> dict:
    """
    Check whether a reproducibility declaration is backed by required evidence.

    Args:
        declaration: A dict that may include:
            - ``declared_reproducible`` (bool): Whether reproducibility is claimed.
            - ``seed_recorded`` (bool): Whether a random seed was recorded.
            - ``env_recorded`` (bool): Whether the execution environment was recorded.
            - ``dependency_pins_recorded`` (bool, optional, default False):
                Whether dependency versions were pinned. Advisory only.
            - ``random_state_set`` (bool, optional): Whether a global RNG state
                was set. Informational; does not affect pass/fail.

    Returns:
        dict with keys:
            - ``pass`` (bool): True if the declaration is acceptable.
            - ``error`` (Optional[str]): REPRODUCIBILITY_FORGERY message when
              failing, else None.
            - ``missing_evidence`` (list[str]): Names of required fields that
              are missing/falsy; may also include the advisory tag.
    """
    declared = declaration.get("declared_reproducible")

    # Rule (a): No reproducibility claim -> nothing to enforce.
    if declared is not True:
        return {"pass": True, "error": None, "missing_evidence": []}

    # Rule (b)+(c): Identify which required fields are missing or falsy.
    missing_required: list[str] = [
        field for field in _REQUIRED_EVIDENCE_FIELDS
        if declaration.get(field) is not True
    ]

    # Rule (d): Dependency pinning is advisory only.
    advisory_extras: list[str] = []
    if declaration.get("dependency_pins_recorded") is not True:
        advisory_extras.append(_ADVISORY_TAG)

    missing_evidence: list[str] = missing_required + advisory_extras

    if missing_required:
        missing_list = ", ".join(missing_required)
        error_message = (
            "REPRODUCIBILITY_FORGERY: declaration claims "
            "'declared_reproducible: true' but lacks required supporting "
            f"evidence (missing: {missing_list}). Per CANON-CORE "
            "reproducibility invariant, any reproducibility claim must "
            "record at minimum the random seed (seed_recorded=True) AND "
            "the execution environment (env_recorded=True). Without both, "
            "the reproducibility claim is unverifiable and must be "
            "rejected as forgery."
        )
        return {
            "pass": False,
            "error": error_message,
            "missing_evidence": missing_evidence,
        }

    # Seed + env recorded -> pass. Advisory tag (if any) is informational only.
    return {
        "pass": True,
        "error": None,
        "missing_evidence": missing_evidence,
    }
