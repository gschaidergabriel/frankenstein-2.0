# Frankenstein 2.0 Telemetry Spine

This directory defines the canonical experimental data contract for Frankenstein 2.0.

## Canonical project databases

The initializer `tools/init_telemetry_dbs.py` materializes these SQLite databases under `databases/`:

- `system_telemetry.sqlite` — system/component logs for every instrumented component participating in a test.
- `communications.sqlite` — all Frankenstein-2.0-produced communication events with causal/session/turn/tool metadata.
- `hypotheses.sqlite` — hypotheses, counterhypotheses, evidence, falsification plans and targeted tests.
- `bugs.sqlite` — defects, symptoms, reproduction, root-cause state, fix commits and regression evidence.
- `grid10_telemetry.sqlite` — GRID10 cycle/cell/Hyperposition/GWT selection/broadcast/uptake/re-entry telemetry.
- `performance.sqlite` — distributed traces, all internal latency spans, queue waits, state intervals and resource samples.

## Test-run packages

Every material test series must create an immutable run package:

```text
runs/<series>/<run_id>/
  manifest.json
  logs/
  grid10/
  communications/
  measurements/
  traces/
  db_snapshots/
  receipts/
  negative_results/
  SHA256SUMS
  CLOSED.json
```

A participating process that does not emit/route telemetry must be listed as `NOT_OBSERVABLE` in the run manifest. A run must never silently claim complete instrumentation while an involved component is absent.

## Time and identity

Event records use both wall-clock UTC timestamps and monotonic timing when duration/ordering matters. Causal joins should carry the strongest available identity, including where applicable:

`run_id`, `workpackage_id`, `generation`, `trace_id`, `span_id`, `parent_span_id`, `session_id`, `agent_id`, `task_id`, `turn_id`, `causal_id`, `invocation_id`, `tool_use_id`, `child_agent_id`.

## Bug closure

`FIXED` means the root cause is identified and removed, not merely that the symptom disappeared. The bugs database mechanically rejects `FIXED` unless root-cause evidence, a fix commit, regression test and regression receipt are all present.

## Scope

This is an evidence/data spine, not proof that every F2 component is already instrumented. Instrumentation coverage is measured per test manifest and grows with the system.
