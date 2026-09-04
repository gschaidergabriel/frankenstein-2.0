# P6d runner/analyzer reconstruction — results

Reconstructs `p6d_runner.py` + `p6d_analyze.py`, lost when the working branch
`self-integration/wp1207-p6b-doc-and-state-test-20260904` and `/tmp/p6d-work`
both disappeared (checked: not local, not on any remote, not dangling —
genuinely gone). This is a reconstruction task under F2-WP-1207, not a
blocker for P7, per Gabriel's directive.

Ground truth used: `PREREG_P6D_20260904.md` (self-integration repo, commit
`75cb4adc66c607be77d89d78b9e01e31e5d32257`), `log/2026-09-04-028-p6d-recurrent-dynamics-results.md`
(self-integration repo, commit `d62a7764595d41d1f49b2a54dc43d49aed44c6a6`),
and direct read-only inspection of the real `unified.db` rows
(`f2_grid10_frame` where `experiment_condition LIKE 'p6d_%'`, 231 rows;
`f2_grid10_cell_observation`; `f2_grid10_p6d_state`, 90 rows).

## What this is NOT claiming

**Not claiming the original code is recovered.** `p6d_runner.py`/`p6d_analyze.py`
here are a rebuild from spec + DB evidence, not a byte-identical recovery —
there is no way to prove identity to code that no longer exists anywhere.
What IS claimed, and is mechanically checkable: replaying the preregistered
recursion using only facts already stored in the real DB reproduces the
results doc's reported numbers, in most cases exactly.

## Method

Two halves, deliberately separated in `p6d_runner.py`:

1. **`replay_condition_from_db`** — replays `state(t+1) = lambda*state(t) +
   alpha*uptake(t) + beta*broadcast(t) - gamma*conflict(t)` per cell per
   frame, using ONLY `f2_grid10_frame.broadcast_winner_cell` /
   `.broadcast_value` / `.runtime_epoch_id` and
   `f2_grid10_cell_observation.uptake` / `.conflict_flag` — all already
   recorded in the DB from the original run. **No signal reconstruction
   needed for this half at all** — winner, uptake, conflict, and the
   winner's own broadcast value are ground truth, not derived.
2. **`derive_signal` / `simulate_condition`** — a generative simulator that
   COULD produce a new run from scratch (for a future properly-powered
   rerun). Its sha256-to-float mapping is a reasonable guess at the prereg's
   "deterministic pseudo-random value in [0,1) ... derived from
   sha256(turn_event_id:cell:signal)" description, but is explicitly
   **unverified** — the DB does not expose raw per-cell signal values for
   non-winning cells, so there is nothing to check the guess against. Not
   used to touch real data in this task; DB access throughout is opened
   `mode=ro` with `PRAGMA query_only = ON`.

Read-only run: `python3 p6d_analyze.py --db ~/.local/share/agentzero/unified.db`.
Confirmed before and after: `f2_grid10_frame` p6d rows = 231, `f2_grid10_p6d_state`
rows = 90, unchanged.

## Reproduction vs. the results doc, criterion by criterion

| Criterion | Results doc | Reconstruction | Match |
|---|---|---|---|
| (B) frozen collapses effect | baseline 14/28=50.0%, frozen 1/28=3.6% | baseline 14/28=50.0%, frozen 1/28=3.6% | **exact** |
| (C) shuffle collapses effect | baseline 14/28=50.0%, shuffle 2/28=7.1% | baseline 14/28=50.0%, shuffle 2/28=7.1% | **exact** |
| (D) reset boundary | no cross-boundary repeat; post-reset 42.9% vs pre-reset 50.0%, "partial" | cross_boundary_repeat=False; post 6/14=42.9%, pre 7/14=50.0%, "partial" | **exact** |
| (E) impulse decay | 0.80 -> peak 2.31 (frame 3) -> geometric decay at ratio 0.700 from ~frame 10 | 0.8 -> peak 2.3144 (frame 3) -> ratio 0.700 exactly, and clean decay actually starts frame 8 (2 frames earlier than the doc's quoted window, same underlying decay — doc's window was just conservative) | **exact** (superset) |
| (F) decay-sweep monotonicity | lambda=0.1: 47.4%, 0.5: 36.8%, 0.9: 84.2%; not monotonic, doc calls it FAIL/underpowered | lambda=0.1: 9/19=47.4%, 0.5: 7/19=36.8%, 0.9: 16/19=84.2%; not monotonic | **exact** |
| (A) counterfactual | proposal_score(G5) diverges; state(G5) cf_a ~1.2-2.0 vs cf_b exactly 0.0; winner differs "4/5" overlap frames | state(G5) cf_a range 1.16-2.01 vs cf_b exactly 0.0; **winner differs 5/5** overlap frames | **magnitude match; winner-count discrepancy (5/5 vs stated 4/5) — see below** |

