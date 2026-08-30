# Frankenstein 2.0 — Triggerword-4 Worker Protocol

Every Triggerword-4 worker doing Frankenstein-2.0 assembly must treat this repository as the canonical build/evidence home.

## Mandatory current execution authority

Before selecting or deferring any executable test, every worker MUST read:

1. `workpackages/RUNTIME_CREDIT_CONVERGENCE_DIRECTIVE.md`
2. `workpackages/VPS_SANDBOX_EXECUTION_AUTHORITY.md`
3. `workpackages/STATE_CONCURRENCY_PROTOCOL_V2.md` when the selected workpackage is migrated to event-sourced state
4. `workpackages/CLAIM_PROTOCOL.md` and `workpackages/CONVERGENCE_PROTOCOL.md` as required by the selected claim
5. `PRODUCT_COMPLETION_LAW.md` for completion-scope questions

The current owner execution rule is **VPS SANDBOX FIRST**.

For every test that can be faithfully represented in the owner-provisioned Ubuntu VPS sandbox / `clay-direct-dev`, execute it there before asking for or deferring to the owner's physical workstation.

The local workstation is a final **physical evidence** surface, not the normal development sandbox.

Before a worker writes `needs local-machine test`, it MUST classify the missing invariant as exactly one of:

```text
VPS_SANDBOX_REPRESENTABLE
PHYSICAL_LOCAL_ONLY
UNKNOWN_FIDELITY
```

Required behavior:

```text
VPS_SANDBOX_REPRESENTABLE -> execute in VPS sandbox now
PHYSICAL_LOCAL_ONLY       -> preserve exact physical reason and defer only that scope
UNKNOWN_FIDELITY          -> improve/measure sandbox fidelity first; do not default to local
```

Every `PHYSICAL_LOCAL_ONLY` classification must name the exact property the VPS Ubuntu sandbox cannot reproduce.

Inside a positively identified disposable sandbox, workers have broad authority to mutate, corrupt, wipe, reinstall, restart, crash, fuzz, stress and otherwise destroy **sandbox-local** state as necessary for high-information testing. They must preserve the owner host, canonical repositories, credentials, SSH/control access and unrelated persistent data as required by `VPS_SANDBOX_EXECUTION_AUTHORITY.md`.

Sandbox success earns only the exact VPS/target-like scope actually executed. It does not automatically earn physical-device, physical-workstation or whole-product credit.

## Provider / coding-agent route

Owner-authorized exception: **GLM-5.3-Flash may be used as an alternative coding/test agent when Claude Code is unavailable or an API-backed coding agent is useful.**

Credentials MUST come from a secret/environment boundary. Never commit, print, echo, copy into prompts, shell history, logs, receipts, test fixtures, artifacts or repository files any provider token.

Together remains forbidden unless a later explicit owner directive changes that. The old autonomous Free-Swarm remains disabled. GLM work is an `ORGAN_NOT_ENTITY` and must pass the same source/test/evidence gates as Claude/GPT/Codex work.

## Active owner convergence priority

Current default work-selection order is:

```text
RUNTIME_CREDIT_CLOSURE
> INTEGRATION_BLOCKER
> EVIDENCE_RECONCILIATION
> NEW_COMPONENT
```

An unclaimed component is **not** automatically useful work. A `NEW_COMPONENT` claim must name the concrete open integration/runtime gate it closes and explain why wiring, adapting, testing or repairing existing machinery cannot close that gate first.

Workers should treat lower-tier accepted/source-ready components with zero higher-tier runtime credit as an integration-debt priority signal, not as failed components and not as permission to relabel evidence.

## Required cycle

