---
name: gsigmad-ingest-publications-json
description: "Validate canonical publication JSON through SeedGraph's deterministic ingest path and require Merkle-backed publication.atomic.json chain-of-custody proof before promotion or writeback."
allowed-tools:
  - Read
  - Bash
  - Glob
  - Grep
---

# gsigmad-ingest-publications-json

Ingest canonical publication JSON into SeedGraph's deterministic local ingest
and proof surfaces. This skill owns the Merkle / chain-of-custody gate between
JSON import and any downstream placement.

## SeedGraph Sources To Use

Read these when working in SeedGraph:

- `src/seedgraph/publication_family/atomic.py`
- `src/seedgraph/merkle/tree.py`
- `src/seedgraph/merkle/atoms.py`
- `src/seedgraph/evidence/verification.py`
- `src/seedgraph/ledger/ledger.py`
- `docs/WORKFLOWS.md`
- `docs/OLLARMA_BRIDGE_CONSUMER.md`

## Required Proof Output

For each package eligible for ingest, produce or verify a
`publication.atomic.json` proof. Minimum fields:

```text
proof_id
proof_version
family_id
source_seed_id
source_sha256
manifest_hash
member_leaf_hashes
derived_leaf_hashes
source_member_root
derived_asset_root
receipt_root
replay_fingerprint
verification.status
verification.blocking_codes
verification.warning_codes
signature.algorithm
signature.digest
signature.signed_by
signature.key_id
```

## Required Merkle Member Proof Fields

```text
member_index
file_name
asset_kind
role
sha256
media_type
leaf_hash
proof_nodes
```

## Required Derived Asset Proof Fields

```text
asset_id
asset_class
origin
file_backed
source_seed_id
member_sha256
derived_seed_id
activation_status
review_status
leaf_hash
proof_nodes
```

## Required Receipt / Ledger Chain Fields

```text
parent_hash
evidence_id
decision_id_or_family_id
chain_index
created_at_or_generated_at
receipt_hash
entry_hash
prev_hash
signature
```

## Hard Halts

Halt with `SEEDGRAPH_MERKLE_CUSTODY_VIOLATION` if:

- `source_seed_id` or `source_sha256` is missing;
- `publication.atomic.json` is missing for a package being promoted past
  local JSON;
- `source_member_root`, `derived_asset_root`, `receipt_root`, or
  `replay_fingerprint` is missing;
- member or derived asset proof paths fail verification;
- receipt parent links or chain indexes are broken;
- verification status is `blocked`;
- signature is invalid, missing without explicit dev-key warning, or silently
  treated as production trust;
- row-level restricted data is extracted without operator approval.

## Output

Emit an ingest validation report with:

- package count
- proof count
- verified proof IDs
- blocked proof IDs and blocking codes
- signature status
- replay fingerprints
- receipt/ledger chain status
- `mutation_performed=false`
- `live_writeback_performed=false`

No live writeback is permitted in this skill.
