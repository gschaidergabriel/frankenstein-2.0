#!/usr/bin/env python3
"""F2-WP-1207 P5a/P5b: Audit- und Nullmodell-/Permutationspipeline gegen
f2_grid10_frame/f2_grid10_cell_observation in der echten UnifiedDB.
Read-only. Keine Zellnamen, nur G1..G10."""
import sqlite3
import statistics
import itertools
import random

DB = "/home/ai-core-node/.local/share/agentzero/unified.db"

def load():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT o.frame_id, o.logical_cell_id, o.uptake, o.reentry_flag, "
        "       o.conflict_flag, o.timing_ms, o.cpu_ru_utime_delta_s, o.rss_delta_kb, "
        "       f.cohort, f.runtime_epoch_id "
        "FROM f2_grid10_cell_observation o JOIN f2_grid10_frame f ON f.frame_id=o.frame_id"
    ).fetchall()
    con.close()
    return rows

def coverage_report(rows):
    frames = {}
    for r in rows:
        frames.setdefault(r["frame_id"], set()).add(r["logical_cell_id"])
    incomplete = [fid for fid, cells in frames.items() if len(cells) != 10]
    return len(frames), incomplete

def per_cell_stats(rows, field):
    by_cell = {}
    for r in rows:
        by_cell.setdefault(r["logical_cell_id"], []).append(r[field])
    out = {}
    for cell, vals in by_cell.items():
        vals = [v for v in vals if v is not None]
        if not vals:
            continue
        out[cell] = {
            "n": len(vals), "mean": round(statistics.fmean(vals), 8),
            "stdev": round(statistics.pstdev(vals), 8) if len(vals) > 1 else 0.0,
            "min": min(vals), "max": max(vals),
        }
    return out

def permutation_test_variance(rows, field, n_perm=2000, seed=42):
    """Nullmodell: wenn logical_cell_id KEIN echtes Signal traegt, sollte die
    Varianz der Cell-Mittelwerte nicht groesser sein als bei zufaellig
    permutierten Zell-Labels. p = Anteil permutierter Varianzen >= echte Varianz."""
    vals = [(r["logical_cell_id"], r[field]) for r in rows if r[field] is not None]
    if len(vals) < 20:
        return {"error": "zu wenig Datenpunkte fuer sinnvollen Permutationstest", "n": len(vals)}
    labels = [v[0] for v in vals]
    data = [v[1] for v in vals]

    def variance_of_cell_means(lbls, dat):
        by = {}
        for l, d in zip(lbls, dat):
            by.setdefault(l, []).append(d)
        means = [statistics.fmean(v) for v in by.values() if v]
        return statistics.pvariance(means) if len(means) > 1 else 0.0

    real_var = variance_of_cell_means(labels, data)
    rng = random.Random(seed)
    perm_vars = []
    shuffled_labels = list(labels)
    for _ in range(n_perm):
        rng.shuffle(shuffled_labels)
        perm_vars.append(variance_of_cell_means(shuffled_labels, data))
    ge = sum(1 for pv in perm_vars if pv >= real_var)
    p = ge / n_perm
    return {
        "n_datapoints": len(vals), "real_variance_of_cell_means": round(real_var, 10),
        "n_permutations": n_perm, "p_value": round(p, 4),
        "perm_var_mean": round(statistics.fmean(perm_vars), 10),
    }

def stability_across_epochs(rows, field):
    """Bleiben Zell-Rangfolgen (nach Mittelwert) ueber verschiedene
    RuntimeEpochs stabil, oder ist die Reihenfolge instabil (=> vermutlich
    Rauschen)?"""
    by_epoch = {}
    for r in rows:
        by_epoch.setdefault(r["runtime_epoch_id"], []).append(r)
    rankings = {}
    for epoch, ep_rows in by_epoch.items():
        stats = per_cell_stats(ep_rows, field)
        if len(stats) < 3:
            continue
        ranking = sorted(stats.keys(), key=lambda c: stats[c]["mean"])
        rankings[epoch[:10]] = ranking
    return rankings

if __name__ == "__main__":
    rows = load()
    n_frames, incomplete = coverage_report(rows)
    print(f"=== COVERAGE ===\nFrames: {n_frames}, unvollstaendig (nicht 10 Zellen): {len(incomplete)}")
    print(f"Cell-Observation-Zeilen gesamt: {len(rows)}")

    by_cohort = {}
    for r in rows:
        by_cohort.setdefault(r["cohort"], 0)
        by_cohort[r["cohort"]] += 1
    print(f"\n=== KOHORTEN (Zeilen) === {by_cohort}")

    for field in ["uptake", "reentry_flag", "conflict_flag", "timing_ms",
                  "cpu_ru_utime_delta_s", "rss_delta_kb"]:
        print(f"\n=== PER-CELL STATS: {field} ===")
        stats = per_cell_stats(rows, field)
        for cell in sorted(stats, key=lambda c: int(c[1:])):
            print(f"  {cell}: {stats[cell]}")

        print(f"  -- Permutationstest ({field}) --")
        pt = permutation_test_variance(rows, field)
        print(f"  {pt}")

    print("\n=== REENTRY-STABILITAET (Ranking nach Mittelwert je Epoche, timing_ms) ===")
    rankings = stability_across_epochs(rows, "timing_ms")
    for epoch, ranking in rankings.items():
        print(f"  Epoche {epoch}...: {ranking}")
