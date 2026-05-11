# GettingScienceDone Dashboard Surface

GettingScienceDone does not host a standalone web dashboard. Its operator
projection is Watchtower, and its runtime bridge is Ollarma.

This file exists as the dashboard/review receipt that Watchtower can discover.
It points at the source surfaces rather than inventing a second UI.

## Operator Projection

| Surface | Owner | Path |
| --- | --- | --- |
| Portfolio operator view | Watchtower | `<watchtower-repo>` |
| Governance bridge docs | gsigmad | `docs/GOVERNANCE_LAYER_BRIDGE.md` |
| Control-plane contract | gsigmad | `docs/CONTROL_PLANE_BRIDGE_CONTRACT.md` |
| Runtime integration matrix | gsigmad | `docs/RUNTIME_INTEGRATION_MATRIX.md` |
| MCP tools | gsigmad | `src/gsigmad/mcp_server.py` |
| Ollarma adapter | gsigmad | `adapters/runtime/ollarma.yaml` |
| Bridge skill | gsigmad | `skills/gsigmad-governance-bridge/SKILL.md` |

## Watchtower Mapping

When Watchtower is running, the review matrix should see:

- docs: `docs/`
- KB: `docs/KB_HOME.md`
- dashboard: `docs/DASHBOARD.md`
- lab notebook: `LAB_NOTEBOOK.md`
- experiments: `experiments/`
- workflows: `.planning/ROADMAP.md`

## Boundary

Watchtower may display gsigmad status, docs, bridge surfaces, and readiness
gaps. It must not become the governance owner. Runtime execution remains
Ollarma's responsibility; durable truth remains Overwatch's responsibility.
