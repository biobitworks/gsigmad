"""
governance/kg/query.py — AQL-based cross-project experiment search.

All queries are read-only. Do not use this module for writes — use
governance.kg.writer instead.

Connects to the Overwatch ArangoDB instance (default: localhost:8531,
database "overwatch") via python-arango.  Uses bind variables for every
filter predicate — no string interpolation in AQL.

Exports
-------
find_experiments(project, classification, status, date_from, date_to,
                 protein, limit) -> list[dict] | dict
format_results_table(results) -> str

Reference: Phase 03 RESEARCH.md Pattern 5, namespace collision Pitfall 5.
"""
from __future__ import annotations

import os

# python-arango is optional — degrade gracefully when ArangoDB is absent.
try:
    from arango import ArangoClient  # type: ignore
    ARANGO_AVAILABLE = True
except ImportError:
    ARANGO_AVAILABLE = False
    ArangoClient = None  # type: ignore

# ---------------------------------------------------------------------------
# AQL template — bind variables keep all filter values out of the query string
# (prevents AQL injection; ArangoDB null == Python None via bind vars).
# ---------------------------------------------------------------------------
_AQL_FIND_EXPERIMENTS = """
FOR e IN experiments
  FILTER (@project == null OR e.project == @project)
  FILTER (@classification == null OR e.classification == @classification)
  FILTER (@status == null OR e.status == @status)
  FILTER (@date_from == null OR e.start_date >= @date_from)
  FILTER (@date_to == null OR e.start_date <= @date_to)
  FILTER (
    @protein == null OR
    LENGTH(
      FOR v, rel IN 1..1 OUTBOUND e GRAPH 'overwatch_graph'
        FILTER rel.rel_type == 'involves'
        FILTER IS_SAME_COLLECTION('entities', v)
        FILTER v.name == @protein OR v.gene_symbol == @protein
        LIMIT 1
        RETURN 1
    ) > 0
  )
  FILTER (
    (@doi == null AND @pmid == null) OR
    LENGTH(
      FOR v, rel IN 1..1 OUTBOUND e GRAPH 'overwatch_graph'
        FILTER rel.rel_type == 'references'
        FILTER IS_SAME_COLLECTION('publications', v)
        FILTER (@doi == null OR v.doi == @doi OR v.external_ids.doi == @doi)
        FILTER (@pmid == null OR v.pmid == @pmid OR v.external_ids.pmid == @pmid)
        LIMIT 1
        RETURN 1
    ) > 0
  )
  SORT e.exp_id ASC
  LIMIT @limit
  RETURN {
    exp_id: e.exp_id,
    project: e.project,
    classification: e.classification,
    status: e.status,
    last_run_id: e.run_ids[-1],
    provenance_sig: e._provenance.`prov:Agent`.`prov:id`
  }
"""

_KG_UNAVAILABLE = {"pass": False, "error": "KG_UNAVAILABLE: ArangoDB not reachable"}

# Maximum number of results returnable in a single query — hard cap.
_MAX_LIMIT = 100


def _get_db(
    arango_host: str = "localhost:8531",
    arango_db: str = "overwatch",
):
    """
    Return a python-arango database handle.

    Host can be overridden via the ARANGO_URL environment variable
    (format: "host:port", e.g. "localhost:8531").  Password is read from
    ARANGO_ROOT_PASSWORD (empty string if absent).

    verify=False is intentional for read-only queries — auth verification
    adds a round-trip that is unnecessary for reads and causes failures when
    the ArangoDB instance has auth disabled.
    """
    host = os.environ.get("ARANGO_URL", arango_host)
    password = os.environ.get("ARANGO_ROOT_PASSWORD", "")
    client = ArangoClient(hosts=f"http://{host}")
    return client.db(arango_db, username="root", password=password, verify=False)


