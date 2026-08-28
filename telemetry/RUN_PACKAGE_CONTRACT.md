# Frankenstein 2.0 — Immutable Run Package Contract

Workpackage: `F2-WP-004`

This contract defines package identity and closure only. It does **not** grant runtime, instrumentation-coverage, GRID10, whole-system, or scientific acceptance credit by itself.

## Canonical package shape

```text
runs/<series>/<run_id>/
  manifest.json
  ARTIFACTS.json
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

Schemas:

- `schemas/run_package_manifest.schema.json`
- `schemas/run_artifact_index.schema.json`
- `schemas/run_closed_receipt.schema.json`

## Identity

A run is identified by `run_id` and is bound to a `workpackage_id + generation + claim_id` tuple. The manifest records the source commit before execution and, when known, the source commit after the bounded step.

A reused human-readable series name never means a reused run identity.

## Observability law

Every component/process participating in the claimed test scope must appear in `manifest.json.participants` as either:

- `OBSERVABLE`, with telemetry references where available; or
- `NOT_OBSERVABLE`, with a non-empty reason.

Absence from telemetry is not silently interpreted as success, idleness, or non-participation.

## Artifact index

`ARTIFACTS.json` records immutable payload artifacts with:

- relative path;
- SHA-256 digest;
- byte size;
- role;
- producer/source provenance;
- optional causal/trace identity.

Paths are repository-package relative and may not escape the run directory.

## Closure order — avoids circular hashes

Closure is deterministic and intentionally excludes self-referential files from their own digest sets:

1. Finish all payload files and `manifest.json`.
2. Create `ARTIFACTS.json` over payload files plus `manifest.json`. Do **not** index `ARTIFACTS.json`, `SHA256SUMS`, or `CLOSED.json` inside `ARTIFACTS.json`.
3. Create `SHA256SUMS` over payload files, `manifest.json`, and `ARTIFACTS.json`. Do **not** include `SHA256SUMS` or `CLOSED.json` in `SHA256SUMS`.
4. Create `CLOSED.json` last. It binds the SHA-256 digests of `manifest.json`, `ARTIFACTS.json`, and `SHA256SUMS` and declares the exact evidence classification/scope.
5. After `CLOSED.json` exists, the run directory is immutable. Any correction creates a new run identity; it never edits a closed run in place.

`CLOSED.json` is therefore a terminal closure receipt, not a file that recursively hashes itself.

## Evidence classification

Permitted classifications are deliberately explicit:

- `SOURCE_ONLY`
- `UNIT_RUNTIME`
- `COMPONENT_RUNTIME`
- `INTEGRATION_RUNTIME`
- `WHOLE_SYSTEM_RUNTIME`
- `NEGATIVE_RESULT`
- `BLOCKED`

The close schema mechanically requires `SOURCE_ONLY` to carry:

```text
runtime_execution_observed = false
runtime_credit = 0
closure_status = CLOSED_SOURCE_ONLY
```

Likewise, any receipt with `runtime_execution_observed=false` is forbidden from claiming positive runtime credit.

## Immutability and promotion

A closed package may support promotion only at the exact scope its evidence establishes. A source-only package can establish that a contract/file exists at a commit; it cannot establish that the contract was executed correctly on any runtime.

`COMPONENT_PASS != WHOLE_SYSTEM_PASS`

`SOURCE_PRESENCE != RUNTIME_PASS`

`NOT_OBSERVABLE != PASS`

`CLOSED != ACCEPTED_BEYOND_DECLARED_SCOPE`
