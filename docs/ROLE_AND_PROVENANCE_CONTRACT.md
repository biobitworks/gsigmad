# Role-Lane & Interaction-Provenance Contract

Status: **DRAFT — forward governance rule, pending operator review**
Created: 2026-05-31
Owner repo: `gsigmad` (reusable workflow machinery + receipt vocabulary)
Consumers: Cellico, Watchtower, Antigence, Ollarma, and all gsigmad-governed repos
Registrar of canonical truth: Overwatch (on operator approval only)

This contract generalizes Cellico's project-local `docs/ROLE_LANE_GOVERNANCE.md`
(2026-05-31) into ecosystem machinery, and adds the **interaction-provenance**
scheme (slug + path + hash + signature + parents) so every agent interaction is
traceable into the SeedGraph knowledge graph with governance and provenance.

It is a project-management, execution-control, and provenance rule only. It does
**not** promote claims, authorize experiments, authorize writeback, or change any
repo's `CANON.md` / canonical truth. Watchtower must not own it; Watchtower
projects it read-only.

---

## 1. Roles (authority scopes, not job titles)

| Role | Owns | Must NOT do by default |
| --- | --- | --- |
| `PI` (Principal Investigator) | Scientific direction, hypothesis framing, **claim ceiling**, final interpretation, stop conditions. | Implement code as a substitute for evidence; promote hypotheses without governed evidence; bypass preregistration. |
| `PM` (Project Manager) | Scope, sequencing, resourcing, risk, delivery/acceptance gates, role assignment, handoffs. | Change scientific meaning; run experiments; treat schedule pressure as evidence. |
| `SWE` (Software Engineer) | Implementation, tests, reproducibility, manifests, deterministic checks, execution receipts inside assigned scope. | Make PI-level scientific decisions; tune thresholds after results; broaden scope; perform writeback without approval. |
| `Operator` | **Human approval authority.** The only role that may approve push / mirror / release / DB-KG writeback / claim promotion / canon change. | Be assumed. Operator authority is **never** inferred — see §3. |

`Operator` is applied **only on explicit user approval** for the specific action
in question. An agent runtime never holds `Operator` by default and cannot grant
it to itself or to a child. The default human operator is `byron@biobitworks.com`.

One human or agent may hold more than one role in a session, but the active role
must be explicit. A role change requires a **handoff receipt** (§6) stating what
authority changes and what remains blocked.

---

## 2. Role → runtime authorization matrix

Extends `docs/RUNTIME_INTEGRATION_MATRIX.md`. Runtime identity is honest per that
doc's Runtime Identity Rule — record the *actual* runtime, never hardcode another.

| Lane / runtime | Default role authorization | Ceiling (max role it may ever hold) |
| --- | --- | --- |
| ChatGPT Codex | `PI` / `PM` | `PI/PM/SWE` (never Operator) |
| Claude Code | `SWE` | `PI/PM/SWE` when explicitly assigned (never Operator) |
| Ollarma agents (`helper`, `executor`, `macfind`) | bounded `SWE`-execution only | `SWE` only — never PI/PM/Operator |
| Ollama | none (model backend) | none |
| Antigence (sidecar) | `Review` (advisory) | `Review` only — advisory, never a gate, never Operator |
| Subagents (any runtime) | **inherit parent's role** | **parent's role; may be down-scoped, never up-scoped** |
| Future providers (Gemini/Grok) | none until receipt-bearing contract | propose/review only; no durable truth |

Defaults are overridable per work unit by the role header (§6); the **ceiling is
not overridable** except by an Operator approval that names the runtime and role.

---

## 3. Replayable role loops

Every role has a short loop that must be visible in the work unit and receipt.
The loop is intentionally simple so a later agent can replay the work without
getting stuck in governance loops or inventing a new process.

| Role | Required loop | Deterministic part | Human/authority part |
| --- | --- | --- | --- |
| `PI` | `input -> analysis -> interpretation` | evidence intake, claim-ceiling check, gap list | interpretation, hypothesis priority, claim ceiling |
| `PM` | `scope -> sequence -> gate` | dependency list, acceptance criteria, risk register | priority, stop/go sequencing, role assignment |
| `SWE` | `design -> apply -> verify` | implementation plan, code/config changes, tests/checks | scope changes, interpretation of scientific meaning |
| `Review` | `input -> analysis -> verdict` | artifact inspection, rule checks, cited findings | advisory verdict only; never approval |
| `Operator` | `request -> approve_or_deny -> receipt` | approval request text and receipt capture | the approval/denial itself |