def find_experiments(
    project: str | None = None,
    classification: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    protein: str | None = None,
    doi: str | None = None,
    pmid: str | None = None,
    limit: int = 100,
) -> list[dict] | dict:
    """
    Search the Overwatch experiments collection with optional filter predicates.

    Supports cross-project queries (project=None returns records from ALL
    projects).  The protein filter uses the involves edge traversal — it does
    NOT perform field matching on the experiment document itself.

    Output exp_id values are always formatted as "{project}:EXP-{N}" to
    prevent namespace collision across projects (e.g. "cellico:EXP-042").

    Parameters
    ----------
    project : str | None
        Restrict to a single project (e.g. "cellico").  None = all projects.
    classification : str | None
        One of CONFIRMATORY | EXPLORATORY | REPLICATION, or None.
    status : str | None
        One of planned | in_progress | completed | failed, or None.
    date_from : str | None
        ISO 8601 date string; only experiments with start_date >= date_from
        are returned.
    date_to : str | None
        ISO 8601 date string; only experiments with start_date <= date_to
        are returned.
    protein : str | None
        Protein name or gene symbol to filter by via the involves edge
        traversal.  None = no protein filter.
    limit : int
        Maximum number of results to return.  Capped at 100.

    Returns
    -------
    list[dict]
        Matching experiment records with exp_id prefixed by project.
        Empty list when no records match.
    dict
        {"pass": False, "error": "KG_UNAVAILABLE: ..."} when ArangoDB is
        not reachable or python-arango is not installed.
    """
    if not ARANGO_AVAILABLE:
        return dict(_KG_UNAVAILABLE)

    # Cap limit at the module maximum.
    effective_limit = min(int(limit), _MAX_LIMIT)

    bind_vars: dict = {
        "project": project,
        "classification": classification,
        "status": status,
        "date_from": date_from,
        "date_to": date_to,
        "protein": protein,
        "doi": doi,
        "pmid": pmid,
        "limit": effective_limit,
    }

    try:
        db = _get_db()
        cursor = db.aql.execute(_AQL_FIND_EXPERIMENTS, bind_vars=bind_vars)
        results = []
        for row in cursor:
            results.append(_add_project_prefix(row))
        return results
    except Exception:  # noqa: BLE001
        return dict(_KG_UNAVAILABLE)


def _add_project_prefix(row: dict) -> dict:
    """
    Ensure exp_id is prefixed with its project to prevent namespace collision.

    The raw ArangoDB exp_id field is "EXP-042"; the formatted version is
    "cellico:EXP-042".  If the prefix is already present (e.g. during a
    re-run or data migration), the row is returned unchanged.
    """
    exp_id: str = row.get("exp_id", "")
    project: str = row.get("project", "")
    if project and not exp_id.startswith(f"{project}:"):
        row = dict(row)  # do not mutate the original dict from the cursor
        row["exp_id"] = f"{project}:{exp_id}"
    return row


def format_results_table(results: list[dict]) -> str:
    """
    Format a list of find_experiments() results as a GitHub-flavored markdown table.

    Columns: EXP | Project | Classification | Status | Last Run | Provenance Sig

    Parameters
    ----------
    results : list[dict]
        Output of find_experiments().

    Returns
    -------
    str
        Markdown table string, or a human-readable message when results is empty.
    """
    if not results:
        return "No experiments found matching the specified filters."

    header = "| EXP | Project | Classification | Status | Last Run | Provenance Sig |"
    separator = "| --- | --- | --- | --- | --- | --- |"

    rows = []
    for r in results:
        exp_id = r.get("exp_id", "")
        project = r.get("project", "")
        classification = r.get("classification", "")
        status = r.get("status", "")
        last_run = r.get("last_run_id") or "\u2014"
        prov_sig = r.get("provenance_sig") or "\u2014"
        rows.append(
            f"| {exp_id} | {project} | {classification} | {status} | {last_run} | {prov_sig} |"
        )

    return "\n".join([header, separator] + rows)
