# Runtime Integration Matrix

| Runtime | Current status | Entry surface | Boundary |
| --- | --- | --- | --- |
| Claude Code | supported | `~/.claude/skills/gsigmad-*`, repo `CLAUDE.md`, MCP tools | must follow repo governance and actual runtime identity |
| ChatGPT Codex | supported | `~/.codex/skills/gsigmad-*`, repo `AGENTS.md`, MCP tools | must follow same `SKILL.md` sources |
| Ollarma | supported as bridge/runtime | `gsigmad_ollarma_continuation`, runtime adapter, receipts | bounded executor only |
| Ollama | supported as local model backend | called by Ollarma or scripts | no governance authority |
| Gemini | future | Agent Skills-compatible surface, provider receipt | no direct writeback |
| Grok | future | Agent Skills-compatible surface, provider receipt | no direct writeback |

## Skill Parity Rule

The source of truth for science skills is `skills/gsigmad-*/SKILL.md`.
Runtime-specific installs should mirror those files instead of editing local
copies by hand.

## Runtime Identity Rule

Skill-generated signatures, handoffs, citations, and session records should use
the actual runtime/model identity. Do not hardcode `Claude Code` or `Codex` when
the same skill may run under another Agent Skills-compatible runtime.

## Provider Rule

Future provider adapters enter through explicit receipt-bearing contracts. They
may answer, review, or propose; they may not promote durable truth.
