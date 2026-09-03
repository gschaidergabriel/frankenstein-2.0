#!/usr/bin/env python3
"""P6c sweep runner. Imports real stern.py helpers (real DB_PATH, real
identity/epoch resolution, real schreib_verbindung) but writes sweep frames
via its OWN persist function (not stern.py's production
_f2wp1207_grid10_frame_persist) so the production function/state table is
never touched. No change to stern.py's function bodies for this reason.
"""
import sys, os, hashlib, random, sqlite3, contextlib, time, json
sys.path.insert(0, os.path.expanduser("~/frankenstein-repo/scripts"))
import stern  # noqa

DB_PATH = stern.DB_PATH


def resolve_identity(session_id):
    installation_id = stern._f2wp1207_installation_id()
    state_root_id = hashlib.sha256(f"F2WP1207_STATE_ROOT_REF/v1:{DB_PATH}".encode()).hexdigest()
    entity_id = stern._f2wp1207_canonical_entity_id()
    return installation_id, state_root_id, entity_id


def sweep_frame_persist(session_id, turn_event_id, entity_id, installation_id,
                         state_root_id, runtime_epoch_id, condition_key,
                         state_weight, shuffle_state=False, freeze_state=False):
    frame_id = hashlib.sha256(f"SWEEP:{condition_key}:{runtime_epoch_id}:{turn_event_id}".encode()).hexdigest()
    ts = stern._jetzt_iso()
    with contextlib.closing(stern.schreib_verbindung()) as c:
        c.execute("PRAGMA foreign_keys = ON")
        c.execute("BEGIN")
        c.execute(
            "INSERT INTO f2_grid10_frame "
            "(frame_id, entity_id, installation_id, state_root_id, runtime_epoch_id, "
            " session_id, turn_event_id, opened_at, closed_at, status, schema, cohort, "
            " experiment_condition, state_weight) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (frame_id, entity_id, installation_id, state_root_id, runtime_epoch_id,
             session_id, turn_event_id, ts, None, "OPEN", "F2WP1207_GRID10_FRAME/v1",
             "CONTROLLED_PROBE", condition_key, state_weight),
        )
        zellen = [f"G{i}" for i in range(1, 11)]
        rng = random.Random(frame_id)
        rng.shuffle(zellen)
        import resource as _resource
        ru_prev = _resource.getrusage(_resource.RUSAGE_SELF)
        for pos, cell in enumerate(zellen, start=1):
            t0 = time.monotonic()
            ru_now = _resource.getrusage(_resource.RUSAGE_SELF)
            timing_ms = round((time.monotonic() - t0) * 1000, 4)
            utime_delta = round(ru_now.ru_utime - ru_prev.ru_utime, 6)
            rss_delta = ru_now.ru_maxrss - ru_prev.ru_maxrss
            ru_prev = ru_now
            obs_id = hashlib.sha256(f"{frame_id}:{cell}".encode()).hexdigest()
            c.execute(
                "INSERT INTO f2_grid10_cell_observation "
                "(observation_id, frame_id, logical_cell_id, input_digest_sha256, "
                " output_digest_sha256, uptake, reentry_flag, conflict_flag, timing_ms, "
                " cpu_ru_utime_delta_s, rss_delta_kb, predecessor_observation_id, schema, "
                " execution_position) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (obs_id, frame_id, cell,
                 hashlib.sha256(f"{turn_event_id}:{cell}:in".encode()).hexdigest(),
                 hashlib.sha256(f"{turn_event_id}:{cell}:out".encode()).hexdigest(),
                 1, 0, 0, timing_ms, utime_delta, rss_delta, None,
                 "F2WP1207_GRID10_CELL_OBSERVATION/v1", pos),
            )
        zustand = {}
        for row in c.execute(
            "SELECT logical_cell_id, state_value FROM f2_grid10_sweep_state WHERE condition_key=?",
            (condition_key,),
        ):
            zustand[row[0]] = row[1]
        state_for_proposal = dict(zustand)
        if shuffle_state:
            vals = list(state_for_proposal.values()) or [0.0] * 10
            cells10 = [f"G{i}" for i in range(1, 11)]
            vals = [state_for_proposal.get(cc, 0.0) for cc in cells10]
            rng2 = random.Random(f"shuffle:{frame_id}")
            rng2.shuffle(vals)
            state_for_proposal = dict(zip(cells10, vals))
        vorschlaege = {}
        for cell in [f"G{i}" for i in range(1, 11)]:
            state_alt = state_for_proposal.get(cell, 0.0)
            signal = (int(hashlib.sha256(f"{turn_event_id}:{cell}:signal".encode()).hexdigest(), 16) % 1000) / 1000.0
            vorschlaege[cell] = state_weight * state_alt + (1.0 - state_weight) * signal
        gewinner = max(vorschlaege, key=vorschlaege.get)
        broadcast_wert = vorschlaege[gewinner]
        c.execute(
            "UPDATE f2_grid10_frame SET status='CLOSED', closed_at=?, "
            "broadcast_winner_cell=?, broadcast_value=? WHERE frame_id=?",
            (stern._jetzt_iso(), gewinner, broadcast_wert, frame_id),
        )
        if not freeze_state:
            for cell, vorschlag in vorschlaege.items():
                base = zustand.get(cell, 0.0)
                if cell == gewinner:
                    neuer_zustand = broadcast_wert
                else:
                    neuer_zustand = 0.9 * base + 0.1 * broadcast_wert
                c.execute(
                    "INSERT INTO f2_grid10_sweep_state "
                    "(condition_key, logical_cell_id, state_value, updated_at, "
                    " updated_by_frame_id, won_broadcast_count, schema) VALUES (?,?,?,?,?,?,?) "
                    "ON CONFLICT(condition_key, logical_cell_id) DO UPDATE SET "
                    "state_value=excluded.state_value, updated_at=excluded.updated_at, "
                    "updated_by_frame_id=excluded.updated_by_frame_id, "
                    "won_broadcast_count=won_broadcast_count + (CASE WHEN ?=? THEN 1 ELSE 0 END)",
                    (condition_key, cell, neuer_zustand, stern._jetzt_iso(), frame_id,
                     1 if cell == gewinner else 0, "F2WP1207_GRID10_SWEEP_STATE/v1",
                     cell, gewinner),
                )
        c.commit()
    return frame_id, gewinner, dict(vorschlaege), dict(zustand)