Overall qualitative pattern: **A, B, C, E hold cleanly; D is partial; F does
not hold as stated (likely underpowered, single run per lambda).** This
matches the results doc's own characterization exactly — the "4/6 PASS"
shorthand (4 clean holds, D partial, F fail) reproduces.

## The one real discrepancy found: (A)'s winner-divergence count

The results doc states "Winner differs in 4/5 overlap frames." Replaying
`p6d_cf_a` and `p6d_cf_b` from the DB and comparing `broadcast_winner_cell`
at overlap-window frame indices 10-14 gives **5/5** — every overlap frame
has a different winner between the two conditions (G5/G7, G8/G7, G5/G3,
G5/G7, G1/G7). This uses stored ground-truth winners directly, no replay
math involved, so it isn't a reconstruction-error candidate in the usual
sense (state-trajectory logic) — it's a straight read of
`f2_grid10_frame.broadcast_winner_cell` for the two conditions at those five
frame indices.

Not forcing a fit: this is reported as a discrepancy against the results
doc's prose, not resolved. Two honest possibilities, not adjudicated here:
(a) the original results doc's "4/5" was an informal/manual count that
undercounted by one, or (b) frame-index alignment between cf_a/cf_b in the
original analysis differed from the "index 10-14 of each condition's own
15-frame sequence" alignment used here in some way not visible from the
surviving DB schema. Either way it does not change criterion (A)'s
qualitative verdict ("Holds") — 5/5 divergence is if anything a *stronger*
confirmation of the counterfactual effect than 4/5, not a weaker one.

## Bugs mentioned in the results doc — status here

The results doc reports two bugs found and fixed during the original run:
(1) a write-transaction-batching bug in the *runner* that starved
`stern.py`'s epoch sync (a runtime/DB-locking issue, not a formula issue —
not applicable to this reconstruction since we don't write frames); (2) an
*analysis* bug where `cf_a`/`cf_b` turn_event_ids embedded `condition_key`,
breaking the "identical stimulus" precondition for the raw stimulus tag
match. This reconstruction's counterfactual check does not depend on
`turn_event_id` equality at all — it compares by frame index within each
condition's own 15-frame run (both cf_a/cf_b index 10-14 use the same
stimulus tags in the same order: short_a, short_b, long_context_a,
long_context_b, retrieval_hit_a per `STIMULUS_TAGS` cycling), so it is not
exposed to bug (2) in the first place.

## What was NOT re-run

No new frames were generated or written. The 231 real `f2_grid10_frame` rows
and 90 `f2_grid10_p6d_state` rows are exactly as they were before this task
started (checked, see counts above). `simulate_condition` in `p6d_runner.py`
exists as a template for a FUTURE properly-powered rerun (needed to actually
resolve criterion F, per both the original results doc and this
reconstruction) but was not invoked against production state.

## Bottom line

Mechanism is reconstructible and, for every criterion except one prose
detail in (A), reproduces the original results doc's numbers exactly using
only DB-recorded ground truth (no signal-function guessing required for any
of B/C/D/E/F or the core of A). "Mechanism reproducible" — not "original
code recovered."
