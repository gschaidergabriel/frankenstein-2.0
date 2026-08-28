# Frankenstein 2.0 — Workpackage State Consistency Contract

Scope: **F2-WP-002 source/continuity metadata only**. This contract does not grant cognitive-runtime, GRID10, provider, VPS, effect, or whole-system credit.

## Authority surfaces

The machine-readable workpackage control surfaces are:

1. `workpackages/STATE.json` — broad workpackage status/evidence summary.
2. `workpackages/active/<workpackage_id>.json` — the sole current mutation-lineage pointer for that workpackage.
3. the pointer's `legacy_claim_ref` — immutable claim/provenance record for the pointed generation.
4. for a terminal pointer, its `terminal_reconciliation_ref` — immutable terminal reconciliation evidence.

A historical claim file alone is never mutation authority.

## Required invariants

### STATE

- schema is `FRANKENSTEIN2_WORKPACKAGE_STATE/v1`;
- canonical repository is `gschaidergabriel/frankenstein-2.0`;
- every workpackage key matches `F2-WP-<integer>`;
- each entry has an allowed status;
- `ACCEPTED_AT_SCOPE` requires at least one non-empty evidence reference.

### Active mutation-lineage pointer

For every JSON file under `workpackages/active/`:

- filename stem equals `workpackage_id`;
- `workpackage_id` exists in `STATE.json`;
- generation is integer `>= 1`;
- `claim_id`, `worker_id`, `base_commit`, and `legacy_claim_ref` are present;
- `base_commit` is lowercase 40-hex;
- the referenced claim exists and matches workpackage, generation, claim, and worker identity;
- pointer state is one of `ACTIVE`, `ACCEPTED`, `FAILED_TERMINAL`, `RETIRED_STALE`, `SUPERSEDED`.

### ACTIVE state

If pointer state is `ACTIVE`:

- broad STATE status must be `IN_PROGRESS`, `HOLD`, or `BLOCKED`;
- no terminal reconciliation is required or inferred.

### Terminal state

If pointer state is terminal:

- `terminal_reconciliation_ref` is required;
- the reconciliation exists and matches workpackage, generation, claim, worker, and terminal state;
- a terminal component claim does **not** automatically close the broader workpackage.

For terminal `ACCEPTED`:

- if reconciliation explicitly says `broader_workpackage_status: IN_PROGRESS`, broad STATE may remain `IN_PROGRESS`;
- otherwise broad STATE must be `ACCEPTED_AT_SCOPE`.

This scoped-terminal exception is required because one accepted generation can close a bounded component contract while the parent workpackage remains open.

## Fail-closed law

Unknown/missing claim identity, malformed generation, wrong filename, missing workpackage state, terminal pointer without reconciliation, reconciliation identity mismatch, invalid broad-state transition, or accepted state without evidence => validation failure.

```text
CLAIM_FILE != MUTATION_AUTHORITY
TERMINAL_COMPONENT_ACCEPTANCE != AUTOMATIC_WHOLE_WORKPACKAGE_ACCEPTANCE
SOURCE_CONTINUITY_PASS != FRANKENSTEIN_RUNTIME_PASS
```
