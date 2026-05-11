# Control Plane Bridge Contract

This is the human-readable companion to the machine contracts under
`src/gsigmad/governance/`.

## Owner Matrix

| Owner | Durable role | Live role | Writes |
| --- | --- | --- | --- |
| gsigmad | science governance, receipt vocabulary, EXP/PROMPT/lab notebook rules | workflow gatekeeper | governance artifacts only |
| Ollarma | bounded runtime evidence | local model routing and execution | `.ollarma/` receipts/checkpoints |
| Watchtower | none | operator projection | no sibling-repo truth writes |
| Antigence | review verdict evidence | risk/escalation review | verdict artifacts |
| Overwatch | canonical portfolio truth | ingestion/promotion control | approved durable truth |
| SeedGraph | graph/evidence structures as adopted | downstream evidence consumer | governed graph artifacts only |
| Claude Code / ChatGPT Codex | none by default | agent runtimes | repo edits only under local approval |
| Gemini / Grok | none by default | future provider/runtime lanes | no direct writes |

## Live vs Durable

Live events are useful for operation but not automatically canonical. Durable
truth requires an accepted artifact class.

| Live event | Durable only when |
| --- | --- |
| chat response | converted into a governed receipt or human decision |
| Ollarma route | receipt is validated and ingested |
| Ollarma workflow | manifest, receipt chain, and validation pass |
| Antigence verdict | structured review artifact is accepted |
| model disagreement | disagreement receipt is routed for review |
| human approval | explicit `HumanDecision` artifact exists |

## Receipt and Lease Rules

- One task claim has one bounded owner at a time.
- Leases expire without implicit re-claim.
- Lane finish receipts report outputs; they do not promote truth.
- Disagreement receipts trigger review; Ollarma does not arbitrate.
- Synthesis receipts require an explicit upstream request.
- Claim promotion requires gsigmad and Overwatch gates.

## Provider Rules

OpenAI, Anthropic, Gemini, Grok, or any future provider may participate only as
a receipt-bearing lane. Provider output is never a direct writeback path.

## Writeback Rules

No runtime writes to:

- Overwatch truth stores
- SeedGraph KG
- ProTHub
- ArangoDB
- project canon files

unless the owning governance path explicitly authorizes the mutation.
