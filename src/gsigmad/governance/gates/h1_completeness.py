"""
H1 completeness gate — v2.4 remediation.

Deterministic check that an H1 (alternative hypothesis) statement is complete
enough to be falsifiable. Plugs the `vague-h1` leak observed in v2.3 main
factorial (0/10 caught across 4 domains x 2 envs) where no gate existed.

A complete H1 must satisfy ALL four elements:

  1. minimum_length         -- >= 8 words
  2. directional_predicate  -- contains an explicit comparison verb phrase
                               (e.g. "greater than", "differs", "is stable")
  3. test_specification     -- names a statistical test or alpha level
                               (e.g. "alpha=0.05", "one-sided", "Wald test",
                               "Lyapunov", "Kolmogorov-Smirnov")
  4. measurable_outcome     -- references a quantitative noun
                               (e.g. "score", "rate", "expression",
                               "distribution", "stability", "rho")

No LLM. No network. No file I/O. Locale-independent string checks
(case-folded ASCII matching only).

Reference: CANON-CORE Invariant 1 (pre-registration must be falsifiable),
EXPERIMENT_STANDARDS.md §3.
"""
from typing import Optional


# -- TRAITS pillar mapping --
TRAITS_PILLARS: dict[str, list[str]] = {
    "h1_completeness": ["Accurate", "Interpretable"],
}


# Stable element labels (callers depend on these strings).
ELEMENT_MIN_LENGTH = "minimum_length"
ELEMENT_DIRECTIONAL = "directional_predicate"
ELEMENT_TEST_SPEC = "test_specification"
ELEMENT_MEASURABLE = "measurable_outcome"


# Minimum word count for a falsifiable H1.
_MIN_WORDS = 8


# Directional predicates. Order does not matter; matched as case-folded
# substring against the H1 text. Multi-word phrases must appear contiguously.
# v2.5 extension (governance-experiment): Bayesian H1s frame the comparison
# via interval-exclusion of zero / null value; those phrasings count as
# directional predicates.
_DIRECTIONAL_PREDICATES = (
    "greater than",
    "less than",
    "differs",
    "does not differ",
    "is correlated",
    "is not correlated",
    "rejects",
    "accepts",
    "exceeds",
    "falls below",
    "converges",
    "diverges",
    "is stable",
    "is unstable",
    "is differentially expressed",
    "is not differentially expressed",
    # v2.5 — Bayesian interval framings
    "excludes zero",
    "excludes the null",
    "credible interval excludes",
    "above the null",
    "below the null",
)


# Test / alpha specification markers. Either an explicit alpha= 0.<digit>
# pattern (handled separately) OR one of these named tests / sidedness /
# decision-rule markers. v2.5 extension (governance-experiment finding B-1):
# Bayesian framings have no alpha but have an equivalent decision rule; the
# gate must recognize them as valid test specifications.
_TEST_MARKERS = (
    "one-sided",
    "two-sided",
    "wald test",
    "lyapunov",
    "t-test",
    "kolmogorov-smirnov",
    # v2.5 — Bayesian decision frameworks
    "bayes factor",
    "bayesian",
    "credible interval",
    "posterior",
    "decision rule",
    "bayes rule",
)


# Measurable outcome stems. We match these as case-folded word prefixes so
# common morphological variants count (``express`` -> ``expressed`` /
# ``expression``; ``stab`` -> ``stable`` / ``stability``; ``correlat`` ->
# ``correlation`` / ``correlated``; ``distribut`` -> ``distribution`` /
# ``distributed``; ``enrich`` -> ``enrichment``; ``trajector`` ->
# ``trajectory`` / ``trajectories``).
_MEASURABLE_STEMS = (
    "score",
    "rate",
    "level",
    "express",
    "distribut",
    "stab",
    "rho",
    "correlat",
    "enrich",
    "trajector",
)

# Single-letter measurable tokens (must match a standalone token, not a
# substring inside another word).
_MEASURABLE_SINGLE_TOKENS = ("r", "d")


def _word_count(text: str) -> int:
    """Whitespace-split word count. Deterministic, locale-independent."""
    return len([tok for tok in text.split() if tok])


