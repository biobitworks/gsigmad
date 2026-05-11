---
name: gsigmad-ingest-web-discussion-json
description: "Validate canonical web-discussion JSON into the SeedGraph / governance ingest path with a deterministic 11-gate matrix, deferred review queue, and completion receipt. The publication-family Merkle gate is not_applicable for web discussion seeds and must be recorded as such. Use after gsigmad-import-web-discussion-json and before gsigmad-audit-web-discussion-ingest."
allowed-tools:
  - Read
  - Write
  - Bash
  - Glob
  - Grep
---

# gsigmad-ingest-web-discussion-json

Validate canonical web-discussion JSON produced by `gsigmad-import-web-discussion-json`
through a deterministic ingest path. This skill owns the **structural ingest gate**
between custody manifest and any downstream routing or claim audit.

It is the structural parallel of `gsigmad-ingest-publications-json` but **without**
the publication-family atomic-proof requirement. The Merkle / `publication.atomic.json`
gate is `not_applicable` here, recorded with an explicit reason in the completion
receipt. Web-discussion comments are never publication evidence; routing them
through the Merkle gate would mis-apply the contract.

## When to use

Run this skill **after** `gsigmad-import-web-discussion-json` has produced the
custody manifest and canonical thread JSON. Run it **before** any
`gsigmad-route-publication-destinations` or `gsigmad-audit-claims` step.

This skill never:

- fetches new data over the network;
- writes to Overwatch / SeedGraph KG / ProTHub / ProAtlas / ArangoDB / Neo4j;
- promotes a comment to canonical evidence;
- de-anonymizes any author handle.

## Required inputs

Under `<target_repo>/.planning/artifacts/<slug>-<date>/`:

- `RAW-SOURCE-CUSTODY.json` — produced by import skill
- `<slug>.raw.{json,html}` — verbatim source snapshot
- `CANONICAL-THREAD.json`
- `COMMENT-ATOMS.json`
- `SENTENCE-ATOMS.json`
- `LINK-URL-INVENTORY.json`
- `PROJECT-RELEVANCE-CANDIDATES.json`
- `IMPORT-CUSTODY-MANIFEST.json`
- (optional) prior `DEFERRED-REVIEW-QUEUE.json` for append-on-rerun

## Required outputs

Under the same artifact directory:

```text
INGESTION-GATE-MATRIX.json    # 11-gate audit, one record per gate
DEFERRED-REVIEW-QUEUE.json    # one record per item flagged for operator review
COMPLETION-RECEIPT.json       # status, gate counts, hard-rail flags
CLAIM-CEILING-AUDIT.md        # written if not already present from import
VALIDATION.md                 # boundary statement, validator counts
ANTIGENCE-REVIEW-RECOMMENDATIONS.json  # one record per Antigence-flagged item
```

## Custody fields carried forward

Every emitted record reuses the `source_seed_id`, `source_sha256`, `source_url`,
`source_class`, and `snapshot_path` from `IMPORT-CUSTODY-MANIFEST.json`. The
ingest path **does not** mutate these fields; mismatch is a hard halt.

## The 11 ingest gates

`INGESTION-GATE-MATRIX.json` records one row per gate. Each row carries
`{gate_id, status ∈ {PASS, BLOCKED, NOT_CONFIGURED, NOT_APPLICABLE, SKIPPED}, reason, evidence_refs[]}`.

| # | Gate | What it checks |
|---|---|---|
| 1 | `source_identity` | `source_url` is canonical and `source_seed_id` is well-formed (`web-discussion:<slug>`). |
| 2 | `source_hash` | `source_sha256` matches the sha256 of `snapshot_path`. |
| 3 | `canonical_thread_parse` | `CANONICAL-THREAD.json` parses; comment ids unique; tree edges form a DAG. |
| 4 | `body_verbatim` | Every `comment.body_text` either appears as a slice of the raw snapshot or carries `body_text_missing=true`. No paraphrase. |
| 5 | `public_handles_only` | No author field outside the documented public-handle whitelist. No emails, no real names, no cross-platform identity. |
| 6 | `claim_ceiling` | `IDEATION_AND_TRIAGE_ONLY` enforced across every atom. No comment marked as "evidence" / "fact" / "validated". |
| 7 | `publication_family_gate` | Status = `NOT_APPLICABLE` with reason `"web_discussion_source_not_publication_family"`. Must not be PASS. Must not be silently absent. |
| 8 | `restricted_data` | `restricted_data_status ∈ {none_observed, operator_review_required}`. No row-level peptide / patient / sequence / financial data extracted. If observed, BLOCKED. |
| 9 | `antigence_recommendation` | For every sentence atom with `needs_antigence_review=true`, an `ANTIGENCE-REVIEW-RECOMMENDATIONS.json` record exists. `antigence_status ∈ {not_configured, recommended, queued, completed, blocked}`. Never PASS without a verified review receipt. |
| 10 | `deferred_writeback_receipt` | Every item routed to deferred review has a `DEFERRED-REVIEW-QUEUE.json` row with `mutation_performed=false`, `live_writeback_performed=false`. |
| 11 | `completion_receipt` | `COMPLETION-RECEIPT.json` exists, validates, and pins the hard-rail flags. |

