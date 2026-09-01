# F2-WP-002 — Machine-State Consistency Contract

This contract defines the minimum deterministic invariants for the machine-readable workpackage state/claim/generation surface.

## Current authority split

State Concurrency Protocol v2 is the successor authority for any workpackage that has a valid append-only state-event chain:

- `workpackages/state_events/<id>/<sequence>.json` = canonical state-transition evidence for migrated rows;
- `workpackages/active/<id>.json` = mutation-authority projection;
- `workpackages/STATE.json` = global materialized compatibility snapshot/cache;
- reconciliation = terminal claim-generation evidence;
- `tools/resolve_workpackage_state_v2.py --check-active` = required resolver/binding validation.

Migration is successor-dynamic, never hardcoded. Once a valid event chain exists for a workpackage, its latest validated event overrides the corresponding `STATE.json` cache row. A stale cache row is `PROJECTION_STALE`, not a competing truth and not by itself a reason for a normal worker to rewrite the global snapshot. If v2 validation fails, validation fails closed; consumers must not silently fall back to the legacy row.

For a workpackage with **no** valid state-event chain, the legacy v1 rules below remain authoritative.

## Legacy v1 objects

Required files for a non-migrated active generation:

- `workpackages/STATE.json`
- `workpackages/active/F2-WP-XXX.json`
- matching `workpackages/claims/*.json` object selected by exact `claim_id`

An ACTIVE pointer identifies the sole mutation authority for that workpackage. Terminal state requires explicit matching reconciliation evidence.

## Legacy v1 invariants for non-migrated rows

1. The active-pointer filename workpackage ID equals its `workpackage_id`.
2. The active pointer has a positive integer `generation` and non-empty `claim_id`.
3. The active pointer's `claim_id`, `generation`, `worker_id` where present, and `workpackage_id` agree with the selected claim object.
4. `workpackages/STATE.json` contains the same non-migrated workpackage and reports a status consistent with the active claim/reconciliation.
5. An ACTIVE pointer must project a nonterminal broad status.
6. A terminal accepted workpackage requires matching reconciliation evidence and explicit zero whole-system credit/acceptance.
7. Generation and claim identity are not inferred from timestamps, filename proximity, or nearby commits.
8. Validation is fail-closed: malformed JSON, missing required legacy files, mismatched identities, unsupported statuses, or absent terminal evidence are errors.

## v2 invariants for migrated rows

1. Event sequence starts at `000001.json` and is contiguous.
2. Every successor binds the previous event path and content SHA-256.
3. The latest event binds the exact current active-pointer Git blob, claim generation/id, active-pointer state, broad status, phase, title, and evidence refs.
4. A terminal event additionally binds the exact reconciliation ref/blob.
5. Missing sequence, stale pointer/reconciliation blob, wrong generation/claim/state, or malformed event fails closed.
6. `STATE.json` may lag the validated event head; it is not synchronously repaired by ordinary Trigger-4/Trigger-6 workers.
7. Global snapshot compaction is a separate reconciliation/compaction responsibility under `STATE_CONCURRENCY_PROTOCOL_V2.md`.

## Credit boundary

Machine-state consistency proves only source/continuity metadata coherence. It grants **zero** provider, VPS, perception, GRID10, HCU, GWT/J-Space, training, effect, completion, or whole-system runtime credit.
