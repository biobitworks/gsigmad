---
name: gsigmad-drift-scan
description: "Scan all 12 project adapters for CANON classification changes. Use when running scheduled drift detection or investigating a suspected CANON change. Loads adapters/*.md automatically and writes a drift report to .agent/drift_reports/."
disable-model-invocation: true
allowed-tools: [Read, Bash]
---

# Drift Scan ($canon-drift-detection)

Scan all 12 registered projects for CANON classification changes. Reads adapter metadata automatically from `adapters/*.md` — no manual project list needed. Writes a timestamped JSON drift report when classification changes are detected.

## Usage

```
/gsd:drift-scan
```

No parameters. All configuration is sourced from `adapters/*.md` automatically (per D-08, WIRE-03).

## Execution

Run the following Python block and display the result:

```python
import sys
sys.path.insert(0, '.')
from gsigmad.governance.compiler.adapter_loader import load_project_registry
from gsigmad.governance.compiler.drift_scanner import scan_all_projects

# Load all 12 project adapters from adapters/*.md (per D-08, WIRE-03)
project_registry = load_project_registry('.')

result = scan_all_projects(gsd_root='.', project_registry=project_registry)

print(f"Scan timestamp: {result['scan_timestamp']}")
print(f"Projects scanned: {result['projects_scanned']}")

if result['drift_detected']:
    print(f"\nDRIFT DETECTED -- {len(result['drift_events'])} event(s):")
    for event in result['drift_events']:
        print(f"  {event['project']}: {event['invariant_changed']} changed")
        print(f"    {event['old_classification']} -> {event['new_classification']}")
    print(f"\nFull report: {result['report_path']}")
else:
    print("No drift detected -- all CANON classifications stable.")
```

## Output

- **Summary to stdout**: scan timestamp, projects scanned count, drift status.
- **Full JSON report**: written to `.agent/drift_reports/DRIFT-{timestamp}.json` only when drift is detected.
- **Last scan marker**: `.agent/last_drift_scan.txt` is always updated after every run (enables 24-hour cron trigger and threshold checks in `drift_check.py`).

## Drift Report Schema

When drift is detected, the full report at `.agent/drift_reports/DRIFT-{timestamp}.json` follows this schema:

```json
{
  "scan_timestamp": "2026-04-01T14:32:00Z",
  "projects_scanned": 8,
  "drift_detected": true,
  "drift_events": [
    {
      "project": "cellico",
      "invariant_changed": "classification",
      "old_classification": "EXPLORATORY",
      "new_classification": "CONFIRMATORY",
      "detected_timestamp": "2026-04-01T14:32:00Z"
    }
  ],
  "report_path": ".agent/drift_reports/DRIFT-20260401T143200Z.json"
}
```

Fields in each drift event:
- `project`: project name from the adapter registry
- `invariant_changed`: which CANON invariant classification changed
- `old_classification`: classification recorded in the previous snapshot
- `new_classification`: classification found in the current CANON.md scan
- `detected_timestamp`: ISO 8601 UTC timestamp when the drift was detected

## Non-Negotiables

- Do NOT manually construct `project_registry`; always call `load_project_registry()` so that adapter file changes propagate automatically without code edits.
- Projects with `has_canon=false` are silently skipped by `scan_all_projects()` — this is correct behaviour, not an error. Conductor, Antigence-Bittensor, and other projects without CANON.md cannot experience classification drift.
- Do NOT suppress or modify drift events; display them verbatim from the result dict. The raw output is the audit record.
- This command is read-only except for writing the DRIFT JSON report and updating `last_drift_scan.txt`. It does not modify any CANON.md, experiment record, or KG document.
