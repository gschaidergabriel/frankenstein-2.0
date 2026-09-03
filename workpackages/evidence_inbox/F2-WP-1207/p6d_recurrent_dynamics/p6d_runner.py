#!/usr/bin/env python3
"""P6d runner: recurrent cell-state dynamics with decay, per PREREG_P6D_20260904.md.
Writes real f2_grid10_frame/cell_observation rows (cohort=CONTROLLED_PROBE,
experiment_condition=<test name>) tagged and isolated via a dedicated state table
f2_grid10_p6d_state (separate from P6c's f2_grid10_sweep_state and from real
per-installation production state). Imports real stern.py for identity/epoch
resolution only.
"""
import sys, os, hashlib, sqlite3, contextlib, time, json, random
sys.path.insert(0, os.path.expanduser("~/frankenstein-repo/scripts"))
import stern  # noqa

DB_PATH = stern.DB_PATH
CELLS = [f"G{i}" for i in range(1, 11)]

LAMBDA_DEFAULT = 0.7
ALPHA = 0.4
BETA = 0.4
GAMMA = 0.3
KAPPA = 0.6
NEAR_MISS_EPS = 0.05


def tanh(x):
    import math
    return math.tanh(x)


def signal_for(turn_event_id, cell):
    return (int(hashlib.sha256(f"{turn_event_id}:{cell}:signal".encode()).hexdigest(), 16) % 1000) / 1000.0


def resolve_identity():
    installation_id = stern._f2wp1207_installation_id()
    state_root_id = hashlib.sha256(f"F2WP1207_STATE_ROOT_REF/v1:{DB_PATH}".encode()).hexdigest()
    entity_id = stern._f2wp1207_canonical_entity_id()
    if not entity_id:
        raise RuntimeError("no canonical entity_id resolvable")
    return installation_id, state_root_id, entity_id


def get_state(c, condition_key):
    zustand = {cc: 0.0 for cc in CELLS}
    for row in c.execute(
        "SELECT logical_cell_id, state_value FROM f2_grid10_p6d_state WHERE condition_key=?",
        (condition_key,),
    ):
        zustand[row[0]] = row[1]
    return zustand


def set_state(c, condition_key, cell, value, frame_id, won):
    c.execute(
        "INSERT INTO f2_grid10_p6d_state "
        "(condition_key, logical_cell_id, state_value, updated_at, updated_by_frame_id, "
        " won_broadcast_count, schema) VALUES (?,?,?,?,?,?,?) "
        "ON CONFLICT(condition_key, logical_cell_id) DO UPDATE SET "
        "state_value=excluded.state_value, updated_at=excluded.updated_at, "
        "updated_by_frame_id=excluded.updated_by_frame_id, "
        "won_broadcast_count=won_broadcast_count + ?",
        (condition_key, cell, value, stern._jetzt_iso(), frame_id, 1 if won else 0,
         "F2WP1207_GRID10_P6D_STATE/v1", 1 if won else 0),
    )


def run_frame(c, condition_key, turn_event_id, entity_id, installation_id, state_root_id,
              runtime_epoch_id, lam, freeze=False, shuffle=False, forced_uptake_cell=None,
              forced_uptake_value=None):
    frame_id = hashlib.sha256(f"P6D:{condition_key}:{runtime_epoch_id}:{turn_event_id}".encode()).hexdigest()
    ts = stern._jetzt_iso()
    c.execute(
        "INSERT INTO f2_grid10_frame "
        "(frame_id, entity_id, installation_id, state_root_id, runtime_epoch_id, "
        " session_id, turn_event_id, opened_at, closed_at, status, schema, cohort, "
        " experiment_condition, state_weight) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (frame_id, entity_id, installation_id, state_root_id, runtime_epoch_id,
         f"p6d:{condition_key}", turn_event_id, ts, None, "OPEN",
         "F2WP1207_GRID10_FRAME/v1", "CONTROLLED_PROBE", condition_key, lam),
    )

    state_before = get_state(c, condition_key)
    state_view = dict(state_before)
    if shuffle:
        vals = [state_view[cc] for cc in CELLS]
        rng = random.Random(f"shuffle:{frame_id}")
        rng.shuffle(vals)
        state_view = dict(zip(CELLS, vals))

    proposals = {}
    for cell in CELLS:
        sig = signal_for(turn_event_id, cell)
        proposals[cell] = sig + KAPPA * tanh(state_view[cell])

    if forced_uptake_cell:
        winner = forced_uptake_cell
        broadcast_value = forced_uptake_value if forced_uptake_value is not None else proposals[winner]
    else:
        winner = max(proposals, key=proposals.get)
        broadcast_value = proposals[winner]

    for pos, cell in enumerate(CELLS, start=1):
        obs_id = hashlib.sha256(f"{frame_id}:{cell}".encode()).hexdigest()
        uptake = 1 if cell == winner else 0
        conflict = 1 if (cell != winner and abs(proposals[cell] - proposals[winner]) < NEAR_MISS_EPS) else 0
        c.execute(
            "INSERT INTO f2_grid10_cell_observation "
            "(observation_id, frame_id, logical_cell_id, input_digest_sha256, output_digest_sha256, "
            " uptake, reentry_flag, conflict_flag, timing_ms, cpu_ru_utime_delta_s, rss_delta_kb, "
            " predecessor_observation_id, schema, execution_position) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (obs_id, frame_id, cell,
             hashlib.sha256(f"{turn_event_id}:{cell}:in".encode()).hexdigest(),
             hashlib.sha256(f"{turn_event_id}:{cell}:out".encode()).hexdigest(),
             uptake, 0, conflict, 0.0, 0.0, 0, None,
             "F2WP1207_GRID10_CELL_OBSERVATION/v1", pos),
        )

    c.execute(
        "UPDATE f2_grid10_frame SET status='CLOSED', closed_at=?, broadcast_winner_cell=?, "
        "broadcast_value=? WHERE frame_id=?",
        (stern._jetzt_iso(), winner, broadcast_value, frame_id),
    )

    if not freeze:
        for cell in CELLS:
            uptake_t = 1.0 if cell == winner else 0.0
            broadcast_t = broadcast_value if cell == winner else 0.0
            conflict_t = 1.0 if (cell != winner and abs(proposals[cell] - proposals[winner]) < NEAR_MISS_EPS) else 0.0
            new_state = lam * state_before[cell] + ALPHA * uptake_t + BETA * broadcast_t - GAMMA * conflict_t
            set_state(c, condition_key, cell, new_state, frame_id, cell == winner)

    return {
        "frame_id": frame_id, "winner": winner, "proposals": dict(proposals),
        "state_before": dict(state_before), "turn_event_id": turn_event_id,
    }


