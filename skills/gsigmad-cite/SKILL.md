---
name: gsigmad-cite
description: "Link an experiment to a publication (PMID or DOI) in the Knowledge Graph. Use when you want to record that an EXP result is supported by, contradicted by, or mentioned in a publication. Calls create_citation_edge() via the governed KG write interface."
allowed-tools: [Read, Bash]
---

# Cite ($citation-edge-creation)

Link an EXP record to a verified publication in the Overwatch Knowledge Graph. Uses `create_citation_edge()` via the governed write interface — DOI/PMID verification runs before any KG write, and W3C PROV-JSON provenance is injected automatically.

## Usage

```
/gsd:cite EXP-015 DOI:10.1371/journal.pcbi.1003285
/gsd:cite EXP-015 PMID:25147205
/gsd:cite EXP-015 DOI:10.xxxx type=contradicts
```

## Parameters

| Parameter | Required | Values | Description |
|-----------|----------|--------|-------------|
| `exp_key` | Yes | ArangoDB `_key`, e.g. `overwatch_exp_015` | The experiment's ArangoDB document key. This is the `_key` field, not the display ID (e.g. `overwatch_exp_015` not `EXP-015`). |
| `doi` | One of doi/pmid | DOI string, e.g. `10.1371/journal.pcbi.1003285` | Digital Object Identifier. Verified against CrossRef before the KG write. |
| `pmid` | One of doi/pmid | PubMed ID string, e.g. `25147205` | PubMed identifier. Verified against the PubMed E-utilities API before the KG write. Used only when `doi` is absent. |
| `citation_type` | No | `supports` / `contradicts` / `mentions` | Semantic relationship from the experiment to the publication. Defaults to `supports`. |

## Execution

Run the following Python block and display the result:

```python
import sys
sys.path.insert(0, '.')
from gsigmad.governance.kg.citations import create_citation_edge

result = create_citation_edge(
    exp_key=$ARGUMENTS.exp_key,
    doi=$ARGUMENTS.doi or None,
    pmid=$ARGUMENTS.pmid or None,
    citation_type=$ARGUMENTS.citation_type or "supports",
    agent="claude-sonnet-4-6",
)

if result.get("pass"):
    print(f"Citation edge created: {$ARGUMENTS.exp_key} -> {$ARGUMENTS.doi or 'PMID:' + str($ARGUMENTS.pmid)}")
    print(f"Type: {$ARGUMENTS.citation_type or 'supports'}")
else:
    error = result.get("error", "UNKNOWN_ERROR")
    if "DOI_VERIFICATION" in error or "PMID_VERIFICATION" in error:
        print(f"BLOCKED: {error}")
        print("Fix: verify the DOI/PMID is valid before citing.")
    elif "UNVERIFIED_PENDING" in error:
        print(f"BLOCKED (timeout): {error}")
        print("Fix: retry when CrossRef/PubMed is reachable.")
    elif "CITATION_ERROR" in error:
        print(f"ERROR: {error}")
    else:
        print(f"KG write failed: {error}")
```

## Trust Tier

Citation edges are written as **PROVISIONAL** artifacts:

- `write_document()` automatically injects a W3C PROV-JSON `_provenance` block into every citation edge before the ArangoDB write.
- DOI/PMID verification runs synchronously before any KG write — an unverifiable identifier is a blocking failure; the edge is never written in that case.
- Citation edges use the `rel` edge collection with `rel_type='cites'` (not the `cites` edge collection directly — see DATA_CONTRACTS.md §6: the `cites` edge collection requires `_from` in the `claim` collection, not the `experiment` collection).
- The provenance chain records: agent identity, activity type (`experiment`), entity type (`citation_link`), evidence class (`MEASURED`), and ISO 8601 timestamp.

## Non-Negotiables

- Do NOT fabricate DOI or PMID values. If the reference is not in CrossRef or PubMed, do not cite it — log it as HYPOTHESIS support instead.
- Do NOT retry after a BLOCKED error. The publication is unverified; retrying will produce the same result until the identifier is corrected.
- The `exp_key` parameter is the ArangoDB `_key`, not the EXP display ID. Use `overwatch_exp_015`, not `EXP-015`. Query the KG with `/gsd:find-experiments` to retrieve the correct `_key`.
