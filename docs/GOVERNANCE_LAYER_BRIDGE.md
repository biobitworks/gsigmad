# Governance Layer Bridge

`gsigmad` is the governance layer for multi-agent scientific work. It lets
Claude Code, ChatGPT Codex, Ollarma/Ollama, and future provider lanes cooperate
without confusing model output with durable truth.

## Purpose

The bridge exists so a task can move through local helper, bounded execution,
review, and truth promotion while preserving source ownership.

## Runtime Roles

| Runtime | Role |
| --- | --- |
| Claude Code | coding/runtime agent that can use gsd and gsigmad skills |
| ChatGPT Codex | coding/runtime agent that can use the same `SKILL.md` surfaces |
| Ollarma | bounded local execution bridge and receipt producer |
| Ollama | local model backend under Ollarma |
| Gemini/Grok | future provider lanes, allowed only through receipt-bearing contracts |

## Control Plane Roles

| System | Role |
| --- | --- |
| gsigmad | science governance and workflow contract |
| Watchtower | downstream operator projection |
| Antigence | review/escalation sidecar |
| Overwatch | canonical portfolio truth and promotion |
| SeedGraph | graph/evidence structure under governed adoption |

## Data Flow

1. A task is proposed by an operator or agent.
2. gsd handles generic planning if software workflow is needed.
3. gsigmad determines whether science governance is required.
4. Ollarma may run bounded local help or manifest execution and emits receipts.
5. Antigence may review risky, contradictory, or promotion-relevant output.
6. gsigmad audits EXP/PROMPT/claim/reproducibility state.
7. Overwatch promotes only approved durable truth.
8. Watchtower projects the state for review.

## What May Be Written

| Writer | Allowed writes |
| --- | --- |
| gsigmad | governance artifacts, EXP/PROMPT/lab notebook entries, adapter contracts |
| Ollarma | local runtime receipts and checkpoints |
| Antigence | review verdict artifacts |
| Watchtower | local projection receipts only |
| Overwatch | approved durable truth |

## What Must Never Be Written Directly

- Canonical KG records from a model response.
- Scientific claim promotions from Ollarma or provider output alone.
- Cross-project task priority from a local runtime.
- ProTHub/Overwatch/SeedGraph writeback outside the approved gate.
- API keys, secrets, or provider credentials in repo files or receipts.

## Minimal Adoption Checklist

A project is bridge-ready when it has:

- `AGENTS.md` or equivalent boundary guidance
- `README.md`
- formal KB surface
- dashboard/operator projection receipt
- `LAB_NOTEBOOK.md` when science work is active
- experiment or run surface when EXP work exists
- workflow/manifest surface for repeatable execution
- adapter registration if Ollarma routing is expected
- gsigmad governance hooks if scientific claims may be produced

## Current Gap

The contracts are implemented in planning and code, but runtimes need this
human-readable surface so Claude Code, ChatGPT Codex, Ollarma, and future
provider lanes follow the same boundaries.