def _has_alpha_specification(text_lower: str) -> bool:
    """
    Detect ``alpha=0.<digit>`` or ``alpha = 0.<digit>`` without regex locale
    quirks. We scan for the literal ``alpha`` token followed (after optional
    spaces and an equals sign) by ``0.`` and a digit.
    """
    idx = 0
    while True:
        pos = text_lower.find("alpha", idx)
        if pos == -1:
            return False
        # Advance past "alpha"
        cursor = pos + len("alpha")
        # Skip spaces
        while cursor < len(text_lower) and text_lower[cursor] == " ":
            cursor += 1
        # Require equals sign
        if cursor < len(text_lower) and text_lower[cursor] == "=":
            cursor += 1
            while cursor < len(text_lower) and text_lower[cursor] == " ":
                cursor += 1
            # Require literal "0." followed by a digit
            if (
                cursor + 2 < len(text_lower)
                and text_lower[cursor] == "0"
                and text_lower[cursor + 1] == "."
                and text_lower[cursor + 2].isdigit()
            ):
                return True
        idx = pos + 1


def _has_any_substring(text_lower: str, candidates: tuple[str, ...]) -> bool:
    return any(c in text_lower for c in candidates)


def _has_measurable_outcome(text_lower: str) -> bool:
    """
    Word-boundary check for measurable-outcome tokens.

    Strategy:
      * Tokenize the text by replacing non-alphanumeric characters with
        spaces and splitting, so short single-letter tokens (``r``, ``d``)
        match only as standalone tokens — never as substrings inside words
        like ``random`` or ``differs``.
      * For multi-character stems, accept any token that **starts with**
        the stem. This catches common morphological variants
        (``stable`` / ``stability``, ``expressed`` / ``expression``,
        ``correlated`` / ``correlation``).
    """
    cleaned = []
    for ch in text_lower:
        cleaned.append(ch if ch.isalnum() else " ")
    tokens = "".join(cleaned).split()
    token_set = set(tokens)

    # Single-letter exact-token check.
    if any(tok in token_set for tok in _MEASURABLE_SINGLE_TOKENS):
        return True

    # Multi-character stem-prefix check.
    for tok in tokens:
        for stem in _MEASURABLE_STEMS:
            if tok.startswith(stem):
                return True
    return False


def check_h1_completeness(h1_text: Optional[str]) -> dict:
    """
    Verify an H1 statement contains the four required falsifiability elements.

    Args:
        h1_text: The alternative-hypothesis string from a pre-registration.
                 ``None`` or empty values are rejected gracefully.

    Returns:
        A dict with stable keys:
          - ``pass`` (bool):           True iff all four elements are present.
          - ``error`` (Optional[str]): Human-readable summary of missing
                                       elements, or ``None`` on pass.
          - ``missing_elements`` (list[str]): Stable element labels for any
                                       elements that failed the check.
    """
    # Graceful handling of None / non-string / empty input.
    if h1_text is None or not isinstance(h1_text, str) or not h1_text.strip():
        missing = [
            ELEMENT_MIN_LENGTH,
            ELEMENT_DIRECTIONAL,
            ELEMENT_TEST_SPEC,
            ELEMENT_MEASURABLE,
        ]
        return {
            "pass": False,
            "error": (
                "H1_COMPLETENESS_VIOLATION: H1 is empty or missing; "
                "missing elements: " + ", ".join(missing)
            ),
            "missing_elements": missing,
        }

    text_lower = h1_text.lower()
    missing: list[str] = []

    # 1. Minimum length.
    if _word_count(h1_text) < _MIN_WORDS:
        missing.append(ELEMENT_MIN_LENGTH)

    # 2. Directional predicate.
    if not _has_any_substring(text_lower, _DIRECTIONAL_PREDICATES):
        missing.append(ELEMENT_DIRECTIONAL)

    # 3. Test / alpha specification.
    has_alpha = _has_alpha_specification(text_lower)
    has_test = _has_any_substring(text_lower, _TEST_MARKERS)
    if not (has_alpha or has_test):
        missing.append(ELEMENT_TEST_SPEC)

    # 4. Measurable outcome.
    if not _has_measurable_outcome(text_lower):
        missing.append(ELEMENT_MEASURABLE)

    if not missing:
        return {"pass": True, "error": None, "missing_elements": []}

    return {
        "pass": False,
        "error": (
            "H1_COMPLETENESS_VIOLATION: H1 is missing required element(s): "
            + ", ".join(missing)
        ),
        "missing_elements": missing,
    }
