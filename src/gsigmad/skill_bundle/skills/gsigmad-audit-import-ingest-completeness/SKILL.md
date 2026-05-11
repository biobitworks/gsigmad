---
name: gsigmad-audit-import-ingest-completeness
description: "Fail-closed audit for publication import/ingest completeness. Verifies canonical JSON, SeedGraph Merkle proof, chain-of-custody receipts, destination queues, restricted-data gates, and adapter statuses."
allowed-tools:
  - Read
  - Bash
  - Glob
  - Grep
---

# gsigmad-audit-import-ingest-completeness

Audit publication import/ingest work before any claim promotion or database
writeback. This skill exists to catch the exact failure mode where local import
artifacts exist but Merkle-backed chain-of-custody and destination receipts do
not.

## Audit Inputs

- canonical local JSON bundle
- `IMPORT-CUSTODY-MANIFEST.json`
- SeedGraph `publication.atomic.json` proofs
- import/ingest validation reports
- destination matrix
- deferred writeback queue
- blocked row-level package report
- restricted-token sweep
- adapter-status report

## Required Gates

All gates must be PASS or explicitly BLOCKED with reason:

1. source identity
2. source hash
3. canonical JSON parse
4. duplicate identity reconciliation
5. citation/bibliography identity
6. figure/table boundary
7. restricted row-level data
8. claim ceiling
9. SeedGraph Merkle proof
10. receipt / ledger chain
11. signature / keyring status
12. destination matrix
13. deferred writeback queue
14. adapter status

## Required Merkle / Custody Fields

```text
source_seed_id
source_sha256
manifest_hash
source_member_root
derived_asset_root
receipt_root
replay_fingerprint
verification_status
blocking_codes
warning_codes
signature.algorithm
signature.digest
signature.signed_by
signature.key_id
parent_hash
receipt_hash
chain_index
entry_hash
prev_hash
```

## Verdicts

- `PASS`: all required packages have verified JSON, Merkle proof, receipt
  chain, destination queue, and no restricted-data violation.
- `PASS_WITH_BLOCKS`: some packages are intentionally blocked or
  `not_configured`, and the blocks are explicit.
- `FAIL`: any expected package is missing JSON, proof, custody chain, adapter
  status, or restricted-data gating.

## Hard Halts

Halt with `IMPORT_INGEST_COMPLETENESS_FAIL` if:

- a package is silently omitted;
- a package reaches destination routing without Merkle proof;
- a writeback queue lacks `mutation_performed=false` before approval;
- restricted row-level data is embedded;
- `not_configured` is reported as PASS;
- a broken receipt chain is ignored.

## Report Back

- verdict
- package counts by gate
- packages missing JSON
- packages missing Merkle proof
- packages with broken receipt chain
- packages blocked for restricted data
- destination jobs by status
- exact next action before live writeback