```text
REFRESH
-> RESOLVE CURRENT EVENT/CLAIM AUTHORITY
-> CLASSIFY RUNTIME-CREDIT / INTEGRATION / RECONCILIATION / NEW-COMPONENT WORK
-> SELECT/CLAIM WORKPACKAGE + GENERATION
-> NAME TARGET COMPLETION TIER + INTEGRATION BOUNDARY
-> CLASSIFY EXECUTION SURFACE: VPS_SANDBOX_REPRESENTABLE / PHYSICAL_LOCAL_ONLY / UNKNOWN_FIDELITY
-> INSPECT DONOR/DEPENDENCIES + ACTIVE RESEARCH PACKETS
-> INSPECT NEWER CLAIM-SCOPED DELTAS / OVERLAP
-> FUSE EXISTING ACCEPTED/SOURCE-READY PARTS FIRST
-> BUILD SMALLEST COHERENT MISSING STEP ONLY IF REQUIRED
-> EXECUTE HIGHEST-INFORMATION AUTHORIZED TEST, VPS SANDBOX FIRST WHERE REPRESENTABLE
-> MEASURE + TRACE + READ BACK
-> CLASSIFY FAILURES
-> RECORD NEGATIVE RESULTS / BUGS / HYPOTHESES
-> COMMIT OWNED SOURCE/TEST/EVIDENCE
-> EMIT CLAIM-SCOPED DELTA
-> APPEND/RECONCILE STATE THROUGH CURRENT PROTOCOL
-> next_exact_action
```

Normal workers do not repeatedly rewrite shared canonical ledgers merely to announce progress.

## Event-first state reentry

For migrated workpackages, current state resolution is event-first:

```text
refresh main
-> resolve workpackages/state_events/<WP>/ valid head
-> inspect workpackages/active/<WP>.json
-> inspect terminal reconciliation / runtime receipt
-> inspect newest claim-scoped deltas
-> only then consult workpackages/STATE.json / checkpoints/CURRENT.json as projections
```

A stale `STATE.json` or `CURRENT.json` is `PROJECTION_STALE`, not permission to overwrite newer event authority.

## Concurrency and mutation authority

Stable work identity:

```text
workpackage_id + generation + claim_id
```

A claim file under `workpackages/claims/` is historical/work evidence; by itself it is **not** mutation authority.

Before mutating workpackage-owned canonical source/state, the worker must own or validly inherit:

```text
workpackages/active/<workpackage_id>.json
```

There may be at most one active mutation pointer per workpackage.

```text
NEW_WORKER != NEW_GENERATION
NEW_TRIGGER != RETRY_GENERATION
CLAIM_FILE != MUTATION_AUTHORITY
ONE_WORKPACKAGE -> AT_MOST_ONE_ACTIVE_MUTATION_POINTER
```

If equivalent canonical work already landed, stop duplicate implementation and convert useful overlap to `REVIEW_ONLY` / `CANDIDATE_FALSIFIER`.

For event-sourced successors, use create-only event paths and non-force Git CAS/fast-forward semantics. A race loser refreshes and re-evaluates. Never force-push merely to win a state race.

## Runtime-subject churn fence

If an exact-source higher-tier runtime probe is already bound, dispatched, queued, assigned or otherwise materially tied to a concrete subject, classify before changing that same semantic boundary:

```text
RUNTIME_SUBJECT_INVARIANT
RUNTIME_PROBE_INVALIDATED_BY_REQUIRED_REPAIR
DEFER_UNTIL_RUNTIME_RESULT
```

Do not create a newer semantic subject merely because another worker is idle. A later runtime PASS for an older subject plus newer repository CI cannot be composed into current-generation runtime credit without explicit semantic-invariance evidence.

## Failure classification

Before architecture repair, classify a failed/nonterminal discriminator as exactly one primary class:

```text
PRODUCT_NEGATIVE
EVIDENCE_INVALID
INFRA_AUTH_TRANSPORT_QUOTA
CONCURRENCY_RETRY
UNKNOWN_NONTERMINAL
```

Examples:

