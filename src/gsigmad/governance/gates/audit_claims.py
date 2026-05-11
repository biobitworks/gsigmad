"""
audit-claims effect size and DOI verification enforcement — STAT-03.

Extends the existing audit-claims skill with two mandatory checks:
1. Reject claims citing p-value without effect size and 95% CI
2. Verify every cited DOI/PMID against CrossRef/PubMed

Reference: CANON-CORE Invariant 6 (effect size mandatory), EXPERIMENT_STANDARDS.md §4
"""
import re
from typing import Optional

import requests

# -- TRAITS pillar mapping (REP-02) --

TRAITS_PILLARS: dict[str, list[str]] = {
    "audit_claims": ["Accurate", "Interpretable"],
}


# ─── Regex patterns ───────────────────────────────────────────────────────────
# p-value detection: requires numeric comparison (prevents "pH value" false positives)
PVALUE_PATTERN = re.compile(
    r"\bp\s*[<>=≤≥]\s*0\.\d+|\bp[-\s]?value\s*[:=]\s*[\d.]+",
    re.IGNORECASE
)

# Effect size detection: Cohen's d/f, eta-squared (η²), r², Pearson r, Cramér's V,
# Hedges' g, odds ratio, hazard ratio, partial eta-squared
EFFECT_SIZE_PATTERN = re.compile(
    r"cohen['\u2019]?s?\s+[dfh]|cohens?\s+[dfh]|"
    r"eta[.\s-]?squared|\bη²|\bη\^2|"
    r"\br²|\br\^2|\bpearson\s+r|\bspearman\s+rho|"
    r"cramer['\u2019]?s?\s+v|cram[eé]r['\u2019]?s?\s+v|"
    r"hedges['\u2019]?\s+g|"
    r"odds\s+ratio|\bOR\s*=|\bOR\s*[<>]|"
    r"hazard\s+ratio|\bHR\s*=|"
    r"\beffect\s+size\b|"
    r"\bd\s*=\s*[\d.]+|\bη²\s*=\s*[\d.]+|"
    r"\br\s*=\s*[-]?0\.\d+",
    re.IGNORECASE
)

# CI detection: [0.38, 0.86] or 95% CI or (0.22, 0.68) or confidence interval
CI_PATTERN = re.compile(
    r"\[[\d.]+,\s*[\d.]+\]|"
    r"\d+%\s*CI\b|"
    r"\bCI\b.*[\[(][\d.]+|"
    r"confidence\s+interval|"
    r"\([\d.]+,\s*[\d.]+\)",
    re.IGNORECASE
)

# DOI and PMID detection
DOI_PATTERN = re.compile(r"10\.\d{4,}/\S+")
PMID_PATTERN = re.compile(r"PMID[:\s]+(\d+)|pmid[:\s]+(\d+)")


# ─── Effect size reporting check ─────────────────────────────────────────────

def check_effect_size_reporting(claim_text: str) -> dict:
    """
    Check that a claim citing a p-value also reports an effect size and CI.

    Args:
        claim_text: The scientific claim text to check.

    Returns:
        {"pass": bool, "error": Optional[str], "recommendation": Optional[str]}
    """
    has_pvalue = bool(PVALUE_PATTERN.search(claim_text))
    has_effect_size = bool(EFFECT_SIZE_PATTERN.search(claim_text))
    has_ci = bool(CI_PATTERN.search(claim_text))

    # No p-value: nothing to enforce
    if not has_pvalue:
        return {"pass": True, "error": None, "recommendation": None}

    # Has p-value but no effect size
    if not has_effect_size:
        return {
            "pass": False,
            "error": (
                "STAT_RIGOR_VIOLATION: Claim cites p-value without an effect size. "
                "Per CANON-CORE Invariant 6 and EXPERIMENT_STANDARDS.md §4, every statistical "
                "test must report an effect size measure (Cohen's d, η², Pearson r, Cramér's V, "
                "hazard ratio, or equivalent) alongside a 95% confidence interval. "
                "p-values alone do not indicate the magnitude or practical significance of an effect."
            ),
            "recommendation": (
                "Add: 'Effect size: [measure] = [value] (95% CI: [lower, upper])' "
                "Example: 'Cohen's d = 0.62 (95% CI: [0.38, 0.86])'"
            )
        }

    # Has effect size but no CI
    if has_effect_size and not has_ci:
        return {
            "pass": False,
            "error": (
                "STAT_RIGOR_VIOLATION: Effect size reported without a confidence interval. "
                "Per CANON-CORE Invariant 6, an effect size measure alone is insufficient — "
                "report 95% confidence interval to quantify estimation uncertainty."
            ),
            "recommendation": (
                "Add confidence interval: "
                "Example: \"Cohen's d = 0.45 (95% CI: [0.22, 0.68])\""
            )
        }

    # Both effect size and CI present — passes
    return {"pass": True, "error": None, "recommendation": None}