## Required completion-receipt shape

`COMPLETION-RECEIPT.json`:

```json
{
  "receipt_version": "1.0.0",
  "source_seed_id": "web-discussion:<slug>",
  "source_sha256": "...",
  "status": "pass" | "missing" | "blocked" | "not_applicable",
  "gate_counts": {
    "pass": <int>,
    "blocked": <int>,
    "not_configured": <int>,
    "not_applicable": <int>,
    "skipped": <int>
  },
  "blocking_codes": ["..."],
  "warning_codes": ["..."],
  "claim_ceiling": "IDEATION_AND_TRIAGE_ONLY",
  "publication_family_gate": "not_applicable",
  "publication_family_gate_reason": "web_discussion_source_not_publication_family",
  "antigence_status": "not_configured" | "recommended" | "queued" | "completed" | "blocked",
  "antigence_recommendation_count": <int>,
  "deferred_review_count": <int>,
  "invocation": "gsigmad-ingest-web-discussion-json",
  "mutation_performed": false,
  "live_writeback_performed": false,
  "network_called": false,
  "row_level_data_extracted": false,
  "created_at_utc": "..."
}
```

Hard rule: `mutation_performed` and `live_writeback_performed` are pinned to
`false` at the receipt level. Setting either to `true` is a contract violation
and must raise `WEB_DISCUSSION_INGEST_HARDRAIL_VIOLATION`.

## Antigence routing

For every sentence atom with `provisional_claim_class` in
`{security_warning, adoption_recommendation}` OR with
`needs_antigence_review=true`, this skill emits one
`ANTIGENCE-REVIEW-RECOMMENDATIONS.json` row:

```text
recommendation_id
sentence_atom_id
comment_id
public_handle
sentence_text
risk_category        # "prompt_injection" | "security_warning" |
                     # "tooling_adoption" | "policy_recommendation" | "other"
antigence_status     # default "not_configured" — never "completed" without
                     # a verified Antigence review receipt
review_payload_path  # path to per-recommendation review JSON if produced
blocking_codes       # array; non-empty when an adapter is missing
```

The skill **does not** invoke Antigence. It emits the recommendation and routes
through `gsigmad-governance-bridge` for any actual review.

## Hard halts

Halt with `WEB_DISCUSSION_INGEST_HARDRAIL_VIOLATION` if:

- any required input file from the import step is missing;
- `source_sha256` mismatch between custody manifest and snapshot;
- a comment body in `CANONICAL-THREAD.json` does not appear in the raw snapshot
  (paraphrase rejected);
- an author field outside the public-handle whitelist is present;
- `publication_family_gate` is set to PASS for a web-discussion seed;
- row-level restricted data is detected;
- any record claims `live_writeback_performed=true`;
- any Antigence recommendation claims `antigence_status=completed` without a
  verified receipt path;
- a missing adapter is reported as PASS instead of `not_configured`.

## Validation

1. All 11 gate rows present in `INGESTION-GATE-MATRIX.json`.
2. `COMPLETION-RECEIPT.json` parses; hard-rail flags pinned false.
3. Every `recommendation_id` in `ANTIGENCE-REVIEW-RECOMMENDATIONS.json`
   references a real `sentence_atom_id`.
4. `DEFERRED-REVIEW-QUEUE.json` carries every project-relevance candidate
   with `operator_review_required=true`.
5. No paraphrase / no PII / no live writeback / no network.

## Report back

- artifact directory path
- gate counts by status
- antigence recommendation count
- deferred review queue length
- completion receipt status
- next skill: `gsigmad-audit-web-discussion-ingest`
- explicit boundary statement
