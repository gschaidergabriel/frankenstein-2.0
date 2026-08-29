# Trigger-4 VPS Parallel Capacity Policy

Status: ACTIVE ARCHITECTURE / EXECUTION POLICY
Owner direction: 2026-08-29
Applies to: exact `4`, `triggerword 4`, `triggerwort 4`

## Purpose

Trigger-4 engineering is allowed to use substantial VPS compute for parallel build, test, benchmark, falsification and measurement work. The goal is high engineering throughput and strong evidence without destabilizing the server.

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

## Budget separation

```text
TRIGGER4_ENGINEERING = MAXIMUM_USEFUL_DEPTH WITH SAFE SHARED VPS LOAD <=70%
FRANKENSTEIN2_RUNTIME = MINIMUM_NECESSARY TOKENS/RESOURCES FOR REQUIRED QUALITY
```

The Trigger-4 worker may spend engineering resources aggressively to prove a more efficient Frankenstein-2.0 runtime. The 70% VPS ceiling is a machine-safety coordination boundary, not a resource-conservation objective.
