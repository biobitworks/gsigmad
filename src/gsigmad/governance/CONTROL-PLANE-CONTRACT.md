# Control-Plane Contract: Phase 32

**Version:** 1.0  
**Scope:** Cross-project control plane for `gsigmad`, Watchtower, Ollarma, Antigence, and Overwatch.

## Comparison Frame

Use one decision frame only:

- `adopt` for patterns that fit the frozen portfolio contract.
- `adapt` for patterns that are useful only after removing planner, queue, or truth ownership.
- `reject` for any pattern that introduces a second planner, shadow queue, duplicated owner, or Watchtower writeback.

Adjacent systems such as Temporal, Airflow, Argo, LangGraph, CrewAI, Backstage, DataHub, MLflow, and OpenLineage are pattern sources only.

## Canonical Ownership Matrix

| Surface | Owner | Write policy |
|---|---|---|
| Planning ontology | `gsigmad` | authoritative |
| Operator view | `watchtower` | projection-only |
| Swarm broker | `ollarma` | execution-boundary |
| Review escalation | `antigence` | review-authority |
| Durable truth | `overwatch` | durable-truth |

The ownership matrix is closed. No surface may be reassigned to a second owner.

## Closed Entity Set

`Project`, `Milestone`, `Phase`, `Plan`, `Wave`, `Task`, `NextStep`, `WorkLease`, `SwarmRun`, `LaneRun`, `Run`, `StageReceipt`, `OffloadRequest`, `OffloadReceipt`, `SidecarReviewBundle`, `EscalationBundle`, `ReviewVerdict`, `HumanDecision`, `ReplayRun`, `ResumeCursor`, `ReverificationReceipt`, `BlockedLifecycleEvent`, `DeadLetterReceipt`, `Artifact`, `Claim`, `Resource`, `Dependency`, `Actor`, `BoundarySurface`, `KGIngestionReceipt`

## Closed Edge Set

`contains`, `planned_by`, `depends_on`, `requires_receipt`, `executed_in`, `has_lane`, `produced`, `generated_by`, `derived_from`, `reviewed_by`, `escalated_to`, `approved_by`, `gates`, `blocks`, `resolves`, `supersedes`, `corrects`, `replays`, `resumes_from`, `claims_about`, `cites`, `attached_to`, `surfaced_in`, `leased_by`, `owned_by`, `ingested_as`

## Durable Receipts

`StageReceipt`, `LeaseReceipt`, `SwarmRunReceipt`, `LaneRunReceipt`, `ReviewVerdict`, `HumanDecision`, `ReplayIdentity`, `ReverificationReceipt`, `BlockedLifecycleEvent`, `DeadLetterReceipt`, `KGIngestionReceipt`

Durable receipts are append-only, schema-versioned, hashable, and eligible for Overwatch ingestion. Live events are not canonical truth by default.

## Live Events

`heartbeat`, `progress-tick`, `ui-cache-update`, `health-poll`, `provider-stream-event`, `queue-internal`

Live events remain repo-local or system-local evidence unless promoted through a durable receipt.

## Repo Adoption Classes

- `active`: full v2.1 participant that can emit or consume canonical receipts.
- `legacy`: compatibility participant with read-first routing.
- `frozen`: read-only exemplar input and contract consumer.

Frozen repos must not declare executable command modes, second planners, or mutation expectations.

## Lease Authority

Lease payloads must carry:

- `lease_id`
- `task_id`
- `lease_scope`
- `holder_system`
- `holder_id`
- `fencing_token`
- `acquired_at`
- `expires_at`
- `heartbeat_at`
- `intent_summary`
- `allowed_outputs`
- `release_policy`

Release reasons are closed to:

`completed`, `blocked`, `escalated`, `abandoned`, `timeout`, `superseded`

Lease authority must not be expressed through a second queue or duplicate ownership field.

## Guardrails

- Reject any second planner.
- Reject any shadow queue.
- Reject any duplicate durable owner.
- Reject Watchtower writeback into canonical truth.
- Reject frozen-repo mutation expectations.

## Machine-Readable Companion

The companion module is `src/gsigmad/governance/control_plane_contract.py`. It exposes the closed enum sets, ownership matrix, repo adoption classes, lease release reasons, and guardrail validators used by later runtime and projection code.
