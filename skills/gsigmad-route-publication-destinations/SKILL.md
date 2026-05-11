---
name: gsigmad-route-publication-destinations
description: "Route verified publication JSON and SeedGraph Merkle proofs to deferred Overwatch, ProTHub, ProAtlas/protatlas, SeedGraph KG, triage SQLite, and research_hub writeback queues."
allowed-tools:
  - Read
  - Bash
  - Glob
  - Grep
---

# gsigmad-route-publication-destinations

Create a destination matrix and deferred writeback queue from canonical JSON
and verified SeedGraph Merkle custody proofs. This skill routes records; it
does not perform live writeback.

## Inputs

- canonical publication JSON bundle
- SeedGraph `publication.atomic.json` proof or explicit
  `cryptographic_gate: not_available`
- import/ingest validation reports
- blocked row-level package list

## Destination Status Values

Use only:

```text
json_prepared
blocked_pending_operator_approval
blocked_missing_merkle_proof
blocked_restricted_row_level
not_configured
missing
deferred_pending_operator_approval
```

Missing adapters must be `not_configured`, never PASS.

## Required Matrix Fields

For every package/destination pair:

```text
package_id
destination
payload_file
payload_count
source_seed_id
source_sha256
proof_id
source_member_root
derived_asset_root
receipt_root
replay_fingerprint
cryptographic_gate
destination_status
blocked_reason
approval_required
mutation_performed=false
live_writeback_performed=false
```

## Destinations

- `overwatch`
- `prothub`
- `proatlas`
- `seedgraph_kg`
- `triage_sqlite`
- `research_hub`

## Hard Halts

Halt with `PUBLICATION_DESTINATION_ROUTING_VIOLATION` if:

- a routable package lacks JSON payload;
- a routable package lacks verified Merkle custody proof;
- row-level restricted data is routed to a public or live destination;
- any queue item claims mutation happened;
- `not_configured` is hidden as PASS.

## Report Back

- destination matrix path
- deferred writeback queue path
- job counts by destination
- packages blocked for missing Merkle proof
- packages blocked for row-level restrictions
- adapters marked `not_configured`
