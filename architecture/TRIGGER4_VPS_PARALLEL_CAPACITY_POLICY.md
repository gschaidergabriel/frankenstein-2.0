# Trigger-4 VPS Parallel Capacity Policy

Status: ACTIVE ARCHITECTURE / EXECUTION POLICY
Owner direction: 2026-08-29
Applies to: exact `4`, `triggerword 4`, `triggerwort 4`

## Purpose

Trigger-4 engineering is allowed to use substantial VPS compute for parallel build, test, benchmark, falsification and measurement work. The goal is high engineering throughput and strong evidence without destabilizing the server.

Trigger-4 does not merely prepare concepts for later local implementation. It is expected to drive Frankenstein 2.0 as far toward a reproducible release candidate as the VPS/bridge environment can honestly prove, leaving the final local Claude Code/Opus lane primarily real-host/device/permission binding and physical acceptance.

See `architecture/VPS_BUILD_TO_LOCAL_ACCEPTANCE_CONTRACT.md`.

## Shared 70% envelope

The owner authorizes coordinated Trigger-4 work to use up to approximately **70% of current usable VPS compute capacity** when useful.

This is a shared machine-wide ceiling:

```text
SUM(TRIGGER4_ADMITTED_LOAD) <= 70% OF CURRENT USABLE VPS COMPUTE CAPACITY
```

It is not a per-worker allowance and it is not a requirement to reach 70%. Use lower load when additional parallelism has little value.

The remaining headroom protects the OS, database/WAL, runners/bridges, coordination/control plane, telemetry/evidence writes and recovery.

## One capacity authority

Parallel workers must be centrally coordinated through one shared capacity view. Use leases, tokens, reservations or an equivalent bounded admission mechanism; do not let each worker independently decide how much machine capacity remains.

Before increasing concurrency, account for:

- active jobs and their claim/work identities;
- current CPU/compute utilization and runnable pressure;
- available RAM and memory pressure;
- swap/OOM indicators;
- disk and DB/WAL I/O pressure;
- runner/bridge health;
- heartbeat/control-loop/DB latency or jitter;
- mutable-path/workpackage/effect conflicts;
- expected peak resource footprint of candidate jobs.

`MANY_TEST_WORKERS -> ONE_SHARED_CAPACITY_BUDGET -> BOUNDED_PARALLELISM`

## Progressive ramp

Prefer measured ramp-up rather than an immediate fan-out. A useful default is:

```text
PRECHECK -> ~40% -> OBSERVE -> ~55% -> OBSERVE -> <=70%
```

Intermediate levels are heuristics. The hard concept is progressive admission with telemetry and backpressure.

## Backpressure / abort conditions

Throttle, stop admitting work, serialize, or terminate expendable tests when the machine shows material instability, including:

- aggregate compute approaching/exceeding the shared 70% ceiling;
- meaningful memory pressure, falling available RAM, swap growth or OOM evidence;
- severe disk I/O queueing or DB/WAL stalls/contention;
- material runner, heartbeat, DB or control-loop latency/jitter degradation;
- repeated process crashes or host/service instability;
- a higher-priority recovery/control/evidence-preservation task requiring reserve.

The safe limit is determined by the first constraining resource. A memory- or I/O-heavy test matrix may need far less than 70% CPU concurrency.

## Parallelism admission

Prefer parallel execution for independent/read-only/isolated workloads such as:

- independent test shards;
- isolated sandboxes;
- read-only benchmarks;
- matched A/B jobs;
- bounded fuzz/property-test shards;
- explicitly instrumented load/concurrency tests.

Serialize or isolate work sharing destructive fixtures, mutable canonical state, exclusive schema/DB operations, deployment authority, effect identity or canonical workpackage mutation unless that concurrency is itself the explicit falsifier and recovery/rollback is proven.

Claim and mutation ownership rules remain unchanged.

## Engineering-to-release obligation

The VPS is the main Frankenstein-2.0 construction and integration workshop. Before handing a package to the final local acceptance lane, Trigger-4 engineering should complete every non-physical layer that can be implemented and falsified without the user's exact devices/OS permissions.

This includes, as applicable:

- cognitive/state architecture;
- GRID10/GWT/Hyperposition integration;
- persistence/restart/recovery;
- memory/world-model paths;
- executor/effect/completion contracts;
- installer/host semantic ABI;
- package/release manifest and verifier;
- synthetic/mock host tests;
- failure/concurrency/soak tests;
- optional VPS bridge implementation;
- the Perception Fabric core architecture and synthetic/mocked multi-source acceptance.

`LOCAL_ACCEPTANCE != DEFERRED_ARCHITECTURE_IMPLEMENTATION`

If a local Claude Code/Opus acceptance run must invent major missing modules, that is evidence of a failed VPS handoff gate. Prefer returning a minimal failure receipt to canonical VPS engineering, repairing once, adding a regression test, and rebuilding the release candidate.

## Perception Fabric obligation

Trigger-4 must treat the Perception Fabric as a core architecture requirement, not a later optional feature. Consult:

- `architecture/PERCEPTION_FABRIC.md`;
- `architecture/PERCEPTION_FABRIC_HARDENING_20260829.md`;
- `workpackages/PERCEPTION_FABRIC_PHASE.json`.

Important execution laws include:

```text
CONFIGURED_PERCEPTION_SOURCES = 0..N
ACTIVE_RETINA_CORTEX_ANALYSIS_WORKERS = 0..4 initially
ONE_CAPTURE_OWNER_PER_SOURCE
OBSERVE_INTENT_REQUIRES_CURRENT_PERMISSION_SNAPSHOT
ARRIVAL_ORDER != EVENT_TIME_ORDER
BASELINE_CONTINUOUS_PERCEPTION_REQUIRES_NO_LLM_TOKENS
PERCEPTION_MUST_NOT_STARVE_COGNITION
```

The VPS side builds/tests the source registry, permission model, CaptureOwner/Broker state machine, token-free Retina L0 path, ObserveIntent, worker scheduler, temporal fusion, epistemic world ingress, bridge and dashboard API contract. The final local lane binds those prebuilt mechanisms to actual OS/device permission surfaces and performs real-device acceptance.

## Telemetry/evidence

Material high-load runs should record enough evidence to reconstruct:

- admitted jobs and capacity slices;
- work/claim identities and timing;
- CPU/compute load;
- RAM/memory pressure;
- relevant I/O/DB pressure;
- achieved concurrency/throughput;
- throttling or abort decisions;
- failures/retries;
- whether the shared 70% envelope and recovery reserve were preserved.

Perception stress runs should additionally record source cardinality, active capture owners, active analysis workers, queue/drop/backpressure behavior, source/clock-domain timing, general-VLM invocation count, raw-frame persistence count and cognitive/control latency impact.

## Budget separation

```text
TRIGGER4_ENGINEERING = MAXIMUM_USEFUL_DEPTH WITH SAFE SHARED VPS LOAD <=70%
FRANKENSTEIN2_RUNTIME = MINIMUM_NECESSARY TOKENS/RESOURCES FOR REQUIRED QUALITY
```

The Trigger-4 worker may spend engineering resources aggressively to prove a more efficient Frankenstein-2.0 runtime. The 70% VPS ceiling is a machine-safety coordination boundary, not a resource-conservation objective.