For machine-executable steps, `analysis` and `verify` SHOULD be deterministic
from declared inputs. `apply` SHOULD be deterministic when it is a script,
manifest-backed execution, or mechanical patch; when it is not deterministic,
the receipt MUST say why. Operator approval is intentionally not deterministic;
it is recorded, not replayed.

Cross-role handoff uses the prior role's `output` as the next role's `input`:

```text
PI:       input -> analysis -> interpretation
PM:       interpretation -> scope -> sequence -> gate
SWE:      gate -> design -> apply -> verify
Review:   artifact -> analysis -> verdict
Operator: request -> approve_or_deny -> receipt
```

Stop rather than loop if a role reaches a step outside its authority ceiling.
For example, `SWE.verify` may report a failing scientific threshold, but it must
not reinterpret that threshold into a promoted claim; that returns to PI/PM.

---

## 4. The authority invariant (the rule everything hangs on)

> **A lane can never grant itself, or a child it spawns, more authority than its
> runtime is authorized for. Operator authority originates only from an explicit
> human approval for the named action.**

Consequences:
- Ollarma cannot become PI/PM. A subagent cannot become Operator. A sidecar
  cannot become a gate.
- Subagents and side-cars inherit the parent role and may only be **down-scoped**
  (e.g. a `SWE` parent may spawn a read-only `SWE` probe, never a `PI` decider).
- Any action requiring Operator approval **fails closed** if the role header's
  `approval_role` is not `operator` with a cited approval string.

---

## 5. Applies to subagents, side-cars, and Ollarma agents

- **Subagents** (Agent-tool / `context: fork`): carry the parent's role header;
  emit their own interaction-receipt (§6) with `parents` pointing at the spawning
  receipt. Down-scope only.
- **Side-cars** (e.g. Antigence review sidecar): role is `Review`. Output is
  advisory (`SAFE` / `CAVEAT` / `BLOCKED`); it is a reviewer, not a gate. Emits a
  review receipt that links to the receipt it reviewed.
- **Ollarma agents**: keep their existing `.ollarma/` receipts; add
  `role` (always SWE-execution), `slug`, `content_hash`, and `parents` fields.
  Bounded executor only — no claim promotion, no writeback.

---

## 6. Interaction-receipt (the provenance unit)

Every agent interaction that produces or modifies an artifact, conversation, or
planning document emits **one interaction-receipt**. It is the traceable node
that flows into SeedGraph.

### 6.1 Fields

```jsonc
{
  "receipt_version": "1.0",
  "slug": "260531-gsigmad-pmswe-claudecode-role-provenance-contract-<shorthash>",
  "created_at": "2026-05-31T16:00:00Z",         // ISO-8601 Z (passed in, not Date.now)
  "runtime": "claude-code",                       // actual runtime identity
  "role_header": {                                // §7 - authority block IS the signature subject
    "role_lane": "PM/SWE",
    "role_owner": "claude-code (under operator direction)",
    "decision_owner": "operator",
    "execution_owner": "SWE",
    "review_owner": "operator",
    "approval_owner": "operator",
    "writeback_disposition": "blocked",
    "claim_ceiling": "GOVERNANCE_ONLY"
  },
  "artifact_path": "gsigmad/docs/ROLE_AND_PROVENANCE_CONTRACT.md",  // POINTER, owner-repo-relative
  "content_hash": "sha256:<64hex>",               // sha256 of the referenced artifact
  "parents": ["<prior receipt slug>", "..."],     // provenance DAG / Merkle chain
  "signature": "SIG-20260531T160000Z-claudecode-role-provenance-contract",
  "session_pointer": "~/.ollarma/swe_session/session-log.jsonl#<entry>",  // cross-agent ledger
  "determinism_note": "deterministic"             // see §5.3
}
```

### 6.2 Slug grammar (deterministic, human-readable, collision-resistant)

```
{date:YYMMDD}-{repo}-{role}-{runtime}-{task-kebab}-{shorthash}
        260531 -gsigmad -pmswe -claudecode -role-provenance-contract -<first 8 of content_hash>
```

- `shorthash` = first 8 hex chars of `content_hash`. This binds the slug to the
  exact content, so the same interaction always reproduces the same slug.
- `signature` = `SIG-{ISO8601-compact}-{runtime}-{task-kebab}` (Cellico's existing
  format, kept for continuity with its change log).

### 6.3 Determinism rule

