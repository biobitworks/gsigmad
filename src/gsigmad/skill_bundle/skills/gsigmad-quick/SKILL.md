---
name: gsigmad-quick
description: "Fast science-governance triage shortcut. Use when the user says: here is an image/dataset/publication/claim/output, triage it, tell me what to do next, write a prompt, decide where the prompt goes, or pick the right gsigmad skill chain."
allowed-tools:
  - Read
  - Write
  - Bash
  - Glob
  - Grep
---

# gsigmad-quick

Fast front-door triage for science-governance work. This skill converts a raw
operator ask into a routed next step, a prompt, and a destination path.

Use this when the request is too small or urgent for a full milestone but still
needs gsigmad guardrails.

## What This Shortcut Answers

For any input such as:

- "here is an image"
- "here is a dataset"
- "here is a publication"
- "here is a claim"
- "here is an output"
- "triage this"
- "write a prompt"
- "what should I do next?"

Return:

1. artifact class
2. risk class
3. right skill chain
4. target repo
5. prompt destination
6. next command / next paste target
7. stop boundary

## Required Discovery Pass

Before writing the prompt or choosing the final route, inspect the existing
workflow surfaces so the answer reuses current machinery instead of inventing a
new lane.

Read or search only the relevant slices; do not bulk-load every file.

### gsigmad / Getting Science Done surfaces

Use these as source-of-truth for science governance:

```text
<gsigmad-upstream-dev-repo>/skills/
<gsigmad-upstream-dev-repo>/.planning/STATE.md
<gsigmad-upstream-dev-repo>/LAB_NOTEBOOK.md
<gsigmad-upstream-dev-repo>/README.md
```

If present for the target task, also inspect:

```text
<gsigmad-upstream-dev-repo>/templates/
<gsigmad-upstream-dev-repo>/workflows/
```

### Get Shit Done / GSD surfaces

Use these for generic workflow scaffolding, prompt-package shape, quick-task
state updates, and execution/review lanes:

```text
~/.codex/skills/gsd-quick/
~/.codex/skills/gsd-fast/
~/.codex/skills/gsd-import/
~/.codex/skills/gsd-ingest-docs/
~/.codex/skills/gsd-code-review/
~/.codex/skills/gsd-plan-phase/
~/.codex/skills/gsd-execute-phase/
~/.codex/skills/gsd-verify-work/
~/.codex/get-shit-done/workflows/
~/.codex/get-shit-done/templates/
```

Pick only what matches the ask. Examples:

- prompt-only triage -> inspect `gsd-quick` and gsigmad route skill;
- import/ingest -> inspect gsigmad import/ingest skills plus `gsd-import` if
  generic import workflow shape is needed;
- red-team/remediate -> inspect `gsigmad-redteam-research-remediate`,
  `gsd-code-review`, and relevant auditor skills;
- phase implementation -> inspect `gsd-plan-phase` / `gsd-execute-phase`.

### Discovery output

The final triage must include:

```text
consulted_gsigmad_surfaces:
consulted_gsd_surfaces:
existing_skill_to_reuse:
new_prompt_needed: true|false
```

## Triage Classes

| Input | Route |
| --- | --- |
| Image / figure / screenshot | inspect locally, classify claim risk, then prompt for extraction or visual audit |
| Dataset / table / supplement | `gsigmad-data-contract` first; row-level gate before extraction |
| Publication / citation / PDF / preprint / NIHMS / bibliography | `gsigmad-import-publications-json` -> `gsigmad-ingest-publications-json` -> `gsigmad-route-publication-destinations` -> `gsigmad-audit-import-ingest-completeness`. **Merkle-first**; `publication.atomic.json` required. |
| Web discussion / HN / Hacker News / Reddit / forum / GitHub discussion / GitHub issue / Discord export / Slack export / blog comments / public comment thread | `gsigmad-import-web-discussion-json` -> `gsigmad-ingest-web-discussion-json` -> `gsigmad-audit-web-discussion-ingest` -> (if security / prompt-injection / adoption candidates) `gsigmad-governance-bridge` for Antigence review. **Claim ceiling: IDEATION_AND_TRIAGE_ONLY. Publication-family gate: not_applicable (explicit, never PASS).** |
| Scientific claim / interpretation | `gsigmad-audit-claims` |
| AI output / results bundle | `gsigmad-audit-output` |
| Existing EXP / PROMPT | `gsigmad-create-prompt`, `gsigmad-run-experiment`, or `gsigmad-session-*` |
| Need adversarial review | `gsigmad-redteam-research-remediate` |
| Cross-system routing | `gsigmad-governance-bridge` |

