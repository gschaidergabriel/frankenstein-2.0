# F2-WP-1207 -- GRID10 functionally-neutral observation schema

Direct answer to Gabriel's directive of 2026-09-03: GRID10 (`G1`..`G10`,
`src/frankenstein2/grid10_interface.py`, F2-WP-503) has no semantic cell
assignment. Naming cells now ("G3 = memory") would assert architecture
instead of measuring it. This iteration builds the **measurement side**
instead: a schema + harness that records real per-cell observations
(inputs, outputs, uptake, reentry, conflicts, resource use, temporal
correlation) keyed only by `logical_cell_id`, with **no naming step at
all** -- deliberately not even attempted.

## What GRID10 is (context, unchanged from LOCAL-ITER3)

Pure stdlib data/validation module. Ten opaque logical cell slots (`G1`..
`G10`), bounded input/output/work budgets, sha256-based canonical
accounting (`Grid10Plan`, `CellBudget`, `CellInput`, `CellOutput`,
`account_outputs`). No model calls, no process spawning, no state mutation,
no live-instance contact. `LOCAL-ITER3-20260902T183203Z/grid10_compat_check.py`
in this same tree already proved (PASS) that it imports and runs cleanly
under v1's interpreter with zero third-party dependencies and zero contact
with v1's `unified.db`. This iteration reuses that same safety posture
(synthetic data only, no live process) but drives the ABI through a batch
of scenarios instead of one, to get observation-schema-shaped output.

## The schema (`grid10_observation_schema.py`)

Two versioned JSON schema tags:
- `FRANKENSTEIN2_GRID10_OBSERVATION_EVENT/v1` -- one record per "cell
  touch" (one `CellInput`+`CellOutput` construction attempt within one
  synthetic scenario-cycle): `logical_cell_id`, `sequence_index`,
  `wall_time_ns`, `outcome` (ok/rejected), and nested `input`/`output`
  blocks (work units, reentry depth, ref counts/length stats, status,
  rejection reason if any).
- `FRANKENSTEIN2_GRID10_OBSERVATION_REPORT/v1` -- the aggregate: per-cell
  rollups (uptake, inputs, outputs, reentry, resource) for all ten cells,
  a temporal-correlation block (pairwise co-occurrence + immediate-sequence
  adjacency across scenario-cycles), two explicit conflict probes, a
  whole-run resource summary, and a distinguishability self-check.

Every dimension Gabriel listed is present and keyed only by
`logical_cell_id`:

| Dimension | Where in schema |
|---|---|
| Inputs | `per_cell[cid].inputs` (ref counts, work units requested) -- form/count only, no content interpretation |
| Outputs | `per_cell[cid].outputs` (status distribution, work units used, output ref counts) |
| Uptake | `per_cell[cid].uptake` (touches, touch_rate over N scenarios) |
| Reentry | `per_cell[cid].reentry` (observed `reentry_depth` values, count > 0) |
| Konflikte | top-level `conflict_observations` (two explicit probes, see below) |
| Ressourcenverbrauch | `per_cell[cid].resource` (real `time.perf_counter_ns` per touch) + top-level `resource_summary` (real `resource.getrusage` delta for the whole run) |
| Zeitliche Korrelationen | top-level `temporal_correlation` (pairwise co-occurrence, sequence adjacency) |

## Mechanical no-naming guard, not just a promise

`_assert_no_semantic_leakage()` scans the canonical-JSON dump of every
event, every per-cell aggregate, and the temporal-correlation block against
a denylist of interpretive/naming tokens (`memory`, `attention`,
`reasoning`, `planning`, `sensor`, `identity`, `role=`, etc., German
equivalents included) before it is emitted. This run passed the guard for
all 137 events + 10 per-cell aggregates + the temporal block -- checked at
runtime, not just asserted in prose.