# ─── Calibration evidence check (CAL-02, CAL-03) ────────────────────────────

def check_calibration_evidence(claim: dict) -> dict:
    """
    Check that a claim referencing scored outputs has calibration evidence.

    Per CAL-02: Claims with calibrated=True must have sufficient evidence
    (method + at least one of: tool, metric, or procedure_ref).
    Per CAL-03: Claims with uncalibrated scored fields get CALIBRATION_ADVISORY.

    Works on plain dicts (same pattern as check_effect_size_reporting).
    Does NOT import CalibrationDeclaration — checks dict keys directly.

    Args:
        claim: A claim dict, optionally containing ``scored_fields`` key.

    Returns:
        {"pass": bool, "error": Optional[str], "advisory": Optional[str]}
    """
    scored_fields = claim.get("scored_fields")
    if not scored_fields:
        return {"pass": True, "error": None, "advisory": None}

    failures: list[str] = []
    advisories: list[str] = []

    for sf in scored_fields:
        field_name = sf.get("name", "<unknown>")
        cal = sf.get("calibration")

        # No calibration block or calibrated=False -> advisory
        if cal is None or not cal.get("calibrated", False):
            advisories.append(
                f"CALIBRATION_ADVISORY: scored field '{field_name}' has no "
                f"calibration evidence. Consider calibrating scored outputs "
                f"before using them in scientific claims."
            )
            continue

        # calibrated=True -> check evidence sufficiency
        method = cal.get("method")
        has_method = method is not None and method != "none"
        has_tool = bool(cal.get("tool"))
        has_metric = (cal.get("brier_score") is not None
                      or cal.get("ece_score") is not None)
        has_ref = bool(cal.get("procedure_ref"))

        if not has_method:
            failures.append(
                f"CALIBRATION_EVIDENCE_REJECTED: scored field '{field_name}' "
                f"declares calibrated=True but method is {method!r}. "
                f"A calibration method must be specified."
            )
        elif not (has_tool or has_metric or has_ref):
            failures.append(
                f"CALIBRATION_EVIDENCE_REJECTED: scored field '{field_name}' "
                f"declares calibrated=True with method='{method}' but provides "
                f"no supporting evidence (need at least one of: tool, "
                f"brier_score, ece_score, procedure_ref)."
            )

    return {
        "pass": len(failures) == 0,
        "error": "; ".join(failures) if failures else None,
        "advisory": "; ".join(advisories) if advisories else None,
    }


# ─── DOI verification ─────────────────────────────────────────────────────────

def verify_doi(doi: str, timeout: int = 10) -> dict:
    """
    Verify that a DOI exists in CrossRef.

    Per Pitfall 5: timeout returns UNVERIFIED_PENDING (not hard block);
    hard block only on explicit 404 (DOI does not exist).

    Args:
        doi: DOI string, e.g. "10.1371/journal.pcbi.1003285"
        timeout: Request timeout in seconds (default 10)

    Returns:
        {"verified": True, "title": str}  — DOI exists in CrossRef
        {"verified": False, "error": "DOI_NOT_FOUND: ..."}  — DOI does not exist (404)
        {"verified": "TIMEOUT", "warning": "..."}  — Network timeout (soft fail)
        {"verified": False, "error": "..."}  — Other HTTP error
    """
    # Clean the DOI (remove trailing punctuation that may have been captured by regex)
    doi = doi.rstrip(".,);")
    url = f"https://api.crossref.org/works/{doi}"

    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "GSD-AuditClaims/1.0 (mailto:science@gsd.local)"}
        )
    except requests.Timeout:
        return {
            "verified": "TIMEOUT",
            "warning": (
                f"DOI_VERIFICATION_TIMEOUT: Could not reach CrossRef for {doi} within {timeout}s. "
                "Claim marked UNVERIFIED_PENDING. "
                "Re-run audit-claims when network is available. "
                "Claims with UNVERIFIED_PENDING status cannot support CONFIRMATORY evidence."
            )
        }
    except requests.RequestException as e:
        return {
            "verified": "TIMEOUT",
            "warning": (
                f"DOI_VERIFICATION_ERROR: Network error for {doi}: {e}. "
                "Claim marked UNVERIFIED_PENDING."
            )
        }

    if resp.status_code == 404:
        return {
            "verified": False,
            "error": (
                f"DOI_NOT_FOUND: {doi} does not exist in CrossRef. "
                "Verify the DOI is correct. If the publication is preprint-only, "
                "use the arXiv ID or bioRxiv DOI instead."
            )
        }

    if resp.status_code == 200:
        try:
            data = resp.json()
            title = ""
            titles = data.get("message", {}).get("title", [])
            if titles:
                title = str(titles[0])[:120]
            return {"verified": True, "title": title}
        except Exception:
            return {"verified": True, "title": ""}

    return {
        "verified": False,
        "error": f"DOI_VERIFICATION_ERROR: CrossRef returned HTTP {resp.status_code} for {doi}."
    }