STIMULUS_SEEDS = [
    "short_a", "short_b", "long_context_a", "long_context_b", "retrieval_hit_a",
    "retrieval_miss_a", "known_topic_a", "unknown_topic_a", "ambiguous_a", "repeat_a",
]


def run_condition(condition_key, state_weight, session_prefix, n_epochs=2, frames_per_epoch=12,
                   shuffle_state=False, freeze_state=False):
    results = []
    for ep in range(n_epochs):
        session_id = f"{session_prefix}:{condition_key}:ep{ep}"
        installation_id, state_root_id, entity_id = resolve_identity(session_id)
        if not entity_id:
            raise RuntimeError("no canonical entity_id resolvable")
        runtime_epoch_id, pred = stern._f2wp1207_runtime_epoch(session_id, force_new=(ep > 0))
        for i in range(frames_per_epoch):
            seed = STIMULUS_SEEDS[i % len(STIMULUS_SEEDS)]
            turn_event_id = f"sweep:{condition_key}:{seed}:{i}"
            frame_id, winner, proposals, state_before = sweep_frame_persist(
                session_id, turn_event_id, entity_id, installation_id, state_root_id,
                runtime_epoch_id, condition_key, state_weight, shuffle_state, freeze_state,
            )
            results.append({
                "condition_key": condition_key, "epoch_idx": ep,
                "runtime_epoch_id": runtime_epoch_id, "frame_id": frame_id,
                "winner": winner, "proposals": proposals, "state_before": state_before,
                "stimulus": seed,
            })
    return results


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    conditions = [
        ("sw00", 0.0, {}),
        ("sw025", 0.25, {}),
        ("sw05", 0.5, {}),
        ("sw075", 0.75, {}),
        ("sw10", 1.0, {}),
        ("sw075_shuffle", 0.75, {"shuffle_state": True}),
        ("sw075_frozen", 0.75, {"freeze_state": True}),
    ]
    all_results = []
    for key, weight, kwargs in conditions:
        print(f"=== condition {key} weight={weight} kwargs={kwargs} ===", file=sys.stderr)
        r = run_condition(key, weight, "p6c", n_epochs=2, frames_per_epoch=12, **kwargs)
        all_results.extend(r)
        print(f"  -> {len(r)} frames", file=sys.stderr)
    with open(args.out, "w") as f:
        json.dump(all_results, f)
    print(f"TOTAL {len(all_results)} frames written to {args.out}", file=sys.stderr)
