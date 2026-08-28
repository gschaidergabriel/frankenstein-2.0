# Frankenstein 2.0 Telemetry Spine

This directory defines the canonical experimental data contract for Frankenstein 2.0.

## Canonical project databases

The initializer `tools/init_telemetry_dbs.py` materializes the project-level longitudinal SQLite stores under `data/`:

- `system_telemetry.sqlite` — system/component events for every instrumented participant in a test.
- `communications.sqlite` — Frankenstein-2.0-produced communication events with causal/session/turn/tool metadata.
- `hypotheses.sqlite` — hypotheses, counterhypotheses, evidence, falsifiers and targeted discriminators.
- `bugs.sqlite` — defects, symptoms, reproduction, root-cause state, fix commits and regression evidence.
- `grid10_telemetry.sqlite` — GRID10 cycle/cell/Hyperposition/GWT selection/broadcast/uptake/re-entry telemetry.
- `performance.sqlite` — distributed traces, internal latency spans and resource samples.

These databases are longitudinal project stores. They are not substitutes for immutable run-local evidence packages.

## Test-run packages

Every material discriminating test series must create an immutable package at:

```text
runs/<WP-ID>/<series-id>/<run-id>/
  manifest.json
  receipt.json
  sources.json
  environment.json
  system_telemetry.sqlite
  communications.sqlite
  hypotheses.sqlite
  bugs.sqlite
  grid10_telemetry.sqlite      # required when GRID participates
  performance.sqlite
  metrics.json
  logs/                        # or a compressed raw-log bundle when material
  artifacts/                   # or immutable external refs + hashes when too large
  SHA256SUMS
  CLOSED.json
```

The run manifest enumerates every expected participating source. Each expected source must have a collector/instrumentation record or an explicit `NOT_INSTRUMENTABLE` reason. Missing expected sources prohibit a `FULL_TELEMETRY` claim.

## Time and causal identity

Use both wall-clock UTC timestamps and monotonic timing whenever duration or local ordering matters. Carry the strongest available causal identity, including where applicable:

`run_id`, `series_id`, `workpackage_id`, `generation`, `trace_id`, `span_id`, `parent_span_id`, `session_id`, `agent_id`, `task_id`, `turn_id`, `causal_id`, `invocation_id`, `tool_use_id`, `child_agent_id`.

Unknown attribution stays `UNKNOWN`; it is not guessed.

## Bug closure

`FIXED` means the confirmed root cause itself is removed or deliberately neutralized at its source and the repository contains distinguishing root-cause evidence, a fix commit/config identity, regression test identity and regression receipt. `SYMPTOM_GONE != FIXED`.

The current initializer mechanically rejects insertion/update to `FIXED` when the required closure evidence fields are absent.

## GRID and latency scope

When GRID participates, structured telemetry must cover cycles/cells, candidates, Hyperposition, GWT selection/broadcast/uptake/re-entry and downstream influence at the scope implemented by the current schema. Performance traces must use `trace_id`/`span_id`/`parent_span_id` and monotonic timing so later collectors can decompose end-to-end latency into internal critical-path spans.

## Current implementation scope

`tools/init_telemetry_dbs.py` establishes the initial SQLite schema and integrity gates only. It is **not** yet the complete WP-005 collector/finalizer stack and is not runtime evidence that every Frankenstein-2.0 component is instrumented.

Next WP-005 deltas are reusable event/communication/hypothesis/bug/GRID emitters, resource/latency collectors, run snapshot/finalization helpers and manifest-completeness enforcement.