def verify_pmid(pmid: str, timeout: int = 10) -> dict:
    """
    Verify that a PMID exists in PubMed eutils.

    Per Pitfall 5: timeout returns UNVERIFIED_PENDING (not hard block).

    Args:
        pmid: PubMed ID string (digits only), e.g. "25147205"
        timeout: Request timeout in seconds (default 10)

    Returns:
        {"verified": True, "title": str}  — PMID found in PubMed
        {"verified": False, "error": "PMID_NOT_FOUND: ..."}  — PMID not found
        {"verified": "TIMEOUT", "warning": "..."}  — Network timeout
    """
    pmid = pmid.strip()
    url = (
        f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        f"?db=pubmed&id={pmid}&retmode=json"
    )

    try:
        resp = requests.get(url, timeout=timeout)
    except requests.Timeout:
        return {
            "verified": "TIMEOUT",
            "warning": (
                f"PMID_VERIFICATION_TIMEOUT: Could not reach PubMed for PMID:{pmid} within {timeout}s. "
                "Claim marked UNVERIFIED_PENDING. "
                "Re-run audit-claims when network is available."
            )
        }
    except requests.RequestException as e:
        return {
            "verified": "TIMEOUT",
            "warning": f"PMID_VERIFICATION_ERROR: Network error for PMID:{pmid}: {e}. Claim marked UNVERIFIED_PENDING."
        }

    if resp.status_code == 200:
        try:
            data = resp.json()
            result = data.get("result", {})
            uids = result.get("uids", [])
            if pmid in result or (uids and pmid in uids):
                title = result.get(pmid, {}).get("title", "")[:120]
                return {"verified": True, "title": title}
        except Exception:
            pass

    return {
        "verified": False,
        "error": f"PMID_NOT_FOUND: PMID:{pmid} not found in PubMed. Verify the PMID is correct."
    }


def audit_claims_gate(claims: list, verify_citations: bool = True) -> dict:
    """
    Run the full audit-claims gate on a list of scientific claims.

    Args:
        claims: List of claim dicts, each with "text" and optionally "citations" (list of DOI/PMID strings).
        verify_citations: If True, verify DOIs/PMIDs against CrossRef/PubMed. Default True.

    Returns:
        {"pass": bool, "failures": list[dict], "warnings": list[str]}
        failures: List of {"claim_index": int, "text": str, "error": str}
        warnings: UNVERIFIED_PENDING citations (timeout cases)
    """
    failures = []
    warnings = []

    for i, claim in enumerate(claims):
        text = claim.get("text", "")

        # Check 1: Effect size enforcement
        es_result = check_effect_size_reporting(text)
        if not es_result["pass"]:
            failures.append({
                "claim_index": i,
                "text": text[:100],
                "error": es_result["error"],
                "recommendation": es_result.get("recommendation")
            })

        # Check 2: Citation verification
        if verify_citations and "citations" in claim:
            for citation in claim["citations"]:
                citation = str(citation).strip()
                if DOI_PATTERN.match(citation):
                    result = verify_doi(citation)
                elif citation.isdigit():
                    result = verify_pmid(citation)
                else:
                    continue

                if result.get("verified") is False:
                    failures.append({
                        "claim_index": i,
                        "citation": citation,
                        "error": result["error"]
                    })
                elif result.get("verified") == "TIMEOUT":
                    warnings.append(result["warning"])

        # Check 3: Calibration evidence (CAL-02, CAL-03)
        cal_result = check_calibration_evidence(claim)
        if not cal_result["pass"]:
            failures.append({
                "claim_index": i,
                "text": text[:100],
                "error": cal_result["error"],
            })
        if cal_result.get("advisory"):
            warnings.append(cal_result["advisory"])

    return {
        "pass": len(failures) == 0,
        "failures": failures,
        "warnings": warnings
    }
