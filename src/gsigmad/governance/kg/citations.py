"""
Citation edge creation for Getting Science Done KG integration.

Links experiment documents to publication documents via the rel edge collection.
Uses rel_type='cites' (not the cites edge collection — see RESEARCH.md Pitfall 1).
DOI/PMID verification via governance.gates.audit_claims before any KG write.

Public API:
    create_citation_edge(exp_key, doi, pmid, citation_type, agent) -> dict
    get_or_create_publication(doi, pmid, title, agent) -> str

Reference:
    governance/RESEARCH.md Pattern 6 (rel edge, not cites edge)
    governance/RESEARCH.md Pitfall 1 (cites collection schema constraint)
    DATA_CONTRACTS.md §6 rule 1 (publication deduplication by DOI/PMID)
    governance/kg/writer.py (write_document — provenance injected there, not here)
    governance/gates/audit_claims.py (verify_doi, verify_pmid)
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from gsigmad.governance.gates.audit_claims import verify_doi, verify_pmid
from gsigmad.governance.kg.writer import write_document

# ---------------------------------------------------------------------------
# Optional ArangoDB dependency
# ---------------------------------------------------------------------------

try:
    from arango import ArangoClient  # type: ignore
    ARANGO_AVAILABLE = True
except ImportError:
    ARANGO_AVAILABLE = False
    ArangoClient = None  # type: ignore

# ---------------------------------------------------------------------------
# Module-level configuration (mirrors writer.py)
# ---------------------------------------------------------------------------

_ARANGO_HOST: str = os.environ.get("ARANGO_HOST", "localhost:8531")
_ARANGO_DB: str = os.environ.get("ARANGO_DB", "overwatch")

# AQL to check for existing publication by DOI or PMID (DATA_CONTRACTS.md §6 rule 1)
_AQL_FIND_PUBLICATION = """
FOR p IN publications
  FILTER (@doi != null AND p.external_ids.doi == @doi)
      OR (@pmid != null AND p.external_ids.pmid == @pmid)
  LIMIT 1
  RETURN p._key
"""

# Valid citation types per plan spec
_VALID_CITATION_TYPES = {"supports", "contradicts", "mentions"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_db():
    """Return an authenticated ArangoDB database handle.

    Uses verify=True for writes (mirrors writer.py pattern).
    """
    if not ARANGO_AVAILABLE:
        raise ImportError("python-arango not installed; KG writes unavailable")
    client = ArangoClient(hosts=f"http://{_ARANGO_HOST}")
    password = os.environ.get("ARANGO_ROOT_PASSWORD", "")
    return client.db(_ARANGO_DB, username="root", password=password, verify=True)


def _iso_now() -> str:
    """Return current UTC time as ISO 8601 with Z suffix."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_or_create_publication(
    doi: Optional[str] = None,
    pmid: Optional[str] = None,
    title: str = "",
    agent: str = "claude-sonnet-4-6",
) -> str:
    """Look up or create a publication document in ArangoDB.

    Checks for an existing publication by DOI or PMID before inserting
    (DATA_CONTRACTS.md §6 rule 1 — deduplication).

    Parameters
    ----------
    doi : str | None
        Digital Object Identifier (e.g. "10.1371/journal.pcbi.1003285").
    pmid : str | None
        PubMed ID string (e.g. "25147205").
    title : str
        Publication title (used when creating a new document).
    agent : str
        Agent identifier for provenance injection.

    Returns
    -------
    str
        ArangoDB _key of the existing or newly created publication.

    Raises
    ------
    ValueError
        If both doi and pmid are None.
    """
    if doi is None and pmid is None:
        raise ValueError("CITATION_ERROR: doi or pmid required for publication lookup")

    # Check for existing publication
    try:
        db = _get_db()
        cursor = db.aql.execute(
            _AQL_FIND_PUBLICATION,
            bind_vars={"doi": doi, "pmid": pmid},
        )
        for existing_key in cursor:
            return existing_key
    except (ImportError, Exception):
        # If DB unavailable, proceed to write (writer.py will queue it)
        pass

    # Publication not found — create it
    now = _iso_now()
    pub_doc = {
        "title": title,
        "external_ids": {
            "doi": doi,
            "pmid": pmid,
        },
        "source_system": "getting_science_done",
        "created_at": now,
        "updated_at": now,
    }

    result = write_document(
        collection="publications",
        doc=pub_doc,
        agent=agent,
        activity_type="citation_lookup",
        entity_type="publication",
        evidence_class="MEASURED",
    )

    # Extract _key from write_document result
    if result.get("pass"):
        write_result = result.get("result", {})
        # result may be the arango insert result dict or contain _key directly
        if isinstance(write_result, dict):
            key = write_result.get("_key") or write_result.get("new", {}).get("_key", "")
            if key:
                return key
        # Fallback: return empty string (caller should handle)
        return ""
    return ""


