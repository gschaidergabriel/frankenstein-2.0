# Frankenstein 2.0 Token and Resource Efficiency Policy

Status: ACTIVE ARCHITECTURE POLICY
Owner direction: 2026-08-29

## Core separation

Frankenstein 2.0 product/runtime efficiency and Trigger-6 research effort are deliberately separate budgets.

```text
TRIGGER6_RESEARCH = MAXIMUM_USEFUL_DEPTH
FRANKENSTEIN2_RUNTIME = MINIMUM_NECESSARY_TOKENS_AND_RESOURCES_FOR_REQUIRED_QUALITY
```

Trigger 6 must not be prematurely shortened to save research tokens or tool effort. Its job is to search deeply enough to discover and falsify better designs.

Frankenstein 2.0 itself should be token- and resource-efficient by architecture, not merely by asking models to be brief.

## Priority order

Efficiency optimization must preserve the following order:

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
- saving tokens by hiding evidence or silently dropping unresolved contradictions.

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

## Trigger-6 binding

Canonical research protocol:

`research/tool_intelligence/TRIGGERWORD_6_PROTOCOL.md`

Trigger 6 uses maximum useful research depth to discover and test efficiency improvements. Trigger 4 owns actual build/integration/runtime measurement. Runtime efficiency claims remain component- or workload-scoped until exact F2 evidence exists.
