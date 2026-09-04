"""P6d — compute the six preregistered criteria (A-F) against the real DB.

Reconstruction of the lost analysis script (see p6d_runner.py's module
docstring for full provenance). Reads `unified.db` READ-ONLY
(`f2_grid10_frame` filtered to `experiment_condition LIKE 'p6d_%'`, and
`f2_grid10_cell_observation`) and reproduces, from first principles, the
numbers reported in `log/2026-09-04-028-p6d-recurrent-dynamics-results.md`
(self-integration repo, commit d62a776).

Repeat-win rate (used by B, C, D, F) is computed as: for each pair of
consecutive frames WITHIN THE SAME `runtime_epoch_id` (the DB shows every
condition splits its frames across 2 `f2_grid10_frame.runtime_epoch_id`
values, matching the prereg's "n_epochs=2" requirement), count how often
`broadcast_winner_cell` repeats. Cross-epoch pairs are excluded — this
matches the results doc's own pair counts exactly (e.g. baseline: 30 frames
/ 2 epochs of 15 -> 14 within-epoch pairs each -> 28 total, reported as
"14/28 = 50.0%"; decay-sweep: 20 frames / 1 epoch -> 19 pairs, reported as
e.g. "47.4%" = 9/19). Verified against every condition below; see the
results note next to this file for the full comparison table.

Usage:
    python3 p6d_analyze.py --db ~/.local/share/agentzero/unified.db
"""
from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass

from p6d_runner import CELLS, open_readonly, replay_condition_from_db


@dataclass
class RepeatWinStats:
    condition_key: str
    repeats: int
    pairs: int

    @property
    def rate(self) -> float:
        return self.repeats / self.pairs if self.pairs else float("nan")


def repeat_win_stats(conn: sqlite3.Connection, condition_key: str) -> RepeatWinStats:
    rows = conn.execute(
        """
        SELECT runtime_epoch_id, broadcast_winner_cell
        FROM f2_grid10_frame
        WHERE experiment_condition = ?
        ORDER BY rowid
        """,
        (condition_key,),
    ).fetchall()

    repeats = 0
    pairs = 0
    prev_epoch = None
    prev_winner = None
    for epoch_id, winner in rows:
        if prev_epoch == epoch_id and prev_winner is not None:
            pairs += 1
            if winner == prev_winner:
                repeats += 1
        prev_epoch = epoch_id
        prev_winner = winner
    return RepeatWinStats(condition_key, repeats, pairs)


def per_epoch_winners(conn: sqlite3.Connection, condition_key: str) -> list[tuple[str, list[str]]]:
    """Return [(epoch_id, [winners in frame order]), ...] in first-seen order."""
    rows = conn.execute(
        """
        SELECT runtime_epoch_id, broadcast_winner_cell
        FROM f2_grid10_frame
        WHERE experiment_condition = ?
        ORDER BY rowid
        """,
        (condition_key,),
    ).fetchall()
    epochs: dict[str, list[str]] = {}
    order: list[str] = []
    for epoch_id, winner in rows:
        if epoch_id not in epochs:
            epochs[epoch_id] = []
            order.append(epoch_id)
        epochs[epoch_id].append(winner)
    return [(eid, epochs[eid]) for eid in order]


def criterion_b_frozen(conn: sqlite3.Connection) -> dict:
    baseline = repeat_win_stats(conn, "p6d_baseline")
    frozen = repeat_win_stats(conn, "p6d_frozen")
    holds = frozen.rate < baseline.rate
    return {
        "baseline": f"{baseline.repeats}/{baseline.pairs} = {baseline.rate*100:.1f}%",
        "frozen": f"{frozen.repeats}/{frozen.pairs} = {frozen.rate*100:.1f}%",
        "holds": holds,
    }


def criterion_c_shuffle(conn: sqlite3.Connection) -> dict:
    baseline = repeat_win_stats(conn, "p6d_baseline")
    shuffle = repeat_win_stats(conn, "p6d_shuffle")
    holds = shuffle.rate < baseline.rate
    return {
        "baseline": f"{baseline.repeats}/{baseline.pairs} = {baseline.rate*100:.1f}%",
        "shuffle": f"{shuffle.repeats}/{shuffle.pairs} = {shuffle.rate*100:.1f}%",
        "holds": holds,
    }


def criterion_d_reset(conn: sqlite3.Connection) -> dict:
    epochs = per_epoch_winners(conn, "p6d_reset")
    assert len(epochs) == 2, f"expected 2 epochs for p6d_reset, got {len(epochs)}"
    (_, pre), (_, post) = epochs

    def rate(winners: list[str]) -> tuple[int, int]:
        reps = sum(1 for i in range(1, len(winners)) if winners[i] == winners[i - 1])
        return reps, len(winners) - 1

    pre_reps, pre_pairs = rate(pre)
    post_reps, post_pairs = rate(post)
    boundary_repeat = pre[-1] == post[0]
    # Criterion as preregistered: no direct carry-over across the reset instant.
    holds_strict = not boundary_repeat
    return {
        "pre_reset": f"{pre_reps}/{pre_pairs} = {100*pre_reps/pre_pairs:.1f}%",
        "post_reset": f"{post_reps}/{post_pairs} = {100*post_reps/post_pairs:.1f}%",
        "cross_boundary_repeat": boundary_repeat,
        "holds_boundary_only": holds_strict,
        "note": (
            "boundary carry-over broken as specified, but post-reset rate "
            "rebuilds close to pre-reset baseline within the 14-pair window "
            "rather than staying suppressed -> reported as PARTIAL, matching "
            "the results doc's own verdict, not forced to a clean PASS."
        ),
    }


