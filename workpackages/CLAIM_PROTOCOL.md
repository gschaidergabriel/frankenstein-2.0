# Frankenstein 2.0 Workpackage Claim Protocol

Purpose: prevent Triggerword-4 worker stampedes while preserving useful independent falsifiers.

## Stable identity

```text
workpackage_id + generation + claim_id
```

## One mutation authority

For each workpackage there is at most one canonical mutation authority at a time.

Before building or modifying workpackage-owned implementation/state, a worker must create:

```text
workpackages/active/<workpackage_id>.json
```

using a create-only Git operation. The file contains the canonical `workpackage_id`, `generation`, `claim_id`, `worker_id`, `base_commit`, `claimed_scope`, `created_at_utc` and `state`.

If that path already exists, another worker **must not** create a second active mutation authority merely by choosing a new timestamp or incrementing generation.

```text
NEW_WORKER != NEW_GENERATION
NEW_TRIGGER != RETRY_GENERATION
DUPLICATE_ACTIVE_CLAIM != INDEPENDENT_REPLICATION
```

## Parallel workers

A worker that finds an active pointer may:

- inspect and review the active work;
- run an independent test/falsifier;
- prepare a candidate patch in a separate artifact/branch when useful;
- record contradictions or negative evidence.

It must label such work `CANDIDATE_FALSIFIER` or `REVIEW_ONLY` and must not overwrite canonical implementation/state.

For high fan-out runs, parallel workers must also follow `workpackages/CONVERGENCE_PROTOCOL.md`. In particular, normal workers report progress through claim-scoped append-only deltas instead of repeatedly rewriting global state/ledger files. Shared canonical state is fused by one temporary reconciliation writer per fusion window.

## Generation advance

Generation advances only after one of these is durably recorded:

1. terminal failure requiring a deliberate successor implementation;
2. explicit semantic change to the workpackage contract;
3. accepted generation completed and a new successor scope is opened;
4. active claim is proven stale/abandoned and a reconciliation record retires it.

A later clock time, new chat, new Triggerword-4 invocation or another worker is not sufficient.

## Release / completion

The active pointer is never silently deleted. On terminal state, move authority by committing a reconciliation record under:

```text
workpackages/reconciliations/<workpackage_id>/<generation>-<claim_id>.json
```

and update the active pointer state to one of:

`ACCEPTED`, `FAILED_TERMINAL`, `RETIRED_STALE`, `SUPERSEDED`.

A successor generation may then replace the pointer with an explicit parent/reconciliation reference.

When many workers are active, terminal bookkeeping should be fused coherently: active-pointer terminal state, reconciliation record, accepted receipt reference and global ledger/state update should be batched by the reconciliation writer rather than emitted as a chain of competing bookkeeping commits.

## Existing duplicate claims

Claims created before this protocol remain historical evidence. They do not all become canonical. Reconciliation selects at most one mutation authority; other same-generation claims become `CANDIDATE_FALSIFIER` or `SUPERSEDED_DUPLICATE`.

## v2 state transition binding

For current high-fan-out work, claim authority and broad state projection are linked through `workpackages/STATE_CONCURRENCY_PROTOCOL_V2.md`.

The active pointer remains the per-workpackage mutation-authority projection, but a migrated workpackage's broad effective state is established by its append-only state-event chain rather than by whichever worker rewrites `STATE.json` first. Every new state event uses the deterministic next six-digit sequence path and binds the exact active-pointer Git blob; terminal events also bind the exact reconciliation blob.

A Trigger-4 worker and a Trigger-6 worker have equal coordination rank. A stale worker may not manufacture priority by changing generation, timestamp, trigger name or forcing the branch ref. When a mutable active/reconciliation change accompanies an event, they must be committed in one Git tree with refreshed `main` as parent and published by non-force fast-forward only.
