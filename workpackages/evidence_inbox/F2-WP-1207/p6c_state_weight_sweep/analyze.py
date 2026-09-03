#!/usr/bin/env python3
import json, random, math
from collections import defaultdict

rows = []
for fn in ["/tmp/f2_p6c_work/sweep_results.json", "/tmp/f2_p6c_work/sweep_results_batch2.json"]:
    rows.extend(json.load(open(fn)))

by_cond = defaultdict(list)
for r in rows:
    by_cond[r["condition_key"]].append(r)

CELLS = [f"G{i}" for i in range(1, 11)]


def bootstrap_ci(vals, n=2000, seed=0):
    if not vals:
        return (float("nan"), float("nan"), float("nan"))
    rng = random.Random(seed)
    n_obs = len(vals)
    means = []
    for _ in range(n):
        sample = [vals[rng.randrange(n_obs)] for _ in range(n_obs)]
        means.append(sum(sample) / n_obs)
    means.sort()
    lo = means[int(0.025 * n)]
    hi = means[int(0.975 * n)]
    return (sum(vals) / n_obs, lo, hi)


def point_biserial_and_effect(state_vals, winner_flags):
    # state_vals, winner_flags: parallel lists (one entry per cell per frame)
    n = len(state_vals)
    if n < 3:
        return None
    mean_s = sum(state_vals) / n
    mean_w = sum(winner_flags) / n
    if mean_w in (0, 1):
        return None
    var_s = sum((s - mean_s) ** 2 for s in state_vals) / n
    if var_s == 0:
        return None
    std_s = math.sqrt(var_s)
    cov = sum((state_vals[i] - mean_s) * (winner_flags[i] - mean_w) for i in range(n)) / n
    std_w = math.sqrt(mean_w * (1 - mean_w))
    r = cov / (std_s * std_w) if std_s > 0 and std_w > 0 else 0.0
    # per-frame diff-in-means as effect size proxy (mean state of winners - mean state of losers)
    winners_state = [state_vals[i] for i in range(n) if winner_flags[i] == 1]
    losers_state = [state_vals[i] for i in range(n) if winner_flags[i] == 0]
    diffs = []
    # effect size per frame pairing isn't directly available here; use overall mean diff
    if winners_state and losers_state:
        effect = (sum(winners_state) / len(winners_state)) - (sum(losers_state) / len(losers_state))
    else:
        effect = float("nan")
    return r, effect


def repeat_rate(frames):
    # frames already sorted by epoch, order within epoch
    by_epoch = defaultdict(list)
    for f in frames:
        by_epoch[f["runtime_epoch_id"]].append(f)
    repeats, total = 0, 0
    winners_seq = []
    for ep, fl in by_epoch.items():
        w = [x["winner"] for x in fl]
        winners_seq.append(w)
        for i in range(1, len(w)):
            total += 1
            if w[i] == w[i - 1]:
                repeats += 1
    return repeats, total, winners_seq


def permutation_test_repeat(winners_seq, n_perm=2000, seed=1):
    rng = random.Random(seed)
    obs_repeats = 0
    obs_total = 0
    for w in winners_seq:
        for i in range(1, len(w)):
            obs_total += 1
            if w[i] == w[i - 1]:
                obs_repeats += 1
    if obs_total == 0:
        return None
    obs_rate = obs_repeats / obs_total
    perm_rates = []
    for _ in range(n_perm):
        pr, pt = 0, 0
        for w in winners_seq:
            wp = w[:]
            rng.shuffle(wp)
            for i in range(1, len(wp)):
                pt += 1
                if wp[i] == wp[i - 1]:
                    pr += 1
        perm_rates.append(pr / pt if pt else 0)
    p = sum(1 for x in perm_rates if x >= obs_rate) / n_perm
    return obs_rate, sum(perm_rates) / len(perm_rates), p


def transition_matrix(winners_seq):
    mat = defaultdict(lambda: defaultdict(int))
    for w in winners_seq:
        for i in range(1, len(w)):
            mat[w[i - 1]][w[i]] += 1
    return mat


print("=" * 70)
for cond in ["sw00", "sw025", "sw05", "sw075", "sw10", "sw075_shuffle", "sw075_frozen"]:
    frames = by_cond[cond]
    state_vals, winner_flags, proposal_vals = [], [], []
    for f in frames:
        w = f["winner"]
        for cell in CELLS:
            sv = f["state_before"].get(cell, 0.0)
            state_vals.append(sv)
            winner_flags.append(1 if cell == w else 0)
            proposal_vals.append(f["proposals"][cell])

    pb = point_biserial_and_effect(state_vals, winner_flags)
    r_prop = None
    n = len(state_vals)
    if n > 2:
        mean_s = sum(state_vals) / n
        mean_p = sum(proposal_vals) / n
        cov = sum((state_vals[i] - mean_s) * (proposal_vals[i] - mean_p) for i in range(n)) / n
        var_s = sum((s - mean_s) ** 2 for s in state_vals) / n
        var_p = sum((p - mean_p) ** 2 for p in proposal_vals) / n
        if var_s > 0 and var_p > 0:
            r_prop = cov / math.sqrt(var_s * var_p)

    rep, tot, wseq = repeat_rate(frames)
    perm = permutation_test_repeat(wseq)
    n_epochs = len(wseq)

    # bootstrap CI on the winner-vs-loser state diff (metric 4 effect size)
    winners_state = [state_vals[i] for i in range(n) if winner_flags[i] == 1]
    losers_state = [state_vals[i] for i in range(n) if winner_flags[i] == 0]
    diff_boot = None
    if winners_state and losers_state:
        rng = random.Random(42)
        diffs = []
        for _ in range(2000):
            ws = [winners_state[rng.randrange(len(winners_state))] for _ in range(len(winners_state))]
            ls = [losers_state[rng.randrange(len(losers_state))] for _ in range(len(losers_state))]
            diffs.append(sum(ws) / len(ws) - sum(ls) / len(ls))
        diffs.sort()
        diff_boot = (sum(winners_state) / len(winners_state) - sum(losers_state) / len(losers_state),
                     diffs[int(0.025 * 2000)], diffs[int(0.975 * 2000)])

    print(f"\n--- condition={cond} n_frames={len(frames)} n_epochs={n_epochs} ---")
    print(f"  metric3 corr(state,proposal)      r={r_prop}")
    if pb:
        print(f"  metric4 corr(state,is_winner)     r={pb[0]:.4f}  mean_diff(winner-loser)={pb[1]:.4f}")
    if diff_boot:
        print(f"  metric4 bootstrap CI (winner-loser state diff): point={diff_boot[0]:.4f} CI95=[{diff_boot[1]:.4f},{diff_boot[2]:.4f}]")
    if perm:
        print(f"  metric2 repeat-rate={perm[0]:.4f} null_mean={perm[1]:.4f} perm_p={perm[2]:.4f} (n_transitions={tot})")

print("\n" + "=" * 70)
print("Transition matrices (sw05 as example, condition with most prior data):")
_, _, wseq05 = repeat_rate(by_cond["sw05"])
tm = transition_matrix(wseq05)
for a in CELLS:
    row = [tm[a][b] for b in CELLS]
    print(a, row)
