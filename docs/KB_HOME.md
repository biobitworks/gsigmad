# GettingScienceDone Knowledge Base Home

This is the operator-facing index for `gsigmad`, the science-governance layer.
It links existing source surfaces and bridge docs. It is not a new source of
truth.

## Core Surfaces

| Topic | File |
| --- | --- |
| Project overview | `../README.md` |
| Release notes | `../RELEASE.md` |
| Security policy | `../SECURITY.md` |
| Citation | `../CITATION.cff` |
| Governance bridge | `GOVERNANCE_LAYER_BRIDGE.md` |
| Control-plane bridge contract | `CONTROL_PLANE_BRIDGE_CONTRACT.md` |
| Runtime integration matrix | `RUNTIME_INTEGRATION_MATRIX.md` |
| Dashboard receipt | `DASHBOARD.md` |

Live state, roadmap, and the project-local lab notebook are scaffolded
by `gsigmad init` into the consuming repo (under `.gsigmad/`,
`.agent/`, and `LAB_NOTEBOOK.md` respectively) — they are not shipped
with the public package.

## Machine Contracts

| Topic | File |
| --- | --- |
| Control-plane contract | `../src/gsigmad/governance/CONTROL-PLANE-CONTRACT.md` |
| Broker contract | `../src/gsigmad/governance/broker_contract.py` |
| Watchtower projection contract | `../src/gsigmad/governance/operator_surface_contract.py` |
| Antigence review contract | `../src/gsigmad/governance/review_contract.py` |
| Overwatch truth contract | `../src/gsigmad/governance/overwatch_truth_contract.py` |
| Ollarma continuation | `../src/gsigmad/governance/ollarma_continuation.py` |

## Skills

Source skills live in `../skills/gsigmad-*/SKILL.md`. The bridge entrypoint is:

- `../skills/gsigmad-governance-bridge/SKILL.md`

The package-bundled copy is:

- `../src/gsigmad/skill_bundle/skills/gsigmad-governance-bridge/SKILL.md`

## Runtime Adapters

Adapter manifests live under `adapters/*.md` in the consuming repo.
Public release ships a template at `../examples/adapters/example-project.md`;
copy it to `adapters/<your-project>.md` (or `adapters/runtime/<name>.yaml`
for runtime-bridge adapters) to register a project with the framework.
Concrete runtime adapters (e.g. for a bounded local execution lane or
a downstream operator console) are operator-defined and live in the
consuming repo, not in this package.

## Claim Boundary

This repository governs scientific work. It does not make model output
scientific evidence by itself. Claim promotion requires governed EXP/PROMPT,
lab-notebook, audit, and Overwatch promotion paths.