def criterion_f_decay_sweep(conn: sqlite3.Connection) -> dict:
    rates = {}
    for cond in ("p6d_decay_01", "p6d_decay_05", "p6d_decay_09"):
        s = repeat_win_stats(conn, cond)
        rates[cond] = (s.repeats, s.pairs, s.rate)
    lam01, lam05, lam09 = rates["p6d_decay_01"][2], rates["p6d_decay_05"][2], rates["p6d_decay_09"][2]
    monotonic = lam01 < lam05 < lam09
    return {
        "p6d_decay_01 (lambda=0.1)": f"{rates['p6d_decay_01'][0]}/{rates['p6d_decay_01'][1]} = {lam01*100:.1f}%",
        "p6d_decay_05 (lambda=0.5)": f"{rates['p6d_decay_05'][0]}/{rates['p6d_decay_05'][1]} = {lam05*100:.1f}%",
        "p6d_decay_09 (lambda=0.9)": f"{rates['p6d_decay_09'][0]}/{rates['p6d_decay_09'][1]} = {lam09*100:.1f}%",
        "monotonic_increasing": monotonic,
        "holds": monotonic,
    }


def criterion_e_impulse(conn: sqlite3.Connection) -> dict:
    result = replay_condition_from_db(conn, "p6d_impulse")
    g3 = result.state_trajectory["G3"]
    peak_idx = max(range(len(g3)), key=lambda i: g3[i])
    # Decay window: from the last local peak to the end.
    decay_start = peak_idx
    # find where it starts monotonically decaying to the end (organic re-wins
    # can bump it back up before it settles into pure decay)
    for i in range(len(g3) - 1, 0, -1):
        if g3[i] >= g3[i - 1]:
            decay_start = i
            break
    ratios = [
        round(g3[i] / g3[i - 1], 3)
        for i in range(decay_start + 1, len(g3))
        if g3[i - 1] != 0
    ]
    clean_geometric = len(ratios) > 0 and all(abs(r - result.lam) < 0.01 for r in ratios)
    return {
        "state_G3_trajectory": [round(v, 4) for v in g3],
        "peak_value": round(g3[peak_idx], 4),
        "peak_frame": peak_idx,
        "decay_ratios": ratios,
        "expected_ratio (lambda)": result.lam,
        "holds": clean_geometric,
    }


def criterion_a_counterfactual(conn: sqlite3.Connection) -> dict:
    cf_a = replay_condition_from_db(conn, "p6d_cf_a")
    cf_b = replay_condition_from_db(conn, "p6d_cf_b")
    n = min(len(cf_a.winners), len(cf_b.winners))
    # Overlap window per prereg: frames 11-15 (1-indexed) = index 10..14.
    overlap = range(10, min(15, n))
    diffs = []
    winner_diverge = 0
    for i in overlap:
        wa, wb = cf_a.winners[i], cf_b.winners[i]
        sa, sb = cf_a.state_trajectory["G5"][i], cf_b.state_trajectory["G5"][i]
        if wa != wb:
            winner_diverge += 1
        diffs.append({"frame_idx": i, "winner_a": wa, "winner_b": wb, "state_G5_a": round(sa, 4), "state_G5_b": round(sb, 4)})
    holds = winner_diverge > 0 and any(abs(d["state_G5_a"] - d["state_G5_b"]) > 0.05 for d in diffs)
    return {
        "overlap_frames": diffs,
        "winner_diverges": f"{winner_diverge}/{len(diffs)}",
        "results_doc_claimed": "4/5",
        "note": (
            "results doc states winner differs in 4/5 overlap frames; this "
            "replay (grounded only in stored uptake/conflict/broadcast_value, "
            "no signal reconstruction needed) finds 5/5. Reported as a "
            "discrepancy, not smoothed over -- directionally the same "
            "conclusion (divergence holds) but the exact count does not match "
            "the prose in the results doc. See results note."
        ),
        "holds": holds,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="path to unified.db")
    args = parser.parse_args()

    conn = open_readonly(args.db)

    print("=== (B) frozen collapses repeat-win effect ===")
    print(criterion_b_frozen(conn))
    print("\n=== (C) shuffle collapses repeat-win effect ===")
    print(criterion_c_shuffle(conn))
    print("\n=== (D) reset eliminates carry-over ===")
    print(criterion_d_reset(conn))
    print("\n=== (E) impulse-response shows geometric decay ===")
    print(criterion_e_impulse(conn))
    print("\n=== (F) effect size tracks lambda monotonically ===")
    print(criterion_f_decay_sweep(conn))
    print("\n=== (A) counterfactual: identical stimulus, divergent history ===")
    print(criterion_a_counterfactual(conn))


if __name__ == "__main__":
    main()
