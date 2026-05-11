---
name: gsigmad-find-experiments
description: "Search and filter EXP records across all projects via ArangoDB. Use when querying experiment history, finding related work, or checking for conflicts. Returns a markdown table with provenance signatures."
allowed-tools: Read, Bash
---

# Find Experiments ($kg-query + $cross-project-search)

Cross-project experiment search — queries the Overwatch KG via AQL with optional filter predicates. Returns a markdown table of EXP records with provenance chains.

## Usage

```
/gsd:find-experiments
/gsd:find-experiments project=overwatch
/gsd:find-experiments classification=CONFIRMATORY status=completed
/gsd:find-experiments protein=TP53
/gsd:find-experiments project=cellico date_from=2026-01-01 date_to=2026-12-31
/gsd:find-experiments classification=EXPLORATORY protein=BRCA1
```

## Filter Parameters

| Parameter | Values | Description |
|-----------|--------|-------------|
| `project` | any project name | Restrict to a single project (e.g. `cellico`, `overwatch`). Omit for all projects. |
| `classification` | `CONFIRMATORY` / `EXPLORATORY` / `REPLICATION` | Filter by experiment classification. |
| `status` | `running` / `completed` / `failed` | Filter by experiment status. |
| `date_from` | ISO 8601 date (e.g. `2026-01-01`) | Include only experiments with start_date >= date_from. |
| `date_to` | ISO 8601 date (e.g. `2026-12-31`) | Include only experiments with start_date <= date_to. |
| `protein` | protein name or gene symbol | Filter via involves edge traversal (e.g. `TP53`, `BRCA1`). |

## Execution

Run the following Python block and display the result:

```python
import sys
sys.path.insert(0, '.')
from gsigmad.governance.kg.query import find_experiments, format_results_table

results = find_experiments(
    project=$ARGUMENTS.project or None,
    classification=$ARGUMENTS.classification or None,
    status=$ARGUMENTS.status or None,
    date_from=$ARGUMENTS.date_from or None,
    date_to=$ARGUMENTS.date_to or None,
    protein=$ARGUMENTS.protein or None,
)

if isinstance(results, dict) and "error" in results:
    if "KG_UNAVAILABLE" in str(results.get("error", "")):
        print("KG unavailable — ensure ArangoDB is running.")
    else:
        print(f"ERROR: {results['error']}")
elif not results:
    print("No experiments found matching the specified filters.")
else:
    print(format_results_table(results))
```

## Output Format

The command returns a GitHub-flavored markdown table:

```
| EXP | Project | Classification | Status | Last Run | Provenance Sig |
| --- | --- | --- | --- | --- | --- |
| cellico:EXP-042 | cellico | CONFIRMATORY | completed | run_20260315_001 | SIG-20260315T... |
```

Columns:
- **EXP**: Experiment ID prefixed with project namespace (e.g. `cellico:EXP-042`) to prevent cross-project collision
- **Project**: Source project name
- **Classification**: CONFIRMATORY / EXPLORATORY / REPLICATION
- **Status**: Current experiment status
- **Last Run**: Most recent run_id for this experiment
- **Provenance Sig**: SIG-ID from the W3C PROV-JSON _provenance block

## Notes

- If `KG_UNAVAILABLE` appears, ArangoDB is offline. The query cannot fall back to local scan.
- Results are capped at 100 per query (ArangoDB hard limit).
- The `protein` filter uses the `involves` edge traversal — it does NOT match experiment document fields directly.
- exp_id values include project prefix (e.g. `cellico:EXP-042`) per DATA_CONTRACTS.md §6 namespace rules.

## Non-Negotiables

- Do NOT fabricate experiment records if KG_UNAVAILABLE; display the error message as-is.
- Results are read-only — this command does not write to the KG.
- Provenance signatures in the table are from ArangoDB — do not modify or truncate them.
