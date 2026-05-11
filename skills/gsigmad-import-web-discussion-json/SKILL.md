---
name: gsigmad-import-web-discussion-json
description: "Normalize public web discussion sources (Hacker News threads, Reddit threads, forum threads, GitHub discussions/issues, Discord exports, blog comment threads) into canonical local JSON before any SeedGraph ingest or downstream routing. Use for HN threads, Reddit threads, forum threads, GitHub discussions, Discord exports, and similar public comment threads."
allowed-tools:
  - Read
  - Write
  - Bash
  - Glob
  - Grep
---

# gsigmad-import-web-discussion-json

Import a public web discussion source into canonical local JSON handoff files.

This skill is the first gate in the **web-discussion source-seed custody chain**.
It is the structural parallel of `gsigmad-import-publications-json` but for a
different source class — one that has no DOI / PMID / atomic-publication family
and must default to a stricter claim ceiling.

It does not ingest into SeedGraph, and it does not write to Overwatch, ProTHub,
ProAtlas/protatlas, ArangoDB, Neo4j, or any live KG.

## When to use

Trigger when the operator says any of:

- "HN thread" / "Hacker News" / `news.ycombinator.com/item?id=...`
- "Reddit thread" / `reddit.com/r/.../comments/...`
- "forum thread" / "Discourse" / phpBB / vBulletin / similar
- "GitHub discussion" / "GitHub issue" / "GitHub thread"
- "Discord export" / "Slack export" / "Matrix export"
- "blog comment thread" / "Disqus export"
- "public comment thread" / "web discussion"

Do **not** route to this skill for:

- preprints, journal articles, NIHMS manuscripts — use `gsigmad-import-publications-json`
- datasets, supplements, row-level data — use `gsigmad-data-contract`
- private chat exports with non-public participants — operator decision; treat
  as restricted and halt before invoking this skill.

## Required order

1. Confirm the raw source is **already on disk** (this skill does not fetch).
2. Discover raw source files and prior artifacts in the target directory.
3. Compute source sha256 over the raw snapshot exactly as received.
4. Normalize the thread into canonical JSON shapes.
5. Record public handles only — no identity enrichment.
6. Emit a destination-independent custody manifest.
7. Stop before ingest. Stop before any live writeback.

## Required inputs

| Input | Purpose |
|---|---|
| `<artifact_dir>/<slug>.raw.json` or `<slug>.raw.html` | The verbatim source snapshot. Source-of-truth for hashing. |
| Operator-supplied `source_url` | Canonical URL (e.g. `https://news.ycombinator.com/item?id=48085993`). |
| Operator-supplied `slug` | Short kebab-case identifier (e.g. `hn-48085993`). |
| `target_repo` | Repo whose `.planning/artifacts/<slug>-<date>/` will receive the JSON outputs (typically SeedGraph). |

## Required outputs

Under `<target_repo>/.planning/artifacts/<slug>-<date>/`:

```text
RAW-SOURCE-CUSTODY.json           # url, source_sha256, snapshot_path, fetched_at, etag, http_status
<slug>.raw.{json,html}            # raw source snapshot (verbatim — do not redact)
CANONICAL-THREAD.json             # normalized thread tree (root_item + comment tree)
COMMENT-ATOMS.json                # one record per comment; parent/child links by id
SENTENCE-ATOMS.json               # sentence-grain decomposition with claim-class hints
LINK-URL-INVENTORY.json           # every outbound link mentioned anywhere in the thread
PROJECT-RELEVANCE-CANDIDATES.json # candidate routings to active projects; never auto-promote
CLAIM-CEILING-AUDIT.md            # confirms IDEATION_AND_TRIAGE_ONLY ceiling
IMPORT-CUSTODY-MANIFEST.json      # destination-independent custody record
VALIDATION.md                     # counts, hard-rail status, next-skill pointer
```

The receipt and audit JSONs (`INGESTION-GATE-MATRIX.json`,
`DEFERRED-REVIEW-QUEUE.json`, `COMPLETION-RECEIPT.json`) are produced by the
*ingest* and *audit* skills, not by this one.

## Custody fields (per source)

Every record in `IMPORT-CUSTODY-MANIFEST.json` must include:

```text
source_seed_id          # stable id: "web-discussion:<slug>"
source_url              # canonical URL
source_sha256           # sha256 over the raw snapshot bytes
snapshot_path           # relative path inside artifact_dir
snapshot_format         # "html" | "json" | "ndjson"
source_class            # "hn" | "reddit" | "forum" | "github_discussion" | "github_issue" |
                        # "discord_export" | "slack_export" | "matrix_export" |
                        # "blog_comments" | "other_public_discussion"
fetched_at_utc          # operator-supplied; ISO-8601
http_status             # if known
etag                    # if known
content_length_bytes
title                   # root post title if applicable
root_author_handle      # PUBLIC handle only
root_posted_at_utc
comment_count
url_count
claim_ceiling           # MUST default to "IDEATION_AND_TRIAGE_ONLY"
publication_family_gate # MUST be "not_applicable" with explicit reason
restricted_data_status  # MUST be "none_observed" or "operator_review_required"
needs_operator_review   # boolean
mutation_performed=false
live_writeback_performed=false
```

