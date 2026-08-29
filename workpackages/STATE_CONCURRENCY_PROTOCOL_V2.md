# Frankenstein 2.0 — Workpackage State Concurrency Protocol v2

Status: CANONICAL CONCURRENCY SUCCESSOR FOR HIGH-FAN-OUT STATE PROJECTION

## Why v2 exists

`workpackages/active/<id>.json` and `workpackages/STATE.json` were both being used as mutable state views. Under parallel Trigger-4/Trigger-6 work this allowed one view to land before the other. WP707-G2 demonstrated the failure: the terminal active pointer existed while the global STATE snapshot did not yet contain WP707.

That state is no longer modeled as two competing truths.

## Authority split

```text
per-WP append-only state event = canonical state-transition evidence
active/<id>.json               = mutation-authority projection
STATE.json                     = global materialized snapshot / cache
reconciliation                 = terminal claim-generation evidence
```

`STATE.json` is no longer required to be synchronously rewritten for every workpackage transition. A stale snapshot is `PROJECTION_STALE`, not a second authority. Consumers requiring current state MUST resolve the snapshot through admitted `workpackages/state_events/` using `tools/resolve_workpackage_state_v2.py`.

## Event path and single-successor rule

Events are append-only and use a deterministic sequence path:

```text
workpackages/state_events/<workpackage_id>/<six-digit-sequence>.json
```

For one workpackage, the next sequence number is unique. Two workers attempting the same successor therefore contend for the same create-only path rather than creating two independently valid heads.

Every event binds:

- workpackage id and sequence;
- previous event path and previous event content SHA-256, or `null` for sequence 1;
- the F2 main SHA observed before the transition/event is proposed;
- claim generation and claim id;
- effective broad status, phase, title and evidence refs;
- active-pointer state and exact active-pointer Git blob SHA;
- reconciliation ref/blob SHA for terminal states;
- explicit zero-credit boundaries.

A missing sequence, mismatched parent, duplicate semantic head, stale bound pointer, or stale reconciliation fails closed.

## Git CAS rule

When an event is created together with a mutable per-WP projection change, the reconciliation writer MUST use one Git tree/commit and update `main` by non-force fast-forward only.

```text
REFRESH main
→ read current event head + active pointer + relevant reconciliation
→ build one tree containing event + projection changes
→ create commit with refreshed main as its only parent
→ update main with force=false
```

If `main` moved, the ref update loses the compare-and-swap race. The worker MUST NOT force-push or replay the stale tree. It refreshes, re-evaluates the new event head and either rebases semantically or becomes `REVIEW_ONLY` / `CANDIDATE_FALSIFIER`.

```text
STALE_PARENT + FAILED_FAST_FORWARD != RETRY_WITH_FORCE
TRIGGER4 != PRIORITY_OVER_TRIGGER6
TRIGGER6 != PRIORITY_OVER_TRIGGER4
FIRST_VALID_CAS_COMMIT != AUTOMATIC_SEMANTIC_WIN_IF_NEW_EVIDENCE_FALSIFIES_IT
```

## Global STATE compaction

`workpackages/STATE.json` is a materialized compatibility snapshot. Only a reconciliation/compaction writer should refresh it. Compaction is deterministic: load the snapshot, validate all event chains, then overlay the latest event row for each migrated workpackage.

No normal worker should write `STATE.json` merely to announce progress. This removes the global file from the per-WP critical path and lets unrelated workpackages advance concurrently.

## Migration rule

Migration is incremental:

- workpackages with no state-event chain continue to resolve from legacy `STATE.json`;
- once a valid event exists for a workpackage, that event chain is the current effective state authority for that row;
- an event may bind pre-v2 accepted evidence without rewriting the historical receipt/reconciliation;
- historical files remain immutable evidence and are not silently edited to satisfy the new contract.

## Required validation

`tools/resolve_workpackage_state_v2.py --check-active` validates migrated event chains and their current active/reconciliation bindings. CI must run it on every change to state events, active pointers, reconciliations, the global snapshot, or the resolver itself.

The legacy v1 validator remains useful for non-migrated rows, but it is not sufficient for high-parallelism synchronization because it only observes a finished checkout.

## Branch enforcement boundary

Repository-local protocol and CI can reject inconsistent commits, but GitHub branch protection/rulesets are the external enforcement boundary for preventing an uncooperative direct push from bypassing required checks. Until a required status rule is enabled, participating Trigger-4/Trigger-6 workers MUST treat the v2 resolver as fail-closed pre-write/pre-merge policy.

## Invariants

```text
STATE_SNAPSHOT_STALE != CANONICAL_CONTRADICTION
EVENT_CHAIN_BRANCH_OR_GAP -> FAIL_CLOSED
ACTIVE_POINTER_BLOB_MISMATCH -> FAIL_CLOSED
TERMINAL_EVENT_WITHOUT_BOUND_RECONCILIATION -> FAIL_CLOSED
GLOBAL_STATE_WRITE_PER_WORKER -> FORBIDDEN
UNRELATED_WORKPACKAGES -> NO_SHARED_STATE_WRITE_LOCK
SAME_WORKPACKAGE_SUCCESSOR -> CREATE_ONLY_FIXED_SEQUENCE + GIT_CAS
FORCE_PUSH_TO_WIN_RACE -> FORBIDDEN
```
