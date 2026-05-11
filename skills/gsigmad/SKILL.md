---
name: gsigmad
description: "Anchor skill for the Getting Science Done (gsigmad-*) framework. Trigger on 'gsigmad', 'gettingsciencedone', 'start a science project', 'write a PROMPT', 'preregister an experiment', 'audit claims', 'triage this', 'here is an image', 'here is a dataset', 'here is a publication', 'red team', 'research and remediate', 'import publications', 'ingest publications', 'publication JSON', 'SeedGraph Merkle', 'chain of custody', 'HN thread', 'Hacker News', 'Reddit thread', 'forum thread', 'GitHub discussion', 'public comment thread', 'web discussion', or any request that mentions the gsigmad/gettingsciencedone namespace. Explains the gsigmad/gsd split and routes to the right sub-skill."
allowed-tools: Read, Bash, Glob, Grep
---

# gsigmad — Getting Science Done

You were invoked because the user mentioned **gsigmad** or **gettingsciencedone**, asked to start a science project / write a prompt / preregister an experiment / audit a claim, or asked how Ollarma, Watchtower, Antigence, Overwatch, Claude Code, ChatGPT Codex, Gemini, or Grok fit into the governance bridge. Your job is to disambiguate, then route to the right sub-skill.

## Two prefixes — never collapse them

| Prefix | Project | Role |
| --- | --- | --- |
| `gsd-*` | **Get Shit Done** (npm `get-shit-done-cc`) | Generic workflow scaffolding — phases, plans, execution, verification, code review. |
| `gsigmad-*` | **Getting Science Done** (`<gsigmad-upstream-dev-repo>`) | Science governance — preregistration (PROMPT artifacts), claim auditing, drift scanning, citation hygiene, FAIR checks, ablation, model identifiability, negative-result protection, replication contracts. |

They share the spoken acronym "GSD" but are separate namespaces and separate codebases. Per `~/projects/CLAUDE.md`:

> Get Shit Done = `gsd-`; Getting Science Done = `gsigmad-`. Never collapse them.

## Available `gsigmad-*` skills

- `gsigmad-quick` — fast front-door triage; classifies an ask/artifact, selects the skill chain, writes the prompt, and tells where it goes
- `gsigmad-redteam-research-remediate` — creates red-team, research, and remediation prompt package for adversarial review before execution
- `gsigmad-session-start` — start-of-session checklist (active EXP status, drift scan, PROMPT integrity)
- `gsigmad-session-pause` / `gsigmad-session-end` — handoff with change-log compliance
- `gsigmad-create-prompt` — author a PROMPT-### preregistration artifact (H0/H1/test/alpha/MESI required for confirmatory experiments)
- `gsigmad-run-experiment` — gated experiment execution with literature traceability and ProtHub writeback
- `gsigmad-find-experiments` — query the experiment knowledge graph across projects
- `gsigmad-audit-claims` — claim linter + hypothesis-promotion + causal guardrail
- `gsigmad-audit-output` — output auditor + reproducibility auditor
- `gsigmad-data-contract` — enforce data contract on experiment artifacts
- `gsigmad-cite` — citation governance and verification
- `gsigmad-drift-scan` — degradation/drift detection
- `gsigmad-fair-check` — FAIR principle compliance
- `gsigmad-model-identifiability` — model identifiability audit
- `gsigmad-negative-results` — negative-result protection
- `gsigmad-ablation` — ablation orchestrator
- `gsigmad-handoff` — cross-agent handoff with change-log compliance
- `gsigmad-governance-bridge` — bridge routing across gsigmad, Ollarma/Ollama, Watchtower, Antigence, Overwatch, and model runtimes
- `gsigmad-review-report` — review-stage reporting
- `gsigmad-export` — export experiment package
- `gsigmad-import-publications-json` — publication/source package import to canonical local JSON only; no live writeback
- `gsigmad-ingest-publications-json` — SeedGraph deterministic ingest with Merkle-backed `publication.atomic.json` proof and chain-of-custody gate
- `gsigmad-route-publication-destinations` — destination matrix + deferred writeback queue for Overwatch / ProTHub / ProAtlas / SeedGraph KG / triage / research_hub
- `gsigmad-writeback-overwatch` — operator-approved Overwatch writeback from verified Merkle/custody queue only
- `gsigmad-writeback-science-databases` — operator-approved writeback to configured science databases with receipts
- `gsigmad-audit-import-ingest-completeness` — fail-closed audit for JSON, Merkle proof, custody receipts, queue, restricted-data, and adapter status
- `gsigmad-import-web-discussion-json` — public web discussion (HN, Reddit, forum, GitHub discussion, Discord export, blog comments) import to canonical local JSON; publication-family gate is `not_applicable`
- `gsigmad-ingest-web-discussion-json` — 11-gate ingest for web discussion JSON with deferred review queue, Antigence recommendations, and `IDEATION_AND_TRIAGE_ONLY` claim ceiling enforcement
- `gsigmad-audit-web-discussion-ingest` — fail-closed audit of a completed web-discussion import/ingest pair before any operator action or downstream routing

## Common entry intents → routing

**"Here is an image / dataset / publication / output / claim — triage it"**
- Route directly to `/gsigmad-quick`.
- It must return artifact class, target repo, owning system, risk class,
  primary skill chain, prompt destination, ready-to-paste prompt, and next step.
- It should write prompt packages to the owning repo under
  `<target_repo>/.planning/quick/<YYMMDD>-<slug>/`, not into
  `gettingsciencedone`, unless the framework itself is being changed.