### Three-way source-class distinguisher

When the input is ambiguous between "publication", "web discussion", and "dataset",
classify by the **canonical identifier** the source carries, not by file
extension or location:

| Canonical identifier present | Source class | Lane |
|---|---|---|
| DOI / PMID / PMCID / NIHMS / journal title + year + author | **publication** | publication custody chain (Merkle-first) |
| HN item id / Reddit `t1_*` / `t3_*` id / GitHub discussion/issue URL / forum thread URL / `discord_export.json` / `slack_export.zip` | **web discussion** | web-discussion source-seed chain (claim ceiling `IDEATION_AND_TRIAGE_ONLY`) |
| Tabular columns / schema / row-level records / accession id (PRIDE, dbGaP, GEO, SRA, CPTAC) | **dataset** | `gsigmad-data-contract` then row-level gate |

A source that carries **none** of these identifiers but is operator-asserted as
science evidence must halt with `gsigmad-quick` returning
`SOURCE_CLASS_UNDETERMINED` and an operator-clarification prompt — do not
default to publication lane and do not default to web-discussion lane.

## Prompt Destination Rule

Put prompt packages in the owning repo, not in the gsigmad framework repo unless
the task is changing the framework itself.

Use:

```text
<target_repo>/.planning/quick/<YYMMDD>-<short-slug>/
```

Required files:

```text
PLAN.md
PROMPT.md
SUMMARY.md
```

For red-team/research/remediate packages, use:

```text
REDTEAM-PROMPT.md
RESEARCH-PROMPT.md
REMEDIATE-PROMPT.md
```

## Quick Output Template

```markdown
# Gsigmad Quick Triage

## Classification
- Input type:
- Target repo:
- Owning system:
- Risk class:
- Row-level / restricted-data risk:
- Claim-promotion risk:

## Route
- Primary skill:
- Follow-on skills:
- Stop boundary:

## Prompt Destination
- Directory:
- Prompt file:

## Paste Prompt
[write a ready-to-paste prompt here]

## Next Step
[one exact command or paste target]
```

## Hard Stops

Stop and ask for operator approval if:

- live database writeback is requested;
- row-level peptide/protein/sequence/quantitative/patient/sample data would be
  extracted;
- a publication package would be promoted without SeedGraph Merkle proof;
- a web-discussion comment would be promoted to scientific or product
  evidence without a subsequent `gsigmad-audit-claims` review (the
  `IDEATION_AND_TRIAGE_ONLY` ceiling is non-negotiable);
- claim wording would move beyond the available evidence class;
- target repo is ambiguous and the prompt could mutate the wrong project;
- a public web discussion would be forced through the publication custody
  chain (it has no DOI/PMID/Merkle family — route to
  `gsigmad-import-web-discussion-json` instead);
- identity enrichment beyond public handles is implied (no email lookup, no
  cross-platform handle resolution).

## Default Shortest Route

When uncertain, use this route:

1. `gsigmad-quick` triage.
2. Write prompt package to `<target_repo>/.planning/quick/<date>-<slug>/`.
3. If publication/source package: require JSON-first import via the
   publication custody chain (`gsigmad-import-publications-json` →
   `gsigmad-ingest-publications-json` → ...). Merkle-first.
4. If public web discussion (HN / Reddit / forum / GitHub
   discussion / Discord export / blog comments): require the
   web-discussion source-seed chain (`gsigmad-import-web-discussion-json` →
   `gsigmad-ingest-web-discussion-json` →
   `gsigmad-audit-web-discussion-ingest`). Claim ceiling
   `IDEATION_AND_TRIAGE_ONLY`. Publication-family gate `not_applicable`.
5. If dataset/table: require data contract and row-level gate.
6. If claim/output: audit before remediation.
7. If adversarial review needed: call `gsigmad-redteam-research-remediate`.

## Report Back

- fastest safe route
- prompt path
- exact prompt text
- next command / paste target
- blocked approvals, if any
