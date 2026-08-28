# Frankenstein 2.0 — Parallel Worker Convergence Protocol

Purpose: keep high Triggerword-4 fan-out useful without turning shared coordination files into a write hotspot.

## Core rule

Parallel workers may explore, test, falsify and implement in their owned workpackage scope, but they must not all act as global state reconcilers.

```text
MANY_WORKERS -> MANY_APPEND_ONLY_DELTAS
ONE_WORKPACKAGE -> AT_MOST_ONE_MUTATION_AUTHORITY
SHARED_CANONICAL_STATE -> SINGLE_RECONCILIATION_WRITER_PER_FUSION_WINDOW
```

## Hot files

The following are canonical aggregation surfaces and are treated as hot files:

```text
workpackages/STATE.json
checkpoints/CURRENT.json
WORKPACKAGES.md
DONOR_ADOPTION_MATRIX.md
README.md
```

A normal worker MUST NOT rewrite a hot file merely to report its own progress. It records a claim-scoped delta instead. A worker may update a hot file only when it is explicitly performing the reconciliation/fusion step and has refreshed current main immediately before the write.

## Claim-scoped delta

Each material worker result should be recorded append-only under:

```text
workpackages/deltas/<workpackage_id>/<generation>-<claim_id>-<sequence>.json
```

Minimum fields:

```text
schema
workpackage_id
generation
claim_id
worker_id
base_commit
observed_main_commit
owned_paths
result_class
source_commits
receipts
falsifiers
contradictions
proposed_state_change
completion_deficit
next_exact_action
created_at_utc
```

`result_class` is one of:

```text
IMPLEMENTATION_DELTA
TEST_DELTA
FALSIFIER
NEGATIVE_RESULT
REVIEW_ONLY
RECONCILIATION_CANDIDATE
```

A delta is evidence/input. It does not itself mint canonical authority.

## Pre-write convergence barrier

Before every canonical source mutation, the mutation-authority worker must:

1. refresh current `main`;
2. re-read `workpackages/active/<workpackage_id>.json`;
3. inspect newer deltas for the same workpackage/generation;
4. compare the exact owned path set with changes since `base_commit`;
5. if another accepted/canonical implementation already covers the intended semantic delta, stop implementation and convert to `REVIEW_ONLY` or `FALSIFIER`;
6. if paths overlap but semantics differ, do not race-write; emit a reconciliation candidate.

```text
STALE_INTENT + NEW_CANONICAL_EQUIVALENT -> NO_NEW_IMPLEMENTATION
PATH_OVERLAP + DIFFERENT_SEMANTICS -> RECONCILE_BEFORE_WRITE
```

## Fusion windows

Do not commit a chain of bookkeeping-only repairs when one coherent fusion commit can represent the same state.

A reconciliation writer should batch mutually dependent metadata changes into one coherent fusion step when possible:

```text
active pointer terminal state
+ reconciliation record
+ accepted receipt reference
+ canonical state/ledger update
= one fusion transaction / smallest coherent commit set
```

Source/test commits may remain incremental. Pure coordination churn should be batched.

## Dependency rule

A worker must not reopen an accepted dependency just because its own work discovers a downstream integration need. Record the integration deficit on the downstream workpackage unless evidence proves the dependency contract itself is wrong.

```text
DOWNSTREAM_INTEGRATION_GAP != UPSTREAM_REOPEN
```

## Reconciliation writer

The reconciliation writer is temporary and scoped to one fusion window. It is not a new persistent entity or authority class. Its job is only to:

- consume worker deltas;
- select the canonical survivor;
- preserve unique falsifiers/negative evidence;
- retire duplicate implementation authorities;
- update hot files once;
- leave an exact next action.

After fusion, ordinary workers return to claim-scoped work.

## Success criterion

The protocol is working when additional Triggerword-4 workers increase independent tests, falsifiers and non-overlapping implementation progress without proportionally increasing:

- `restore` / `repair` / `rebind` coordination commits;
- duplicate adapters;
- repeated state-pointer rewrites;
- stale claim resurrection;
- duplicate dispatches.