**"Red team / research / remediate / what am I missing?"**
- Route to `/gsigmad-redteam-research-remediate`.
- It writes `REDTEAM-PROMPT.md`, `RESEARCH-PROMPT.md`, and
  `REMEDIATE-PROMPT.md` in the owning repo's `.planning/quick/` directory.
- Red-team comes before remediation. Research findings must cite local files or
  mark claims unresolved.

**"Start a new science project"**
1. Use `/gsd-new-project` for repository scaffolding (PROJECT.md, ROADMAP.md, planning surface).
2. Then `/gsigmad-session-start` to establish the experiment-governance baseline (PROMPT integrity, drift scan, EXP map).
3. Use `/gsigmad-create-prompt` for the first PROMPT-### artifact before any experimental code runs.

**"Write a prompt" or "preregister an experiment"**
- Route directly to `/gsigmad-create-prompt`. It enforces:
  - H0/H1, statistical test, alpha, MESI (justified, not arbitrary)
  - Power analysis (min N to detect MESI at alpha with power ≥ 0.80)
  - PROMPT_EXP_MAP update in the same session
- For confirmatory or replication experiments, the preregistration fields are required — do not bypass.

**"Audit a claim" / "check this output"**
- `/gsigmad-audit-claims` for hypothesis/promotion/causal guardrail.
- `/gsigmad-audit-output` for reproducibility and output auditing.

**"Run an experiment"**
- `/gsigmad-run-experiment` — gates on literature traceability and ProtHub writeback.

**"Import publications" / "ingest publications" / "literature import" / "publication JSON"**
Route through the publication custody chain. Do not collapse these steps:

1. `/gsigmad-import-publications-json` — source packages -> canonical local JSON.
2. `/gsigmad-ingest-publications-json` — canonical JSON -> SeedGraph deterministic ingest and `publication.atomic.json`.
3. `/gsigmad-route-publication-destinations` — verified JSON/proof -> destination matrix and deferred writeback queue.
4. `/gsigmad-audit-import-ingest-completeness` — fail-closed audit before promotion or writeback.
5. `/gsigmad-writeback-overwatch` and/or `/gsigmad-writeback-science-databases` — only after explicit operator approval.

SeedGraph import/ingest governance is Merkle-first moving forward. A package
cannot be promoted beyond local JSON unless it has source identity, source hash,
deterministic Merkle roots, replay fingerprint, append-only receipt/ledger
chain, and a valid signature or explicit untrusted-dev-key warning. Missing
adapters are `not_configured`, never PASS.

**"HN thread" / "Hacker News" / "Reddit thread" / "forum thread" / "GitHub discussion" / "GitHub issue" / "Discord export" / "Slack export" / "blog comment thread" / "public comment thread" / "web discussion"**
Route through the **web-discussion source-seed custody chain**, *not* the
publication custody chain. Do not collapse these steps:

1. `/gsigmad-import-web-discussion-json` — raw snapshot + canonical thread + comment tree + URL inventory + custody manifest.
2. `/gsigmad-ingest-web-discussion-json` — 11-gate ingest matrix, deferred review queue, Antigence recommendations, completion receipt.
3. `/gsigmad-audit-web-discussion-ingest` — fail-closed audit before any operator action or downstream routing.
4. If security / prompt-injection / tooling-adoption candidates were emitted, route through `/gsigmad-governance-bridge` for Antigence review before implementation.

Non-negotiable for this lane:

- Claim ceiling defaults to `IDEATION_AND_TRIAGE_ONLY`. HN/Reddit/forum/GitHub-discussion comments are **never** scientific evidence or product truth without a subsequent `gsigmad-audit-claims` review.
- Publication-family gate is `not_applicable` (recorded explicitly with reason, **never** PASS).
- No identity enrichment beyond public handles. No email lookup. No cross-platform handle deanonymization.
- No network fetching from within these skills — the raw snapshot must already be on disk.
- Missing adapters are `not_configured`, never PASS.
- Antigence status values: `not_configured`, `recommended`, `queued`, `completed`, `blocked`. Never claim `completed` without a verified review receipt.

**"End or pause the session"**
- `/gsigmad-session-pause` (mid-session) or `/gsigmad-session-end` (closing).
- Both apply change-log compliance.

**"How does Ollarma / Watchtower / Antigence / Overwatch / Gemini / Grok fit?"**
- Route to `/gsigmad-governance-bridge`.
- It classifies the runtime/project role and blocks direct truth/writeback claims.


## Source of truth

- Repo: `<gsigmad-upstream-dev-repo>`
- Repo CLAUDE.md / AGENTS.md govern behavior inside that repo.
- Skill source files live at `gettingsciencedone/skills/gsigmad-*/SKILL.md` and are symlinked into `~/.claude/skills/` and `~/.codex/skills/` for runtime discovery. Edit in source; both runtimes pick up changes immediately.

## What this skill does NOT do

- It does **not** itself run experiments, write prompts, or audit claims. It is an anchor + router.
- After you (the agent) have identified the intent, hand off to the specific `gsigmad-*` or `gsd-*` skill. Do not execute their work inline.

## Disambiguation rule

If the user's request is ambiguous between gsd and gsigmad (e.g. "start a project" — could be either), ask one clarifying question:

> Is this a science experiment (preregister with `gsigmad`) or a generic software project (scaffold with `gsd`)? They can be combined — gsd handles repo scaffolding, gsigmad handles the science governance layer on top.
