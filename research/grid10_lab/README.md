# GRID10 — first Frankenstein 2.0 laboratory prototype

Status: **LAB_ONLY / ZERO_PRODUCT_CREDIT**

This directory is the first bounded GRID10 laboratory prototype admitted into the
`frankenstein-2.0` build repository. It is intentionally isolated from the canonical
Clay/EntityOS state authority and from the active Voice/FDX runtime boundary.

## What this prototype contains

`grid10_fabric_lab.py` adapts the central control invariants of the canonical Clay GRID10
fabric into a small, standard-library-only SQLite/WAL laboratory fabric:

- autonomous node join / heartbeat;
- claim-aware task acquisition with epoch CAS;
- ordinary-node S1 write rejection;
- explicit `NODE_RESULT/v1` result channel;
- temporary scope-bound coordinator leases;
- coordinator-only scoped commit;
- lease revocation;
- stale ordinary-task claim recovery;
- duplicate-result rejection;
- sandbox-local state with explicit `canonical_truth=false` and `effect_authority=false`.

The smoke test exercises the authority fence, result admission, duplicate rejection and
post-revocation write denial.

## Provenance

Canonical donor repository:
`gschaidergabriel/clay-global-research-entity`

Donor commit:
`ef0ad6b49013cdfac17c6253b5c32626a0072fe9`

Primary donor file:
`tools/grid10_fabric.py`

Primary donor blob:
`a4521bbb9c3238d5638be8170d102f32eef9beba`

The user also supplied `GRID10_Fabric_2026-08-27.zip` as the intended package reference.
The attachment bytes were not mounted/readable in this execution, so this import does **not**
claim byte-equivalence to that ZIP. The implementation is instead provenance-bound to the
independently retrievable canonical Clay donor above. `PROVENANCE.json` records this fence.

## Credit fence

Adding or passing this lab prototype does **not** establish:

- physical GRID10 credit;
- canonical S1/UnifiedDB authority;
- GWT/J-Space causal uptake/re-entry;
- effect authority;
- whole-product acceptance;
- training credit;
- Voice/FDX runtime credit.

Those require their own exact runtime subjects and receipts. In particular, the active Voice/FDX
subject remains separate and must not inherit credit from this research lane.

## Promotion path

The next GRID10-specific evidence step is a bounded S1/S2 sandbox run with multiple independent
OS processes against a disposable shared fabric, followed by the original GRID10 discriminators
(join, dynamic coordinators, CAS collision, revocation, restart/rejoin, stale/duplicate rejection,
recursive compression and resource metrics). Only measured properties may be promoted.