- exact executed assertion/regression failure -> `PRODUCT_NEGATIVE`
- wrong/unbound/fake/dry-run subject -> `EVIDENCE_INVALID`
- runner/auth/transport/quota/host-health guard -> `INFRA_AUTH_TRANSPORT_QUOTA`
- failed fast-forward / legitimate claim race -> `CONCURRENCY_RETRY`
- queued/pending/zero-step unresolved run -> `UNKNOWN_NONTERMINAL`

Infrastructure failure is not product evidence.

## Required receipt fields

Each material run should preserve:

```text
run_id
workpackage_id
generation
claim_id
worker_id
source_commit_before
source_commit_after
donor_source_refs
environment/runtime identity
execution_surface_class
sandbox_identity/reset_path when sandboxed
resource/host-health limits when relevant
commands/tests
started_at / finished_at
exit status
metrics paths
trace paths
actual executed steps
result/readback
system-log package path
communication-log slice
GRID10-log slice
hypothesis IDs
bug IDs
negative-result paths
failure_class
acceptance scope
explicit zero-credit boundaries
completion deficit
next_exact_action
```

## Evidence law

```text
SOURCE_PRESENCE != RUNTIME_PASS
QUEUED_JOB != EXECUTION
MODEL_CONSENSUS != EVIDENCE
SIMULATION_PASS != WORLD_PASS
VPS_SANDBOX_PASS != PHYSICAL_LOCAL_PASS
SYMPTOM_GONE != ROOT_CAUSE_FIXED
COMPONENT_PASS != WHOLE_SYSTEM_PASS
```

A workpackage receives acceptance only when its exact evidence is archived/bound under current protocol.

## Commit law

Commit coherent causal steps, not one giant final dump and not bookkeeping-only chains where one atomic fusion commit is sufficient.

A worker step is not finished if the only surviving evidence is chat text, terminal output or an uncommitted workspace.

## Donor law

`gschaidergabriel/frankenstein` is the current primary Frankenstein donor and remains read-only during F2 assembly unless a separate explicit task changes it.

Historical Project-Frankenstein/Agent-Zero/other repos may be read when exact provenance is needed, but a Triggerword-4 build step returns to this repository and materializes the selected successor here.

## Telemetry law

All system components participating in a test must either emit/route telemetry or be declared `NOT_OBSERVABLE` in the test manifest. Every test series gets an immutable package under `runs/<series>/<run_id>/` or the current admitted receipt path.

GRID10 logs, latency spans, resource/performance measurements, communications, hypotheses/counterhypotheses and bug/root-cause states are first-class experiment data.

## Bug closure law

A bug may not be marked `FIXED` unless all are present:

```text
confirmed root cause
root-cause evidence
fix commit
regression test
regression receipt
```

Patching around a symptom remains `FIX_CANDIDATE` or `REGRESSION_PENDING`.

## Canonical-build priority after repository materialization

Triggerword-4 assembly is **F2-repository-first**. Research-Entity, controller, VPS and historical repositories remain valid donor/evidence/execution surfaces, but canonical F2 product state materializes here.

A useful result produced elsewhere must be materialized here as source, test, measurement, receipt, provenance record or explicitly linked external evidence before it earns F2 build credit.

A nonterminal runner-dependent discriminator does not block independent work on a different named runtime-credit/integration/reconciliation boundary, but workers must not stampede duplicate dispatches.

## Current execution shorthand

```text
CAN_IT_BE_TESTED_FAITHFULLY_IN_UBUNTU_VPS_SANDBOX?
    YES -> TEST IT THERE NOW.
    NO  -> NAME THE EXACT PHYSICAL-LOCAL PROPERTY.
    UNSURE -> IMPROVE/MEASURE SANDBOX FIDELITY FIRST.
```

Preferred convergence flow:

```text
accepted exact source/artifact
-> fresh target-like Ubuntu VPS sandbox
-> install/run/falsify
-> crash/restart/readback as relevant
-> exact receipt
-> only measured credit
-> next dependency-correct boundary
-> physical local machine only for irreducible final physical evidence
```
