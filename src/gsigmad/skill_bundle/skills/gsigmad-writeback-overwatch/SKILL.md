---
name: gsigmad-writeback-overwatch
description: "Perform operator-approved Overwatch writeback from a verified publication destination queue only after SeedGraph Merkle proof and chain-of-custody gates pass."
allowed-tools:
  - Read
  - Bash
  - Glob
  - Grep
---

# gsigmad-writeback-overwatch

Write to Overwatch only from an approved deferred queue whose records already
passed canonical JSON import, SeedGraph Merkle ingest, and destination routing.

This skill is blocked by default. It requires explicit operator approval in the
current session.

## Preconditions

All must be present:

- canonical JSON bundle
- `publication.atomic.json` proof for every package being written
- `cryptographic_gate: PASS`
- `verification.status: verified`
- destination queue with Overwatch jobs
- explicit operator approval naming the queue and destination
- restricted-data sweep result

## Required Receipt Fields

Every writeback receipt must include:

```text
writeback_receipt_id
destination=overwatch
payload_file
payload_count
source_seed_id
source_sha256
proof_id
source_member_root
derived_asset_root
receipt_root
replay_fingerprint
operator_approval
mutation_performed
live_writeback_performed
created_at
signature_or_audit_id
```

## Hard Halts

Halt with `OVERWATCH_WRITEBACK_CUSTODY_VIOLATION` if:

- operator approval is absent or ambiguous;
- Merkle proof is missing or blocked;
- replay fingerprint is missing;
- any row-level restricted payload is included;
- destination queue was modified after validation without a new hash/receipt;
- writeback would bypass the Overwatch governed adapter/MCP boundary.

## Report Back

- approval string used
- Overwatch jobs attempted
- Overwatch jobs written
- receipt paths
- skipped/blocked jobs and reasons
- post-writeback validation status
