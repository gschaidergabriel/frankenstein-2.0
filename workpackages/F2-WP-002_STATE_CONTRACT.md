# F2-WP-002 — Machine-State Consistency Contract

This contract defines the minimum deterministic invariants for the machine-readable workpackage state/claim/generation surface.

## Objects

Required files for an active generation:

- `workpackages/STATE.json`
- `workpackages/active/F2-WP-XXX.json`
- `workpackages/claims/F2-WP-XXX_G<generation>_<worker-or-tag>.json`

An ACTIVE pointer identifies the sole mutation authority for that workpackage. Terminal state requires an explicit reconciliation record.

## Invariants

1. The active-pointer filename workpackage ID equals its `workpackage_id`.
2. The active pointer has a positive integer `generation` and `claim_id`.
3. The active pointer's `claim_id`, `generation`, `worker_id`, `base_commit`, and `workpackage_id` agree with the referenced claim.
4. `workpackages/STATE.json` contains the same workpackage and reports a status consistent with the active claim.
5. An ACTIVE pointer must not point at a terminal claim.
6. A terminal workpackage (`ACCEPTED_AT_SCOPE`) requires a matching reconciliation reference in the claim/active pointer and at least one evidence item in `STATE.json`.
7. A claim filename mismatch is invalid; the filename's workpackage and generation must match its JSON fields.
8. Generation and claim identity are not inferred from timestamps or nearby commits.
9. Validation is fail-closed: malformed JSON, missing files, mismatched identities, unsupported statuses, or absent terminal evidence are errors.

The validator intentionally proves only machine-state consistency. It does not grant runtime, provider, VPS, GRID10, HCU, training, or whole-system acceptance.
