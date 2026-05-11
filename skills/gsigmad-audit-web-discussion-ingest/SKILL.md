---
name: gsigmad-audit-web-discussion-ingest
description: "Fail-closed audit of a completed web-discussion import/ingest pair. Verifies custody chain integrity, public-handle-only authorship, IDEATION_AND_TRIAGE_ONLY claim ceiling, deferred review routing, Antigence recommendation completeness, and the explicit not_applicable publication-family gate. Use to audit Hacker News, Reddit, forum, GitHub discussion, Discord export, and similar public web discussion ingest packages before any operator action."
allowed-tools:
  - Read
  - Bash
  - Glob
  - Grep
---

# gsigmad-audit-web-discussion-ingest

Audit the completed output of `gsigmad-import-web-discussion-json` +
`gsigmad-ingest-web-discussion-json` before any downstream operator action.

This skill is the structural parallel of
`gsigmad-audit-import-ingest-completeness` but for the web-discussion source
class. It exists to catch the failure mode where an HN-style ingest exists on
disk but the custody chain, claim ceiling, or Antigence routing is incomplete.

## When to use

Run before:

- routing any web-discussion-derived candidate to an active project's planning
  surface;
- escalating any prompt-injection / security / adoption candidate through
  `gsigmad-governance-bridge`;
- citing any web-discussion content as input to a PROMPT or EXP;
- displaying any web-discussion-derived item on a Watchtower projection
  surface.

The audit **never** writes to a sibling repo and **never** invokes the network.

## Required inputs

Under `<target_repo>/.planning/artifacts/<slug>-<date>/`:

- `RAW-SOURCE-CUSTODY.json`
- `<slug>.raw.{json,html}`
- `CANONICAL-THREAD.json`
- `COMMENT-ATOMS.json`
- `SENTENCE-ATOMS.json`
- `LINK-URL-INVENTORY.json`
- `PROJECT-RELEVANCE-CANDIDATES.json`
- `IMPORT-CUSTODY-MANIFEST.json`
- `INGESTION-GATE-MATRIX.json`
- `DEFERRED-REVIEW-QUEUE.json`
- `COMPLETION-RECEIPT.json`
- `ANTIGENCE-REVIEW-RECOMMENDATIONS.json`
- `CLAIM-CEILING-AUDIT.md`
- `VALIDATION.md`

If any of these is missing, halt with `WEB_DISCUSSION_AUDIT_MISSING_ARTIFACT`.

## Required custody fields (verified, not produced)

```text
source_seed_id              # "web-discussion:<slug>"
source_url
source_sha256
snapshot_path
source_class
comment_count
url_count
claim_ceiling               # MUST equal "IDEATION_AND_TRIAGE_ONLY"
publication_family_gate     # MUST equal "not_applicable"
publication_family_gate_reason  # MUST be non-empty
restricted_data_status      # in {none_observed, operator_review_required}
antigence_status            # in {not_configured, recommended, queued, completed, blocked}
mutation_performed          # MUST be false
live_writeback_performed    # MUST be false
network_called              # MUST be false
row_level_data_extracted    # MUST be false
```

## Required gates (all must PASS or be explicitly BLOCKED with reason)

1. `custody_chain_continuous` — `source_seed_id`, `source_sha256`, `source_url`
   identical across `IMPORT-CUSTODY-MANIFEST.json`,
   `INGESTION-GATE-MATRIX.json`, `COMPLETION-RECEIPT.json`.
2. `source_hash_matches_snapshot` — sha256 of `snapshot_path` equals
   `source_sha256`.
3. `canonical_thread_well_formed` — DAG, unique ids, parent links resolve.
4. `body_text_verbatim` — body slice check against raw snapshot.
5. `public_handles_only` — no PII; no real-name fields; no email; no cross-
   platform handle resolution.
6. `claim_ceiling_enforced` — `IDEATION_AND_TRIAGE_ONLY` across every atom and
   every project-relevance candidate.
7. `publication_family_gate_not_applicable` — explicit not_applicable with
   reason `"web_discussion_source_not_publication_family"`; **never PASS**.
8. `antigence_recommendations_complete` — every sentence atom with
   `needs_antigence_review=true` has a matching row in
   `ANTIGENCE-REVIEW-RECOMMENDATIONS.json`. `antigence_status` is one of
   `{not_configured, recommended, queued, completed, blocked}`. Never PASS
   without a verified receipt.
9. `deferred_review_complete` — every project-relevance candidate with
   `operator_review_required=true` appears in `DEFERRED-REVIEW-QUEUE.json`.
10. `restricted_data_clear` — no row-level peptide / protein / sequence /
    patient / financial / personal data extracted into atoms.
11. `hardrail_flags_pinned` — `mutation_performed=false`,
    `live_writeback_performed=false`, `network_called=false`,
    `row_level_data_extracted=false` across every emitted record.
12. `adapter_status_explicit` — every missing adapter (Antigence, SeedGraph KG
    writer, Overwatch writer, Watchtower projector) reports `not_configured`,
    never PASS.

## Verdicts

- `PASS` — all 12 gates PASS; no BLOCKED rows.
- `PASS_WITH_BLOCKS` — one or more rows BLOCKED for explicit, recorded reasons
  (e.g. row_level data observed and operator review queued; Antigence
  recommended but adapter not configured). Each block carries a `reason` and an
  optional `operator_marker`.
- `FAIL` — any required artifact missing, custody chain broken, paraphrase
  detected, claim ceiling violated, publication-family gate set to PASS, PII
  observed, or hard-rail flag claimed true.

## Hard halts

Halt with `WEB_DISCUSSION_AUDIT_COMPLETENESS_FAIL` if:

- the source hash mismatch is detected;
- a comment body in `CANONICAL-THREAD.json` is not a verbatim slice of the raw
  snapshot;
- `claim_ceiling` is anything other than `IDEATION_AND_TRIAGE_ONLY` without an
  explicit operator-attested deviation receipt;
- `publication_family_gate` is set to PASS;
- any record claims `mutation_performed=true` or
  `live_writeback_performed=true`;
- any Antigence row claims `antigence_status=completed` without a verifiable
  review receipt path;
- a missing adapter is reported as PASS;
- author identity enrichment beyond public handles is detected;
- network was called during ingest (`network_called=true` in
  `COMPLETION-RECEIPT.json`).

## Validation

The audit is itself read-only. It does not modify the artifact directory.
It produces, into the same artifact directory:

```text
AUDIT-REPORT.json             # gate-by-gate verdict + counts
AUDIT-SUMMARY.md              # human-readable verdict + next-action
```

## Report back

- verdict: PASS / PASS_WITH_BLOCKS / FAIL
- artifact directory
- gate counts by status
- antigence recommendation count + status distribution
- deferred review queue length
- blocking codes (if any)
- next safe action (always operator-driven for web-discussion-derived
  candidates)
- explicit boundary statement: `mutation_performed=false`,
  `live_writeback_performed=false`, `network_called=false`,
  `row_level_data_extracted=false`.
