# Frankenstein 2.0 Token and Resource Efficiency Policy

Status: ACTIVE ARCHITECTURE POLICY
Owner direction: 2026-08-29

## Core separation

Frankenstein 2.0 product/runtime efficiency and Trigger-4/Trigger-6 engineering/research effort are deliberately separate budgets.

```text
TRIGGER4_WORK = MAXIMUM_USEFUL_BUILD_TEST_MEASUREMENT_DEPTH
TRIGGER6_RESEARCH = MAXIMUM_USEFUL_RESEARCH_DEPTH
FRANKENSTEIN2_RUNTIME = MINIMUM_NECESSARY_TOKENS_AND_RESOURCES_FOR_REQUIRED_QUALITY
```

Trigger 4 must not be prematurely shortened to save worker tokens, tool calls, test/CI effort, sandbox compute, debugging effort or analysis depth. Its job is to build, falsify, measure and integrate deeply enough to establish the strongest available evidence and continue through additional dependency-correct non-duplicate work when useful capacity remains.

Trigger 6 likewise must not be prematurely shortened to save research tokens or tool effort. Its job is to search deeply enough to discover and falsify better designs.

Frankenstein 2.0 itself should be token- and resource-efficient by architecture, not merely by asking models to be brief.

This means engineering/research may spend substantial resources to discover and prove a runtime that uses fewer resources.

## Trigger-4 execution-budget law

On an exact `4`, `triggerword 4`, or `triggerwort 4` invocation, subject to hard platform, safety, authority, provider, spending and claim constraints:

- use the largest useful reasoning, source-reading, tool, test, benchmark, failure-injection, debugging, measurement and output budget available;
- do not stop merely to conserve ChatGPT tokens, tool calls, CI attempts, local/sandbox compute or analysis effort;
- after one objective reaches a useful terminal state, continue into additional dependency-correct, non-duplicate objectives when useful work remains;
- a claimed or blocked objective is a reason to respect ownership and choose another useful objective, not a reason to end the run solely for resource conservation;
- use stronger negative tests, replay/restart/concurrency tests, exact-head CI and target-runtime measurements when they materially improve confidence or discriminate competing hypotheses;
- produce architecture deltas when evidence changes the best-supported integration, authority, component, resource or token strategy;
- preserve enough evidence to distinguish source presence, component success, hosted CI, target-runtime behavior, causal uptake, effect correctness and end-to-end acceptance.

Maximum useful effort never overrides hard authority, safety, provider or spending restrictions and never creates duplicate mutation authority.

## Trigger-4 VPS parallel capacity envelope

Maximum engineering effort does not mean uncoordinated machine saturation.

Trigger-4 workers may run useful build/test/benchmark/falsification jobs in parallel on the authorized VPS and may use up to approximately **70% aggregate usable VPS compute capacity**, provided the load is centrally coordinated and the machine remains healthy and recoverable.

```text
SUM(TRIGGER4_ADMITTED_VPS_LOAD) <= 70% OF CURRENT USABLE VPS COMPUTE CAPACITY
```

The 70% ceiling is shared across all Trigger-4 workers, not granted independently to each worker, and it is not a target when lower parallelism is sufficient.

Use one shared capacity authority/view. Prefer progressive admission (for example ~40% -> observe -> ~55% -> observe -> <=70%) and automatically throttle, serialize or abort expendable test load when memory pressure, swap/OOM evidence, I/O or DB/WAL stalls, runner/heartbeat/control-loop degradation, repeated crashes or another recovery signal appears.

The first constraining resource wins: a memory- or I/O-heavy workload may require substantially less than 70% CPU concurrency.

Keep reserve for OS, database, coordination/control plane, runners/bridges, monitoring/evidence persistence and emergency recovery.

Canonical detailed policy:

`architecture/TRIGGER4_VPS_PARALLEL_CAPACITY_POLICY.md`

## Priority order

Efficiency optimization of Frankenstein 2.0 must preserve the following order:

1. deterministic authority / safety / effect boundaries;
2. exact evidence, provenance and replayability;
3. required capability and measured quality;
4. token, context, latency and compute efficiency.