The synthetic drive pattern itself (which cells get touched, with what
reentry depth, what status) is a closed-form function of `cell_index`
only -- `0.25 + 0.055 * cell_index` for touch probability, index-mixed
formulas for reentry depth / work units / status pick -- applied
identically to all ten cells. No cell is special-cased or picked out by a
story. This is the mechanism that keeps "let's make G3 realistic" from
accidentally becoming "let's make G3 memory-like".

## First real run: 24 synthetic scenarios, real numbers

```
python3 grid10_observation_schema.py > grid10_observation_report.json
```

137 raw events, all ten cells got genuinely different, non-identical
numbers (`distinguishability_check.touch_rate_spread_nonzero: true`,
neither always- nor never-touched):

| cell | touches/24 | touch_rate | reentry>0 | wall_time_ns mean |
|---|---|---|---|---|
| G1 | 8 | 0.333 | 6 | 196,981 |
| G2 | 9 | 0.375 | 6 | 230,993 |
| G3 | 10 | 0.417 | 8 | 195,986 |
| G4 | 11 | 0.458 | 8 | 191,592 |
| G5 | 13 | 0.542 | 10 | 190,765 |
| G6 | 14 | 0.583 | 11 | 192,243 |
| G7 | 16 | 0.667 | 11 | 189,406 |
| G8 | 17 | 0.708 | 13 | 191,766 |
| G9 | 19 | 0.792 | 15 | 190,413 |
| G10 | 20 | 0.833 | 14 | 189,537 |

Touch-rate spread (0.333 -> 0.833) is a direct, expected artifact of the
index-formulaic probability, not a discovery -- exactly as intended: it
proves the schema *can* distinguish cells, using synthetic data engineered
to do exactly that and nothing more. `wall_time_ns` means cluster tightly
(~189k-231k ns, i.e. a few hundred microseconds per touch on this Python
3.12 interpreter) with G2 as a mild outlier -- most plausibly ordinary
interpreter/GC jitter on a 24-scenario sample, not a per-cell cost
difference; a larger real run would be needed to say more, and this report
does not claim more.

Whole-run resource (`resource.getrusage` delta, real, not estimated):
`ru_utime_delta_seconds=0.0407`, `ru_stime_delta_seconds=0.0`,
`ru_maxrss_delta_kb=512` for 137 events across 24 scenarios plus the two
conflict probes.

## Conflict probes: what the ABI does and does not detect

1. **Same cell, same `account_outputs()` call** (two `CellOutput`s for
   `G5` inside one plan's pairs list): **hard-rejected**,
   `Grid10InterfaceError: duplicate output for logical cell`. The ABI
   actively guards this shape.
2. **Same cell, two independent `Grid10Plan` instances** (different
   `frame_id`/`policy_id`, both targeting `G8`): **both succeeded
   independently, no error, no interaction**. Confirmed by code reading
   (no module-level mutable state -- no registry, lock, or counter shared
   across `Grid10Plan` instances) and empirically by the probe. Honest
   framing per the task brief: this is **not** evidence the module is safe
   against cross-frame conflicts -- it is a structural absence. The module
   has no notion of "another plan" to conflict with, so it cannot detect
   this shape at all. A real conflict guard for this case would have to
   live in whatever orchestrator constructs/dispatches `Grid10Plan`
   instances, not inside `grid10_interface.py` itself.

## What this iteration does NOT do

- Does not assign any name, role, or functional interpretation to any
  `Gx` cell -- checked mechanically, see above.
- Does not wire GRID10 into `stern.py`, v1, or any live code path.
- Does not touch `main` in either repo.
- Does not claim the synthetic drive pattern reflects real production
  GRID10 usage -- it is index-formulaic by construction, explicitly to
  avoid smuggling a narrative into the numbers. A real run of this same
  schema against actual GRID10 traffic (once/if GRID10 is ever wired to a
  live source of Frame/Plan events) is the next step that would produce
  numbers worth interpreting.

## Next candidate

Once GRID10 has any real (non-synthetic) traffic source, point this same
schema/harness at it unchanged -- the event/report schema tags are
versioned (`/v1`) specifically so a later real-traffic run is
apples-to-apples comparable to this synthetic baseline.
