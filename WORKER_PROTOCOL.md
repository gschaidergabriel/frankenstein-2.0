# Frankenstein 2.0 — Triggerword-4 Worker Protocol

Every Triggerword-4 worker doing Frankenstein-2.0 assembly must treat this repository as the canonical build/evidence home.

## Required cycle

```text
REFRESH
→ SELECT/CLAIM WORKPACKAGE + GENERATION
→ INSPECT DONOR/DEPENDENCIES
→ BUILD SMALLEST COHERENT STEP
→ TEST
→ MEASURE + TRACE
→ RECORD NEGATIVE RESULTS / BUGS / HYPOTHESES
→ COMMIT
→ UPDATE WORKPACKAGE STATE
→ WRITE CHECKPOINT + next_exact_action
```

## Commit law

Commit coherent steps, not one giant final dump. Typical progression:

```text
F2-WP-403: claim NeRD projection generation 2
F2-WP-403: import bounded donor primitives
F2-WP-403: add physical plausibility cases
F2-WP-403: archive lesion benchmark
F2-WP-403: accept projection adapter scope
```

A worker step is not finished if the only surviving evidence is chat text, terminal output or an uncommitted workspace.

## Concurrency

Stable work identity:

```text
workpackage_id + generation + claim_id
```

Before every write:

1. refresh current `main`;
2. inspect `workpackages/STATE.json` and `checkpoints/CURRENT.json`;
3. detect overlapping/newer claims;
4. never overwrite a newer accepted generation with stale state;
5. if overlap is useful as an independent falsifier, label it explicitly rather than pretending it is independent by default.

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
commands/tests
started_at / finished_at
exit status
metrics paths
trace paths
system-log package path
communication-log slice
GRID10-log slice
hypothesis IDs
bug IDs
negative-result paths
acceptance scope
completion deficit
next_exact_action
```

## Evidence law

```text
SOURCE_PRESENCE != RUNTIME_PASS
QUEUED_JOB != EXECUTION
MODEL_CONSENSUS != EVIDENCE
SIMULATION_PASS != WORLD_PASS
SYMPTOM_GONE != ROOT_CAUSE_FIXED
COMPONENT_PASS != WHOLE_SYSTEM_PASS
```

A workpackage receives `[x]` only when its exact acceptance evidence is archived in this repository.

## Donor law

`gschaidergabriel/frankenstein` is the current primary Frankenstein donor and remains read-only during F2 assembly unless a separate explicit task changes it.

Historical Project-Frankenstein/Agent-Zero/other repos may be read when exact provenance is needed, but a Triggerword-4 build step returns to this repository and materializes the selected successor here.

## Telemetry law

All system components participating in a test must either emit/route telemetry or be declared `NOT_OBSERVABLE` in the test manifest. Every test series gets an immutable package under `runs/<series>/<run_id>/`.

GRID10 logs, all internal latency spans, resource/performance measurements, communications, hypotheses/counterhypotheses and bug/root-cause states are first-class experiment data.

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

The canonical `gschaidergabriel/frankenstein-2.0` repository now exists. From this point forward, Triggerword-4 assembly is **F2-repository-first**.

Research-Entity, controller, VPS and historical repositories remain valid donor/evidence/execution surfaces, but they are not the canonical product state. A useful result produced elsewhere must be materialized here as source, test, measurement, receipt, provenance record or explicitly linked external evidence before it earns Frankenstein-2.0 build credit.

Queued or unavailable self-hosted runner gates are side-fronts unless the selected workpackage truly depends on them. In particular:

```text
QUEUED_RUNNER_GATE != BLOCKED_FRANKENSTEIN2_PROJECT
OLD_ENTITYOS_HCU_P0 != AUTOMATIC_F2_GLOBAL_P0
RESEARCH_STAGING_PROGRESS != F2_IMPLEMENTATION_PROGRESS
```

Required behavior while a runner-dependent discriminator is nonterminal:

1. preserve the existing singleton/claim and do not stampede duplicate dispatches;
2. record the exact blocked discriminator and required runtime receipt;
3. continue independent Frankenstein-2.0 workpackages in this repository;
4. prioritize evidence/data spine, causal identity, donor migration, GRID/GWT interfaces, memory, world-model, child ABI, Retina/Voice and cognitive-test work that can proceed without that runner;
5. consume the runner result when it becomes terminal and then update only the workpackages whose acceptance actually depends on it.

A stale external supervisor state written before the canonical F2 repository existed must not override this repository's current `workpackages/STATE.json`, README, checkpoints or accepted evidence.