A cheaper path that breaks evidence, authority, correctness or required capability is not an optimization.

## First-class metrics

Where relevant, F2 workpackages and Trigger-4/Trigger-6 ablations should measure:

- input tokens per cycle/task;
- output tokens per cycle/task;
- total model calls and calls avoided;
- context/prompt bytes/tokens;
- retrieved evidence payload size;
- cache/reuse hit rate;
- repeated-state/restatement volume;
- p50/p95/p99 latency;
- CPU time and utilization;
- RSS/PSS RAM;
- GPU/VRAM and decode concurrency;
- disk I/O and network I/O;
- startup versus steady-state overhead;
- quality/evidence retained per token or per unit of compute.

## Preferred architectural moves

When equivalent or better in quality/evidence, prefer:

- compact typed state and identifiers over repeated prose state dumps;
- smallest-sufficient evidence retrieval over replaying whole histories;
- deterministic routers/gates for deterministic decisions instead of unnecessary model arbitration;
- stable cached summaries/projections with exact provenance pointers instead of regenerating unchanged context;
- event/reference identity and incremental deltas instead of full-state retransmission;
- shared weights/resident models and bounded physical decode concurrency instead of unnecessary duplicate model residency;
- early deterministic rejection/filtering before expensive cognition;
- narrow specialist invocation only when its expected information gain justifies the call;
- structural distillation of an external tool/mechanism when importing the complete framework adds avoidable runtime/dependency weight;
- local/offline deterministic computation when it can replace a model call without reducing required quality;
- output formats that carry exact machine-usable state with minimal redundant natural-language scaffolding.

## Anti-patterns

Treat the following as explicit optimization targets:

- sending unchanged canonical state to a model repeatedly;
- large prompts assembled from whole databases or whole logs when a typed slice is sufficient;
- repeated model calls for deterministic validation/routing;
- multiple modules independently reconstructing the same context;
- duplicated resident checkpoints without measured need;
- verbose inter-module natural-language protocols where compact typed packets suffice;
- context compression that destroys provenance, uncertainty or causal identity;
- saving runtime tokens by hiding evidence or silently dropping unresolved contradictions;
- saving Trigger-4 engineering resources by under-testing, under-measuring or stopping before another high-value non-duplicate discriminator;
- treating the shared 70% VPS envelope as a per-worker quota;
- maximizing parallelism without central admission/backpressure or recovery headroom.

## Architecture-delta rule

Research or measurements that reveal a materially cheaper F2 path with equal-or-better required quality should produce a versioned architecture delta when useful.

Such a delta should record:

- old path and proposed path;
- exact affected modules/workpackages;
- measured or expected token/resource change;
- quality/evidence comparison;
- authority/safety impact;
- counterhypothesis;
- executable falsifier/acceptance test;
- rollback boundary.

Do not promote an efficiency delta from aesthetic preference alone. Prefer measured ablation evidence.

## Trigger bindings

Canonical Trigger-6 research protocol:

`research/tool_intelligence/TRIGGERWORD_6_PROTOCOL.md`

Trigger 6 uses maximum useful research depth to discover and test efficiency improvements.

Trigger 4 owns actual build/integration/runtime measurement and also uses maximum useful engineering/test depth. The active owner binding on the Research-Entity side is:

`research_entity/global/TRIGGERWORD_4_MAXIMUM_EXECUTION_BUDGET_BINDING.md`

The F2-side VPS execution envelope is:

`architecture/TRIGGER4_VPS_PARALLEL_CAPACITY_POLICY.md`

Runtime efficiency claims remain component- or workload-scoped until exact F2 evidence exists.

```text
TRIGGER4_WORK_BUDGET != FRANKENSTEIN2_RUNTIME_BUDGET
TRIGGER6_RESEARCH_BUDGET != FRANKENSTEIN2_RUNTIME_BUDGET
SPEND ENGINEERING/RESEARCH RESOURCES TO PROVE A CHEAPER, BETTER RUNTIME
TRIGGER4_VPS_PARALLELISM = AGGRESSIVE_WHEN_USEFUL + CENTRALLY_COORDINATED + RECOVERABLE <=70% COMPUTE
```