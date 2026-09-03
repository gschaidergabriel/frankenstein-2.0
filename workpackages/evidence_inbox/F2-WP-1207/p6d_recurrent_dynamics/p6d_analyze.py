#!/usr/bin/env python3
"""Analyze P6d results against PREREG_P6D_20260904.md criteria A-F."""
import sqlite3, contextlib, sys, json, os, math

sys.path.insert(0, os.path.expanduser("~/frankenstein-repo/scripts"))
import stern  # noqa

DB_PATH = stern.DB_PATH


def frames_for(condition):
    with contextlib.closing(sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)) as c:
        rows = c.execute(
            "SELECT turn_event_id, broadcast_winner_cell, opened_at, runtime_epoch_id "
            "FROM f2_grid10_frame WHERE experiment_condition=? AND cohort='CONTROLLED_PROBE' "
            "ORDER BY opened_at ASC",
            (condition,),
        ).fetchall()
    return rows


def repeat_win_rate(condition, skip_across_epoch_boundary=True):
    rows = frames_for(condition)
    hits, total = 0, 0
    for i in range(1, len(rows)):
        prev_ep, cur_ep = rows[i - 1][3], rows[i][3]
        if skip_across_epoch_boundary and prev_ep != cur_ep:
            continue
        total += 1
        if rows[i - 1][1] == rows[i][1]:
            hits += 1
    return hits, total, (hits / total if total else float("nan"))


def state_trajectory(condition, cell):
    with contextlib.closing(sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)) as c:
        rows = c.execute(
            "SELECT updated_at, state_value, updated_by_frame_id FROM f2_grid10_p6d_state "
            "WHERE condition_key=? AND logical_cell_id=? ORDER BY updated_at ASC",
            (condition, cell),
        ).fetchall()
    return rows


def cf_compare(cell="G5", overlap_start_idx=10):
    with contextlib.closing(sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)) as c:
        def get(cond):
            return c.execute(
                "SELECT turn_event_id, broadcast_winner_cell, broadcast_value "
                "FROM f2_grid10_frame WHERE experiment_condition=? AND cohort='CONTROLLED_PROBE' "
                "ORDER BY opened_at ASC",
                (cond,),
            ).fetchall()
        a = get("p6d_cf_a")
        b = get("p6d_cf_b")
    overlap_a = a[overlap_start_idx:]
    overlap_b = b[overlap_start_idx:]
    diffs = []
    for ra, rb in zip(overlap_a, overlap_b):
        diffs.append({"turn": ra[0], "winner_a": ra[1], "winner_b": rb[1],
                       "same_stimulus": ra[0] == rb[0], "same_winner": ra[1] == rb[1]})
    return diffs


def reset_boundary(condition="p6d_reset", reset_idx=15):
    rows = frames_for(condition)
    before = [r[1] for r in rows[:reset_idx]]
    after = [r[1] for r in rows[reset_idx:]]
    hits_before = sum(1 for i in range(1, len(before)) if before[i] == before[i - 1])
    hits_after = sum(1 for i in range(1, len(after)) if after[i] == after[i - 1])
    cross_boundary_same = (before[-1] == after[0]) if before and after else None
    return {
        "before_repeat_rate": hits_before / max(1, len(before) - 1),
        "after_repeat_rate": hits_after / max(1, len(after) - 1),
        "boundary_frame_before": before[-1] if before else None,
        "boundary_frame_after": after[0] if after else None,
        "cross_boundary_repeat": cross_boundary_same,
    }


if __name__ == "__main__":
    report = {}

    # E: impulse response — state(G3) trajectory
    traj = state_trajectory("p6d_impulse", "G3")
    report["E_impulse_response_G3"] = [{"frame": i, "state": v} for i, (_, v, _) in enumerate(traj)]

    # B/C vs baseline: repeat-win rates
    for cond in ("p6d_baseline", "p6d_frozen", "p6d_shuffle"):
        h, t, r = repeat_win_rate(cond)
        report[f"repeat_win_{cond}"] = {"hits": h, "total": t, "rate": r}

    # D: reset boundary
    report["D_reset_boundary"] = reset_boundary()

    # F: decay sweep repeat-win rates
    report["F_decay_sweep"] = {}
    for lam_key in ("p6d_decay_01", "p6d_decay_05", "p6d_decay_09"):
        h, t, r = repeat_win_rate(lam_key)
        report["F_decay_sweep"][lam_key] = {"hits": h, "total": t, "rate": r}

    # A: counterfactual
    report["A_counterfactual"] = cf_compare()

    print(json.dumps(report, indent=2, default=str))