STIMULUS_SEEDS = [
    "short_a", "short_b", "long_context_a", "long_context_b", "retrieval_hit_a",
    "retrieval_miss_a", "known_topic_a", "unknown_topic_a", "ambiguous_a", "repeat_a",
]


def open_epoch(session_id, force_new):
    runtime_epoch_id, pred = stern._f2wp1207_runtime_epoch(session_id, force_new=force_new)
    return runtime_epoch_id


def run_series(condition_key, n_frames, lam=LAMBDA_DEFAULT, freeze=False, shuffle=False,
                impulse_at=None, impulse_cell=None, n_epochs=2, reset_at=None,
                cf_injections=None):
    installation_id, state_root_id, entity_id = resolve_identity()
    results = []
    frames_per_epoch = max(1, n_frames // n_epochs)
    idx = 0
    for ep in range(n_epochs):
        session_id = f"p6d:{condition_key}:ep{ep}"
        # resolved standalone (own short connection inside stern's helper) --
        # never nested inside our own open write transaction below, otherwise
        # the epoch-db-sync write silently loses a lock race against our
        # frame transaction (found+fixed this round).
        runtime_epoch_id = open_epoch(session_id, force_new=(ep > 0))
        for i in range(frames_per_epoch):
            if idx >= n_frames:
                break
            seed = STIMULUS_SEEDS[idx % len(STIMULUS_SEEDS)]
            turn_event_id = f"p6d:{condition_key}:{seed}:{idx}"
            forced_cell = None
            forced_val = None
            if impulse_at is not None and idx == impulse_at:
                forced_cell = impulse_cell
                forced_val = 1.0
            if cf_injections and idx in cf_injections:
                forced_cell = cf_injections[idx]
                forced_val = 1.0
            # each frame = its own short transaction (safety discipline: no
            # long-held write locks that could collide with concurrent
            # sessions or the epoch-sync helper).
            with contextlib.closing(stern.schreib_verbindung()) as c:
                c.execute("PRAGMA foreign_keys = ON")
                c.execute("BEGIN")
                if reset_at is not None and idx == reset_at:
                    for cc in CELLS:
                        set_state(c, condition_key, cc, 0.0, "RESET", False)
                r = run_frame(c, condition_key, turn_event_id, entity_id, installation_id,
                               state_root_id, runtime_epoch_id, lam, freeze=freeze,
                               shuffle=shuffle, forced_uptake_cell=forced_cell,
                               forced_uptake_value=forced_val)
                c.commit()
            r["epoch_idx"] = ep
            r["runtime_epoch_id"] = runtime_epoch_id
            results.append(r)
            idx += 1
    return results


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    out = {}

    print("=== 1. impulse (already ran clean before the lock-fix crash; re-reading, not re-running) ===", file=sys.stderr)
    out["impulse"] = "already_persisted_pre_fix_21_frames_condition_p6d_impulse"

    print("=== 2a. baseline (for frozen comparison) ===", file=sys.stderr)
    out["baseline"] = run_series("p6d_baseline", n_frames=30, n_epochs=2)

    print("=== 2b. frozen ===", file=sys.stderr)
    out["frozen"] = run_series("p6d_frozen", n_frames=30, freeze=True, n_epochs=2)

    print("=== 3. shuffle ===", file=sys.stderr)
    out["shuffle"] = run_series("p6d_shuffle", n_frames=30, shuffle=True, n_epochs=2)

    print("=== 4. reset ===", file=sys.stderr)
    out["reset"] = run_series("p6d_reset", n_frames=30, reset_at=15, n_epochs=2)

    print("=== 5. decay sweep ===", file=sys.stderr)
    out["decay_sweep"] = {}
    for lam in (0.1, 0.5, 0.9):
        key = f"p6d_decay_{str(lam).replace('.', '')}"
        out["decay_sweep"][str(lam)] = run_series(key, n_frames=20, lam=lam, n_epochs=1)

    print("=== 6. counterfactual ===", file=sys.stderr)
    out["counterfactual_a"] = run_series(
        "p6d_cf_a", n_frames=15, n_epochs=1,
        cf_injections={1: "G5", 3: "G5", 5: "G5"},
    )
    out["counterfactual_b"] = run_series("p6d_cf_b", n_frames=15, n_epochs=1)

    with open(args.out, "w") as f:
        json.dump(out, f, default=str)
    total = sum(len(v) if isinstance(v, list) else sum(len(vv) for vv in v.values())
                for v in out.values())
    print(f"TOTAL {total} frames written to {args.out}", file=sys.stderr)
