---
name: gsigmad-redteam-research-remediate
description: "Create a three-lane red-team, research, and remediation prompt package for a scientific artifact, publication ingest, dataset, claim, or AI output."
allowed-tools:
  - Read
  - Write
  - Bash
  - Glob
  - Grep
---

# gsigmad-redteam-research-remediate

Create a compact three-lane review package:

1. red-team prompt
2. research prompt
3. remediation prompt

Use this when the operator says "red team", "research and remediate", "what am
I missing?", "audit then fix", or asks for adversarial review before ingest,
claim promotion, publication use, writeback, or public release.

## Output Directory

Write into the owning repo:

```text
<target_repo>/.planning/quick/<YYMMDD>-<slug>-redteam-research-remediate/
```

Required files:

```text
PLAN.md
REDTEAM-PROMPT.md
RESEARCH-PROMPT.md
REMEDIATE-PROMPT.md
SUMMARY.md
```

## PLAN.md Must Include

- target artifact / ask
- owning repo
- evidence class
- claim ceiling
- restricted-data risk
- destination/writeback risk
- required skill chain
- expected outputs
- stop boundaries

## REDTEAM-PROMPT.md Must Ask

- What can fail?
- What is unsupported?
- What claim wording overreaches?
- What data should not be extracted?
- What missing adapters are being laundered as PASS?
- What Merkle / custody proof is absent?
- What would make this unsafe to ingest, publish, or write back?

## RESEARCH-PROMPT.md Must Ask

- What official/local source artifacts should be read?
- What schemas or contracts apply?
- What prior imports/EXP/PROMPT records overlap?
- What identifiers need reconciliation?
- What source hashes, Merkle roots, replay fingerprints, or receipts already
  exist?
- What is the minimum implementation path?

## REMEDIATE-PROMPT.md Must Ask

- Apply only the fixes supported by the red-team and research findings.
- Preserve row-level restrictions.
- Emit canonical JSON first for publication/source imports.
- Require SeedGraph `publication.atomic.json` before destination routing.
- Create validation and blocked-record reports.
- Do not perform live writeback unless explicitly approved.

## Hard Rails

- No live Overwatch / ProTHub / ProAtlas / SeedGraph KG / ArangoDB / Neo4j
  writeback by default.
- No network call by default.
- No row-level restricted extraction without explicit approval.
- Missing adapters are `not_configured`, never PASS.
- Red-team must run before remediation.
- Research findings must cite local files or mark claims as unresolved.

## Final Report

Report:

- package path
- red-team prompt path
- research prompt path
- remediate prompt path
- fastest safe next step
- approvals required before execution
