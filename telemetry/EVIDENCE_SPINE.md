# Frankenstein 2.0 — Evidence / Telemetry Spine v1

This is the Phase-0 observability contract. It defines the minimum common envelope before collectors and runtime integrations are promoted.

## Canonical event channels

Every participating component emits or routes typed records into one or more channels:

- `SYSTEM` — lifecycle, health, state epoch, scheduler, DB identity, recovery.
- `COMMUNICATION` — parent/child, agent/agent, voice/tool/executor message delivery and ACK lineage.
- `HYPOTHESIS` — hypothesis, counterhypothesis, falsifier, confidence and evidence links.
- `BUG` — symptom, root-cause state, fix candidate, regression and closure evidence.
- `GRID10` — cycle/cell/workspace selection, broadcast, uptake, re-entry and control snapshot.
- `PERFORMANCE` — CPU/RAM/IO/token/decode/throughput measurements.
- `LATENCY` — causal spans and critical-path timing.
- `PERCEPTION` — typed observation/inference/NOT_COMPUTED and active-sensing lineage.
- `VOICE` — utterance/session/tool-return/barge-in/silence state with causal ids.
- `EFFECT` — request/admission/execution identity. Never interpreted as completion by itself.
- `COMPLETION` — typed verification outcome and completion deficit closure.

The common schema is `schemas/EVIDENCE_SPINE.schema.json`.

## Causal minimum

A telemetry record must carry a stable `event_id`, `run_id`, timestamp, component, event type, `causal_id`, and `generation`. Where the surface supports them, it must also carry `session_id`, `agent_id`, `task_id`, and `turn_id`.

Missing identity is not silently guessed. A collector that cannot bind a field leaves it `null` and the test manifest must declare the limitation.

## Epistemic typing

Telemetry can say what was observed by the instrument, but it cannot promote model output or simulation into world fact. Use only these statuses:

`OBSERVED | INFERRED | HYPOTHESIS | SIMULATED | UNKNOWN | CONFLICT | NOT_COMPUTED`

## Run packages

Every material test series lives under:

`runs/<series>/<run_id>/`

At minimum the package contains a schema-valid `manifest.json`. Optional files may include telemetry JSONL/SQLite, traces, metrics, system logs, communication slices, GRID10 slices, hypotheses, bugs and negative results.

Paths are immutable by convention once the run is closed. Corrections are new run IDs or explicit successor receipts; do not rewrite old failures into passes.

## Promotion boundary

This Phase-0 contract is source/schema evidence only. It does not prove collectors are wired, a runtime executed, GRID10 ran physically, or Frankenstein 2.0 is accepted end to end.

F2-WP-005 remains `IN_PROGRESS` until real components emit/route records and repository-bound runs demonstrate collector coverage, causal joining, crash behavior and bounded overhead.
