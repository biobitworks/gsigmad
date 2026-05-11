---
name: gsigmad-import-publications-json
description: "Normalize publication-like source packages into canonical local JSON before any SeedGraph ingest or database writeback. Use for literature import, publication import, batch reimport, citation/source-asset import, and any request that says import first to JSON."
allowed-tools:
  - Read
  - Bash
  - Glob
  - Grep
---

# gsigmad-import-publications-json

Import publication-like sources into canonical local JSON handoff files. This
skill is the first gate in the publication custody chain. It does not ingest
into SeedGraph and it does not write to Overwatch, ProTHub, ProAtlas/protatlas,
ArangoDB, Neo4j, or any live KG.

## Required Order

1. Discover source packages and existing local artifacts.
2. Normalize them into local JSON arrays.
3. Record source identity, file hashes, and blocked/restricted status.
4. Emit a destination-independent custody manifest.
5. Stop before SeedGraph ingest or live writeback.

## Required JSON Outputs

At minimum, produce or verify:

- `PUBLICATION-BATCH-INVENTORY.json`
- `OVERWATCH-PUBLICATION-UPSERT.json`
- `OVERWATCH-SOURCE-ASSET-UPSERT.json`
- `OVERWATCH-CITATION-UPSERT.json`
- `OVERWATCH-FIGURE-TABLE-UPSERT.json`
- `PROTEIN-ENTITY-DESTINATION.json`
- `BLOCKED-ROW-LEVEL-PACKAGES.json`
- `IMPORT-CUSTODY-MANIFEST.json`
- `VALIDATION.md`

## Minimum Custody Fields

Every package record must include:

```text
source_seed_id
source_sha256
title_or_name
doi
pmid
pmcid
nihms_id
repository_id
source_package
source_artifacts
claim_ceiling
evidence_class
needs_operator_review
mutation_performed=false
live_writeback_performed=false
```

If a SeedGraph atomic proof already exists, also carry:

```text
proof_id
manifest_hash
source_member_root
derived_asset_root
receipt_root
replay_fingerprint
verification_status
signature.digest
signature.signed_by
source_atomic_proof_path
```

If no atomic proof exists, set `cryptographic_gate: "not_available"` and
`next_gate: "gsigmad-ingest-publications-json"`.

## Hard Halts

Halt with `IMPORT_JSON_CUSTODY_VIOLATION` if:

- source identity is missing and cannot be represented as
  `needs_operator_review=true`;
- source hash is missing for a local file that is safe to hash;
- row-level peptide/protein/sequence/quantitative/patient data would be copied;
- any record claims live writeback happened;
- a missing adapter is reported as PASS instead of `not_configured`.

## Report Back

- packages discovered
- publication/source/citation/figure-table/entity records emitted
- blocked row-level packages
- JSON output directory
- packages with existing SeedGraph atomic proof
- packages requiring `gsigmad-ingest-publications-json`
- validation commands run