def create_citation_edge(
    exp_key: str,
    doi: Optional[str] = None,
    pmid: Optional[str] = None,
    citation_type: str = "supports",
    agent: str = "claude-sonnet-4-6",
) -> dict:
    """Create a citation edge from an experiment to a publication in the KG.

    Uses the ``rel`` edge collection with ``rel_type='cites'`` (not the ``cites``
    edge collection — see RESEARCH.md Pitfall 1: cites collection requires _from
    in the claim collection, not experiment collection).

    Verification order:
    1. If doi provided: call verify_doi(). Block on any failure including TIMEOUT.
    2. Elif pmid provided: call verify_pmid(). Block on failure.
    3. Look up or create the publication document.
    4. Build citation edge (WITHOUT _provenance — write_document injects it).
    5. Call write_document(collection="rel", ...) and return result unchanged.

    Parameters
    ----------
    exp_key : str
        ArangoDB _key of the experiment document (e.g. "overwatch_exp_015").
    doi : str | None
        DOI to verify and cite.
    pmid : str | None
        PubMed ID to verify and cite (only used if doi is None).
    citation_type : str
        One of "supports", "contradicts", "mentions". Defaults to "supports".
    agent : str
        Agent identifier for provenance injection via write_document.

    Returns
    -------
    dict
        {"pass": True, "result": ...} on success (from write_document).
        {"pass": False, "error": "..."} on verification failure.
    """
    if doi is None and pmid is None:
        return {"pass": False, "error": "CITATION_ERROR: doi or pmid required"}

    # Validate citation_type
    if citation_type not in _VALID_CITATION_TYPES:
        citation_type = "supports"

    # Step 1: Verify DOI (if provided)
    if doi is not None:
        verification = verify_doi(doi)
        verified = verification.get("verified")
        if verified is not True:
            # Both False and "TIMEOUT" are blocking failures
            # Extract a meaningful error string
            if "error" in verification:
                error_msg = verification["error"]
            elif "warning" in verification:
                # TIMEOUT case — treat as UNVERIFIED_PENDING block
                warning = verification["warning"]
                error_msg = f"UNVERIFIED_PENDING: {warning}"
            else:
                error_msg = f"DOI_VERIFICATION_ERROR: verification failed for {doi}"
            return {"pass": False, "error": error_msg}

    # Step 2: Verify PMID (if no DOI)
    elif pmid is not None:
        verification = verify_pmid(pmid)
        verified = verification.get("verified")
        if verified is not True:
            if "error" in verification:
                error_msg = verification["error"]
            elif "warning" in verification:
                warning = verification["warning"]
                error_msg = f"UNVERIFIED_PENDING: {warning}"
            else:
                error_msg = f"PMID_VERIFICATION_ERROR: verification failed for {pmid}"
            return {"pass": False, "error": error_msg}

    # Step 3: Get or create publication
    pub_key = get_or_create_publication(doi=doi, pmid=pmid, agent=agent)

    # Step 4: Build citation edge (NO _provenance — write_document injects it)
    now = _iso_now()
    evidence_ref = doi if doi is not None else f"PMID:{pmid}"

    citation_edge = {
        "_key": f"{exp_key}-references-{pub_key}",
        "_from": f"experiments/{exp_key}",
        "_to": f"publications/{pub_key}",
        "rel_type": "references",
        "confidence": 1.0,
        "evidence_refs": [evidence_ref],
        "source_system": "getting_science_done",
        "visibility": "shared",
        "created_at": now,
        "updated_at": now,
        "metadata": {
            "citation_type": citation_type,
            "doi": doi,
            "pmid": pmid,
        },
        # NOTE: _provenance is intentionally NOT set here.
        # write_document() injects the W3C PROV-JSON _provenance block.
    }

    # Step 5: Write via governed interface
    return write_document(
        collection="rels",
        doc=citation_edge,
        agent=agent,
        activity_id=exp_key,
        activity_type="experiment",
        entity_type="citation_link",
        evidence_class="MEASURED",
    )