## Canonical thread JSON shape

`CANONICAL-THREAD.json`:

```json
{
  "source_seed_id": "web-discussion:<slug>",
  "source_class": "hn",
  "root_item": {
    "id": "<id>",
    "kind": "story" | "post" | "issue" | "discussion",
    "title": "...",
    "author_handle": "...",
    "posted_at_utc": "...",
    "url": "...",
    "body_text": "..."
  },
  "comments": [
    {
      "id": "<comment_id>",
      "parent_id": "<parent_id_or_root_id>",
      "depth": 0,
      "author_handle": "...",
      "posted_at_utc": "...",
      "body_text": "...",
      "child_ids": ["..."]
    }
  ],
  "edges": [
    {"parent": "<id>", "child": "<id>"}
  ],
  "counts": {
    "comments": <int>,
    "max_depth": <int>,
    "unique_handles": <int>
  }
}
```

## Comment-atom and sentence-atom shapes

`COMMENT-ATOMS.json` — one record per comment with the canonical id, parent
chain, author handle (public), posted_at, raw body, depth, and the source_seed_id.

`SENTENCE-ATOMS.json` — sentence-grain decomposition. Each atom carries:

```text
atom_id                 # "<slug>:<comment_id>:<sentence_index>"
comment_id
sentence_index
sentence_text
provisional_claim_class # "ideation" | "opinion" | "anecdote" | "question" |
                        # "link" | "code_snippet" | "security_warning" |
                        # "adoption_recommendation" | "rant" | "humor" | "other"
                        # ALL provisional — never authoritative without later audit
contains_url            # bool
contains_code           # bool
mentions_external_project  # bool
needs_antigence_review     # bool — true when class hints at security/prompt-
                           # injection/adoption-candidate content
```

## Link inventory shape

`LINK-URL-INVENTORY.json` — one record per outbound link mentioned anywhere in
the thread:

```text
link_id
source_comment_id
url
host
scheme
appears_in_root        # bool
mention_count_in_thread
sentence_atom_ids      # back-references
```

No link is auto-followed. No fetching is done here.

## Project relevance candidates shape

`PROJECT-RELEVANCE-CANDIDATES.json` — candidate routings only. Never an
authority for assigning work or claim:

```text
candidate_id
keyword_or_phrase
sentence_atom_ids
suggested_active_projects   # array of project names matched against
                             # /path/to/<project>; never enforced
relevance_signal_class       # "technical_alignment" | "competitive_intel" |
                             # "security_concern" | "adoption_signal" |
                             # "telemetry_or_pattern" | "tooling_recommendation"
operator_review_required     # always true for IDEATION_AND_TRIAGE_ONLY ceiling
antigence_recommended        # true when signal class is security/adoption
```

## Hard halts

Halt with `WEB_DISCUSSION_IMPORT_CUSTODY_VIOLATION` if:

- raw source is not on disk (network fetching is out of scope here);
- source identity cannot be established and `needs_operator_review` is not set;
- source hash is missing for a local file that is safe to hash;
- any record claims `live_writeback_performed=true`;
- any record claims `publication_family_gate=PASS` (this gate is always
  `not_applicable` for web discussions);
- any record claims `claim_ceiling` looser than `IDEATION_AND_TRIAGE_ONLY`
  without an operator-attested deviation receipt;
- identity enrichment beyond public handles is performed (no email lookups, no
  cross-platform handle deanonymization, no private-DB cross-reference);
- a missing adapter is reported as PASS instead of `not_configured`;
- comment bodies are paraphrased / summarized / rewritten in the canonical
  thread JSON (the canonical thread is a structural normalization, not a
  rewrite — body_text must be a verbatim slice of the raw snapshot or marked
  `body_text_missing: true` if extraction failed).

## Validation

Before declaring import complete:

1. Every output JSON parses cleanly.
2. `source_sha256` in `RAW-SOURCE-CUSTODY.json` matches the sha256 of the file
   at `snapshot_path`.
3. `comment_count` in custody manifest equals the length of
   `CANONICAL-THREAD.json.comments`.
4. Every comment_id referenced in `COMMENT-ATOMS.json` exists in
   `CANONICAL-THREAD.json.comments`.
5. Every `sentence_atom_id` is unique.
6. Every link in `LINK-URL-INVENTORY.json` traces back to at least one
   `sentence_atom_id`.
7. `claim_ceiling` is `IDEATION_AND_TRIAGE_ONLY`.
8. `publication_family_gate` is `not_applicable` with an explicit reason.
9. `live_writeback_performed` is `false` across every emitted record.
10. No identity enrichment beyond public handles.

## Report back

- artifact directory path
- source class + URL
- counts: comments, sentence atoms, links, project-relevance candidates
- packages flagged for Antigence (`needs_antigence_review=true`)
- output files emitted
- next skill: `gsigmad-ingest-web-discussion-json`
- explicit boundary statement (no network, no live writeback, claim ceiling
  IDEATION_AND_TRIAGE_ONLY)
