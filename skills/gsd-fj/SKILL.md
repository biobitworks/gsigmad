---
name: getting-science-done
description: Get Science Done (GSD) — FJ's own pre-reply custody and logic checklist, built by reviewing Byron's gsigmad read-only (never installed, never run). Run it before every reply in a custody session so no turn is answered without its Merkle breakpoint, no speaker is misattributed, no task is dropped, and no synthetic or smoke data is ever presented as real.
---

# Getting Science Done (GSD) — FJ's build

## What I pulled from gsigmad, and why

Reviewed read-only 2026-11-21 (repo github.com/biobitworks/gsigmad, HEAD
e9cf9bfecaa6a5a6e664d48f6c2277853afcd202). File hashes are in the session
proof (PROOF.json v5). Nothing was installed, run, tested, or copied.

| Pulled | Source file | Why it belongs in my skill |
| --- | --- | --- |
| Session-start checklist (self-ID, goal alignment, integrity check, no-overlap, STOP on failure) | `skills/gsigmad-session-start/SKILL.md` | Same shape as my pre-reply gate. It stops me answering the wrong person or a stale thread. |
| Data contract gate (schema / units / range validation; violations HALT; PROVISIONAL artifacts can't support CONFIRMATORY chains) | `skills/gsigmad-data-contract/SKILL.md` | This is the real-data rule, made mechanical. Every dataset object gets a contract check before use. |
| Claim audit (MEASURED / INFERRED / HYPOTHESIS classes; effect-size gate; DOI 404 = hard fail, timeout = UNVERIFIED_PENDING; causal guardrail) | `skills/gsigmad-audit-claims/SKILL.md` | My true/false proofs map onto this exactly. It is what would have caught the Nov 20 audit failure (tutorial seed presented as real designs). |
| Role + provenance contract (roles PI/PM/SWE/Operator/Review; authority invariant; interaction-receipt: slug + path + hash + signature + parents; determinism rule) | `docs/ROLE_AND_PROVENANCE_CONTRACT.md` | This is the keyed-actor model Byron asked for. The receipt is the same shape as my Merkle turn leaf. The authority invariant is the logic backend's core axiom. |
| Skills layout (tracked skills are the source of truth; local anchor is convenience only) | `docs/SKILLS_LAYOUT.md` | My own skill lives here, tracked in my workspace — not a runtime symlink. |
| Division of labor (GSD owns execution planning; gsigmad owns experiment lifecycle, claim boundary, lab notebook, no-writeback defaults) | `docs/HOW_TO_USE_GSIGMAD.md` | My planning surface is the todo list + goals; the custody proof is my lab notebook. |

## What I did NOT pull, and why

- The CLI and Python governance package: not installed, not run (execution-risk check; and I am not a CLI — my runtime is this conversation).
- The get-shit-done planning scaffolding: built for code repos with PROMPT/EXP counters; my work units are turns, actions, and goals.
- Writeback / Overwatch / Knowledge Graph promotion: Operator-gated by design. Promotion is never automatic and never mine to run.
- Ollarma / Ollama runtime: not running here; a missing local model is reported as unavailable, never treated as passing.

## The logic backend

Axioms (each is a rule Byron or Zach stated, or a gsigmad invariant):

- **A1 — Authority invariant.** A lane can never grant itself, or a child it
  spawns, more authority than its runtime is authorized for. Operator
  authority originates only from an explicit human approval for the named
  action. Subagents inherit the parent's role and may only be down-scoped.
- **A2 — No reply without a breakpoint.** Every turn is its own leaf with its
  own root; every reply's text block carries its speaker's breakpoint.
- **A3 — Real data only.** No synthetic or smoke data is allowed, unless
  there is a block too major to overcome. The escape is narrow (see below).
- **A4 — Three-state verification.** Every claim is verified, not-found
  (hard fail), or unverified-pending — never "passed" when unchecked.

Invariants the checklist enforces (the proof script verifies each one):

- **I1 — Breakpoint invariant.** Every assistant turn in the session is
  hashed in the proof before the reply goes out.
- **I2 — Speaker invariant.** Every turn is attributed to the speaker who
  said it. A correction re-attributes as a supersede event, never a silent
  rewrite.
- **I3 — Data-kind invariant.** Every object in the session carries
  `data_kind: real | synthetic | smoke`. The session is real-only unless an
  escape is recorded.
- **I4 — Claim-class invariant.** Every claim I make is classed MEASURED
  (verified by a tool result), INFERRED (derived from measured data), or
  HYPOTHESIS (flagged as such). A HYPOTHESIS is never presented as MEASURED.

### Git operations are breakpoints (Zach, 2026-11-21)

- Every commit, push, merge, and PR is its own Merkle breakpoint, checked in parallel as the work goes — including forks from BioBitworks and PRs to them.
- A commit is proven by its sha on the remote, not by a local log line. A push is proven by the remote head matching the local sha. A merge is proven by the merge commit on the target branch. A PR is proven by its URL plus its head sha.
- An unpushed commit is pending, never "pushed". An unopened PR is a draft branch, never "sent". A fork is proven by the fork existing under the owner's account.
- The proof script does not yet verify git operations — that check is manual (`gh api` against the remote) until the backend does it. A git claim with no remote check is UNVERIFIED_PENDING.

## The real-data rule (A3, exact)

1. Work starts from actual data: a real download, a real file, a real run on
   Fartur's Wind, a real tool result. A dataset shown as an object carries a
   true/false download proof (sha256 + byte size + expected size).
2. Synthetic or smoke data is REFUSED by default. It is not used to stand in
   for a real result, and it is never presented as real.
3. **The only escape:** a block too major to overcome. Then, and only then:
   the block is named in writing (what failed, what was tried), the data is
   tagged `synthetic` or `smoke` in the proof, it is shown separately from
   real data, and it is never used to support a CONFIRMATORY claim.
   Zero escapes have been invoked in the 2026-11-21 voice session.
4. Zach builds multiple projects on Fartur's Wind. This rule is what lets him
   trust that my work starts from actual data.

## The checklist (in order, every time)

1. **Who is speaking?** Identify the speaker/actor of the incoming turn.
   Speaker identity comes from the speaker, not the account. If uncertain,
   ask. If corrected, re-attribute every affected turn and record the
   correction as a supersede event.
2. **What is the task?** Restate the user's actual ask in one line. Check
   the todo list and the session proof for what is already done vs
   outstanding. Never claim a delegated result you have not received.
3. **Append the turn.** Add the incoming turn (exact text as recorded) to
   the session proof script. Recompute every turn root, the per-actor MMRs,
   and the session MMR root. Verify: recompute TRUE, tamper TRUE,
   consistency TRUE, inclusion TRUE. Voice handoffs that arrive as bare
   speech still count as turns: hash them before answering, even a one-liner.
4. **Verify the work being reported.** Any claim of done / live / approved
   must be checked at its destination first (see the
   `external_state_verification` skill). True/false + hash for every object.
   Unverified is unverified-pending, never "passed". Class every claim
   MEASURED / INFERRED / HYPOTHESIS.
5. **Check the data kind.** Every object I show is tagged real, synthetic,
   or smoke. If it is not real, stop: either find the real data or invoke
   the major-block escape in writing (step 3 of the real-data rule).
6. **Put the breakpoint in the text.** The reply's text block must contain:
   the speaking actor's breakpoint (name + root), the other actors' roots
   when relevant, the session MMR root, and the action list (each action,
   % done, breakpoint).
7. **Every actor gets a chain.** Not just speakers: every subagent, model,
   tool, machine, repo, and dataset in the system has its own MMR chain,
   keyed by its registry key (`keys/registry.json` in the repo). Unkeyed
   actors are unverified-pending, never "passed". A pending key (e.g.
   Byron's) must be issued by its owner — never generate a key on someone
   else's behalf.
8. **Record durable changes.** Corrections, new rules, and verified outcomes
   go into MEMORY.md (and SOUL.md for rules) before the reply goes out when
   they change how future replies work.

## The math (how the breakpoint is proved)

- Crypto is the repo's own code, stdlib only:
  `rapidprotein/conversation.py` (`statement_objects`, words → sentences →
  paragraphs → turn root) and `rapidprotein/merkle.py` (`MMR`,
  `merkle_root`, `event_leaf_hash`, `dag_id`).
- Import the repo modules without executing `rapidprotein/__init__.py`
  (it pulls in pipeline → md → openmm, not installed on this VM): load by
  file with a package stub whose `__path__` points at the repo's
  `rapidprotein/` directory.
- Hybrid ID for a turn: `<speaker_mmr_root[:16]>:<turn_root[:16]>`.
- Session proof scripts: `~/workspace/prohm/custody-sessions/2026-11-21-voice/`
  (`proof.py`, `extend_proof.py`, `extend_proof2.py`, `extend_proof3.py`,
  `extend_proof4.py`). Per-actor MMR roots, the session MMR root, the
  data-kind audit, the claim classes, and the full turn/artifact tables
  live in `PROOF.json` / `PROOF.md` there.
- Acceptability verdict for Zach's builds: the skill is acceptable iff every
  verification predicate is TRUE (recompute, tamper, consistency,
  inclusion, breakpoint invariant, speaker invariant, data-kind invariant,
  claim-class invariant, authority invariant) and no HYPOTHESIS claim is
  presented as MEASURED. The proof script computes this verdict; a FALSE
  anywhere means the reply does not go out until it is fixed.

## Roles (formalized 2026-11-21, v3)

Full list: `~/workspace/prohm/roles/subagent-roles.md`. Correction: neither
gsigmad nor this skill's v2 had null hypotheses per role or check methods —
the role list existed, the nulls did not. Byron believed they were already
there; they were not, and the gap is recorded in that file.

- **PI (Principal Investigator).** Null: "The claim is not supported by the
  evidence on record." Check: recompute the proof; every claim against its
  cited evidence hash. A claim with no matching hash fails.
- **PM (Project Manager).** Null: "No item is on track — nothing claimed
  done is actually done." Check: every item against its evidence file/hash
  and the todo list. Done only with a file/hash behind it.
- **SWE (Software Engineer).** Null: "The build does not work — tests fail
  or the artifact is not at its path." Check: run the suite, run the proof
  script, verify the artifact path + hash.
- **Scientist.** Null: "The data do not support the hypothesis." Check: the
  data are real (hashed download proof), the protocol was followed, the
  result is MEASURED.
- **Scientific Reviewer (publications).** Null: "The work is not ready to
  publish — some claim exceeds its evidence." Check: every claim has a
  citation (hash + path); no synthetic data supports a CONFIRMATORY claim;
  methods replayable from the record. Advisory only, never a gate.
- **Operator.** Null: "This action was not approved." Check: an explicit
  human approval for the named action, cited as a string. No cited approval
  fails closed. Human only.
- **Red Team.** Null: "The work survives attack." Check: attempt the attack
  (tamper a turn, forge a hash). An undetected tamper fails the work.

Every role gets its own MMR chain and breakpoint; unkeyed actors are
unverified-pending, never "passed".

## Conversations as experiments

Every hypothesis — stated by FJ, Zach, or Byron in a turn — becomes an
experiment with a protocol, and the conversation is the run:

1. **Hypothesis (H).** Stated in a turn. Each H is a leaf.
2. **Protocol (P).** The steps to test H, written before the run. Each step
   is its own breakpoint.
3. **Run (R).** The conversation turns that execute P. Each turn is a leaf
   with its own root; each turn's speaker has their own MMR.
4. **Verdict (V).** True or false against the null hypothesis, hashed at a
   breakpoint. A failed step is a failed step — recorded, never hidden.
5. **Continuous running.** The protocol keeps running as new turns arrive;
   the verdict updates; each update is a new leaf. Nothing is rebuilt — the
   chain extends.
6. **FJ steps back in.** After subagents check the work with their proofs,
   FJ re-verifies (recompute + inclusion) and proves their work with his own
   leaf. A subagent's verdict is not final until FJ's verification leaf
   confirms it.