The slug and signature MUST be derived from the content hash + a **passed-in**
timestamp. Never use wall-clock randomness (`Date.now()` / `Math.random()` / argless
`new Date()`) — those break replay and verifiability. `determinism_note` is one of
`deterministic` / `deterministic_if_manifest_fixed` / `operator_action_not_deterministic`.

---

## 7. Required role header (on every governed work unit)

```text
Role lane:            <PI|PM|SWE|Review|PI/PM|PM/SWE|PI/PM/SWE>
Role owner:           <human or agent/runtime>
Decision owner:       <PI|PM|SWE|operator>
Execution owner:      <PI|PM|SWE|not_applicable>
Review owner:         <PI|PM|SWE|operator>
Approval owner:       <operator|not_required>      # operator only, with cited approval string
Worktree / branch:    <path and branch, or not_applicable>
Writeback disposition:<not_applicable|blocked|deferred|dry_run_only|approved_with_manifest>
Claim ceiling:        <HYPOTHESIS|GOVERNANCE_ONLY|MEASURED|...>
```

Use on: PROMPT/EXP preregistration, TASK records, wave/phase plans, quick planning
folders, red-team/remediation packets, run-readiness checklists, writeback/export
decision packets. The role header on the active work unit is the controlling
authority (defaults in §2 only apply when the header is silent).

---

## 8. Where receipts live and how they reach the KG

```
emit (at the lane)                  vocabulary/schema        ingest                 promote
─────────────────                   ─────────────────        ──────                 ───────
Claude Code / Codex                 gsigmad owns the         SeedGraph ingests      Overwatch
  → owner-repo receipt ledger        slug grammar, hash       receipts via the       registers
    (.gsigmad/receipts/ or           rule, signature          deterministic          canonical truth
    .planning/quick/<lane>/)         format, role header.     chain-of-custody       — operator-gated
  → + pointer line into scribe                                path (Merkle-proof).   writeback only.
    ~/.ollarma/swe_session/                                   node = receipt;
    session-log.jsonl                                         edge = parents +       Watchtower
Ollarma agents                                                role/authority.        projects/queries
  → .ollarma/ receipts (+ new fields)                                                read-only.
```

Rules:
- Receipts store a **pointer + hash**, never a durable copy of sibling-repo truth
  (`DOCUMENT_OWNERSHIP_CONTRACT`).
- A receipt is **emitted at the lane that did the work**, in that work's owner repo.
- Cross-agent visibility comes from a one-line pointer mirrored into the scribe
  `session-log.jsonl`; the durable receipt stays in the owner repo.
- Promotion to canonical KG truth is an Operator-gated Overwatch writeback — never
  automatic.

---

## 9. Worktree / branch rule (lane isolation)

For parallel roles/agents in one repo: **one git worktree and one branch per active
lane.** Each lane gets its own index → no `.git/index.lock` contention. Integrate
through explicit review / PR-style merge, never by multiple agents writing one
checkout. Minimum lane record:

```text
Lane id: <short slug>      Role lane: <...>        Worktree path: <path>
Branch: <branch>           Base ref: <ref>         Integration target: <branch/review>
Single-writer rule: <who may write in this lane>
```

This is the structural fix for the cross-lane collision class; the
`bash_batch_guard` `git-index-lock` rule only *flags* contention at the command
level — it does not replace per-lane worktrees.

---

## 10. Stop conditions

Stop and escalate if:
- a `SWE` lane is asked to choose scientific interpretation, nulls, thresholds, or
  promotion language without PI approval;
- a `PI`/`PM` lane is about to edit implementation files without an explicit SWE
  assignment;
- a lane or subagent would exceed its §2 ceiling, or a child would up-scope;
- an action needs Operator approval but `approval_owner` is not `operator` with a
  cited approval string;
- two agents are writing the same checkout for different lanes;
- a role handoff omits claim ceiling, writeback disposition, or owner repo;
- an interaction-receipt is missing slug, content_hash, or signature.

---

## Change Log

| Date | Signature | Type | Description |
| --- | --- | --- | --- |
| 2026-05-31 | SIG-20260531T160000Z-claudecode-role-provenance-contract | CREATE | Generalized Cellico role-lane governance to gsigmad machinery; added Operator role + explicit-approval rule, role→runtime authorization matrix with non-up-scope ceiling, and the interaction-receipt provenance scheme (slug/path/hash/signature/parents) flowing to SeedGraph via Overwatch-gated writeback. DRAFT pending operator review. |
