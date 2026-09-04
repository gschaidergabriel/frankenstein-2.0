"""P6d — recurrent GRID10 cell-state dynamics with decay: mechanism + DB replay.

RECONSTRUCTION, not recovered original. The P6d experiment that produced the 231
`f2_grid10_frame` rows (`experiment_condition LIKE 'p6d_%'`) and the 90
`f2_grid10_p6d_state` rows tagged `cohort='CONTROLLED_PROBE'` in the real
`unified.db` was run from a script that only ever existed in `/tmp/p6d-work`
and on git branch `self-integration/wp1207-p6b-doc-and-state-test-20260904`,
which no longer exists anywhere (local, remote, dangling — all checked, gone).
This module rebuilds the mechanism from:
  - `PREREG_P6D_20260904.md` (self-integration repo, commit 75cb4ad) — the
    formula and the six preregistered test definitions, written before any run.
  - `log/2026-09-04-028-p6d-recurrent-dynamics-results.md` (self-integration
    repo, commit d62a776) — what the run actually did, including two bugs
    found and fixed mid-run/mid-analysis.
  - Direct inspection of the surviving DB rows.

Two functionally distinct halves live here:

1. `state_update` / `proposal_score` / `replay_condition_from_db` — the exact
   preregistered recursion, driven by facts already recorded per-frame in the
   real DB (`broadcast_winner_cell`, `broadcast_value`, and per-cell `uptake`/
   `conflict_flag` in `f2_grid10_cell_observation`). This half needed no
   guessing: replaying it against the real 231 frames reproduces the results
   doc's numbers exactly (see p6d_analyze.py and the results note next to
   this file). This is the part that matters for closing WP-1207's evidence
   gap.

2. `derive_signal` / `simulate_condition` — a generative simulator that could
   produce a NEW run from scratch, for future reruns (e.g. a properly powered
   F-criterion sweep). `derive_signal`'s sha256-to-float mapping is a
   REASONABLE GUESS at "deterministic pseudo-random value in [0,1) derived
   from sha256(turn_event_id:cell:signal)" (the prereg's own words) — the
   exact byte-level recipe used by the lost original is not recoverable, and
   this guess is NOT verified against the stored data (the stored data does
   not expose non-winning cells' raw signal values, only the derived
   winner/uptake/conflict/broadcast facts used by half 1). Treat `simulate_*`
   output as a mechanism sanity-check and a template for future runs, not as
   a bit-exact reproduction of the original generation.

No semantic cell-role naming: G1..G10 stay opaque throughout, per house
convention already followed in the original P6b/P6c/P6d work.
"""
from __future__ import annotations

import hashlib
import random
import sqlite3
from dataclasses import dataclass, field
from math import tanh
from typing import Callable, Iterable

CELLS: tuple[str, ...] = tuple(f"G{i}" for i in range(1, 11))

# Primary parameters, fixed in PREREG_P6D_20260904.md before any run.
LAMBDA_PRIMARY = 0.7
ALPHA = 0.4
BETA = 0.4
GAMMA = 0.3
KAPPA = 0.6

# Decay-sweep lambdas (test 5), alpha/beta/gamma/kappa held at primary values.
DECAY_SWEEP_LAMBDAS: dict[str, float] = {
    "p6d_decay_01": 0.1,
    "p6d_decay_05": 0.5,
    "p6d_decay_09": 0.9,
}

# Condition -> lambda, for replay. Everything not in DECAY_SWEEP_LAMBDAS uses
# the primary lambda (baseline/frozen/shuffle/reset/impulse/cf_a/cf_b).
def lambda_for_condition(condition_key: str) -> float:
    return DECAY_SWEEP_LAMBDAS.get(condition_key, LAMBDA_PRIMARY)


# Stimulus tag cycle observed in the real turn_event_ids
# ("p6d:<condition_key>:<tag>:<frame_index>"), 10 tags repeating.
STIMULUS_TAGS: tuple[str, ...] = (
    "short_a",
    "short_b",
    "long_context_a",
    "long_context_b",
    "retrieval_hit_a",
    "retrieval_miss_a",
    "known_topic_a",
    "unknown_topic_a",
    "ambiguous_a",
    "repeat_a",
)


# --------------------------------------------------------------------------
# Half 1: the preregistered recursion itself (verified against real DB data)
# --------------------------------------------------------------------------


def state_update(
    state: float,
    uptake: float,
    broadcast: float,
    conflict: float,
    lam: float = LAMBDA_PRIMARY,
    alpha: float = ALPHA,
    beta: float = BETA,
    gamma: float = GAMMA,
) -> float:
    """state(t+1) = lambda*state(t) + alpha*uptake(t) + beta*broadcast(t) - gamma*conflict(t)."""
    return lam * state + alpha * uptake + beta * broadcast - gamma * conflict


def proposal_score(signal: float, state: float, kappa: float = KAPPA) -> float:
    """proposal_score(t+1) = signal(t+1) + kappa*tanh(state(t+1))."""
    return signal + kappa * tanh(state)


@dataclass
class ReplayResult:
    condition_key: str
    lam: float
    frame_ids: list[str] = field(default_factory=list)
    winners: list[str] = field(default_factory=list)
    broadcast_values: list[float] = field(default_factory=list)
    # per-cell state AFTER each frame's update, in frame order
    state_trajectory: dict[str, list[float]] = field(default_factory=dict)
    # runtime_epoch_id per frame, in frame order (for epoch-boundary-aware analysis)
    epoch_ids: list[str] = field(default_factory=list)


def replay_condition_from_db(
    conn: sqlite3.Connection, condition_key: str, lam: float | None = None
) -> ReplayResult:
    """Replay the state(t+1) recursion for one condition using ONLY facts
    already stored in the real DB for the real 231 P6d frames:
    `f2_grid10_frame.broadcast_winner_cell` / `.broadcast_value` /
    `.runtime_epoch_id`, and per-cell `uptake` / `conflict_flag` from
    `f2_grid10_cell_observation`.

    Read-only: caller must open `conn` against a `mode=ro` URI or an
    otherwise read-only connection. This function issues SELECT only.

    Initial state for every cell is 0.0 (prereg: "no history ever
    accumulates" before frame 0). This matches the results doc's own replay
    method: "the impulse decay curve had to be reconstructed by replaying
    the deterministic recursion from the ordered frame/winner log, not read
    directly" (the state table is an upsert, current-value-only).
    """
    if lam is None:
        lam = lambda_for_condition(condition_key)

    frames = conn.execute(
        """
        SELECT frame_id, runtime_epoch_id, broadcast_winner_cell, broadcast_value
        FROM f2_grid10_frame
        WHERE experiment_condition = ?
        ORDER BY rowid
        """,
        (condition_key,),
    ).fetchall()

    result = ReplayResult(
        condition_key=condition_key,
        lam=lam,
        state_trajectory={c: [] for c in CELLS},
    )
    state = {c: 0.0 for c in CELLS}

    for frame_id, epoch_id, winner, broadcast_value in frames:
        obs = conn.execute(
            """
            SELECT logical_cell_id, uptake, conflict_flag
            FROM f2_grid10_cell_observation
            WHERE frame_id = ?
            """,
            (frame_id,),
        ).fetchall()
        obs_map = {cell: (uptake, conflict_flag) for cell, uptake, conflict_flag in obs}

        new_state: dict[str, float] = {}
        for cell in CELLS:
            uptake, conflict_flag = obs_map.get(cell, (0, 0))
            # "only the winning cell's own state receives the broadcast term
            # directly" — PREREG_P6D_20260904.md, broadcast(t) definition.
            broadcast = float(broadcast_value) if cell == winner else 0.0
            new_state[cell] = state_update(
                state[cell],
                float(uptake),
                broadcast,
                float(conflict_flag),
                lam=lam,
            )
            result.state_trajectory[cell].append(new_state[cell])
        state = new_state

        result.frame_ids.append(frame_id)
        result.winners.append(winner)
        result.broadcast_values.append(float(broadcast_value))
        result.epoch_ids.append(epoch_id)

    return result


def open_readonly(db_path: str) -> sqlite3.Connection:
    """Open unified.db strictly read-only. Never call .commit()/write SQL
    through a connection returned here — mode=ro makes writes raise, this
    is belt-and-suspenders so a reconstruction bug can't touch the 231 real
    frames / 90 real state rows this module reads."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only = ON;")
    return conn


# --------------------------------------------------------------------------
# Half 2: generative simulator (best-effort mechanism reconstruction, for
# FUTURE reruns — not used to touch real data in this reconstruction task)
# --------------------------------------------------------------------------


def derive_signal(turn_event_id: str, cell: str) -> float:
    """Best-effort reconstruction of "deterministic pseudo-random value in
    [0,1) derived from sha256(turn_event_id:cell:signal)" (prereg's exact
    words, describing a mechanism shared with P6b/P6c). The P6b/P6c code
    that would pin down the exact byte-slice-to-float recipe is also lost
    (checked: never committed anywhere in this repo or self-integration).

    This is ONE reasonable implementation of that description (first 8 hex
    chars of the digest as an unsigned int, scaled to [0,1)) — NOT verified
    bit-identical to the original, because the stored DB data only exposes
    winner/uptake/conflict/broadcast_value (already-resolved outcomes), not
    raw per-cell signal values for non-winning cells to check against.
    """
    digest = hashlib.sha256(f"{turn_event_id}:{cell}:signal".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 2**32


@dataclass
class SimulatedFrame:
    turn_event_id: str
    winner: str
    broadcast_value: float
    uptake: dict[str, int]
    conflict: dict[str, int]
    proposal_scores: dict[str, float]


def simulate_condition(
    condition_key: str,
    n_frames: int,
    lam: float = LAMBDA_PRIMARY,
    forced_uptake: dict[int, str] | None = None,
    freeze_state: bool = False,
    shuffle_state: bool = False,
    reset_at: int | None = None,
    rng_seed: int = 0,
) -> list[SimulatedFrame]:
    """Generate a NEW synthetic run of `n_frames` for `condition_key`, using
    `derive_signal` + the same recursion as `state_update`/`proposal_score`.

    This does NOT write to any database. It is a mechanism check / template
    for a future properly-powered rerun (e.g. multiple seeds per lambda for
    the F criterion). `forced_uptake` maps a 0-indexed frame number to a
    cell that is force-declared the winner that frame (used for the impulse
    test's frame-0 injection and the counterfactual's history-divergence
    injections) — this mirrors the prereg's "experimenter-injected event,
    not organically won" language, exactly as validated against the real
    impulse-condition replay (frame 0: forced winner G3, uptake(G3)=1,
    broadcast=that frame's own proposal_score -> state(G3) becomes 0.8,
    matching the results doc precisely; see p6d_analyze.py output).
    """
    forced_uptake = forced_uptake or {}
    rng = random.Random(rng_seed)
    state = {c: 0.0 for c in CELLS}
    frames: list[SimulatedFrame] = []

    for i in range(n_frames):
        tag = STIMULUS_TAGS[i % len(STIMULUS_TAGS)]
        turn_event_id = f"p6d:{condition_key}:{tag}:{i}"

        signals = {c: derive_signal(turn_event_id, c) for c in CELLS}
        scores = {c: proposal_score(signals[c], state[c]) for c in CELLS}

        if i in forced_uptake:
            winner = forced_uptake[i]
            scores[winner] = max(scores[winner], max(scores.values()) + 1e-6)
        else:
            winner = max(scores, key=lambda c: scores[c])

        broadcast_value = scores[winner]
        uptake = {c: (1 if c == winner else 0) for c in CELLS}
        conflict = {
            c: (1 if (c != winner and abs(scores[c] - broadcast_value) <= 0.05) else 0)
            for c in CELLS
        }

        frames.append(
            SimulatedFrame(
                turn_event_id=turn_event_id,
                winner=winner,
                broadcast_value=broadcast_value,
                uptake=uptake,
                conflict=conflict,
                proposal_scores=dict(scores),
            )
        )

        if reset_at is not None and i == reset_at:
            state = {c: 0.0 for c in CELLS}
        elif freeze_state:
            pass  # state never updates ("frozen" condition, test 2)
        else:
            new_state = {}
            for c in CELLS:
                broadcast = broadcast_value if c == winner else 0.0
                new_state[c] = state_update(state[c], uptake[c], broadcast, conflict[c], lam=lam)
            if shuffle_state:
                values = list(new_state.values())
                rng.shuffle(values)
                new_state = dict(zip(CELLS, values))
            state = new_state

    return frames


def _cli() -> None:
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)

    p_replay = sub.add_parser("replay", help="replay one condition from the real DB (read-only)")
    p_replay.add_argument("--db", required=True, help="path to unified.db")
    p_replay.add_argument("--condition", required=True)

    p_sim = sub.add_parser("simulate", help="generate a synthetic run (no DB writes)")
    p_sim.add_argument("--condition", required=True)
    p_sim.add_argument("--n-frames", type=int, default=20)
    p_sim.add_argument("--lambda", dest="lam", type=float, default=LAMBDA_PRIMARY)

    args = parser.parse_args()

    if args.mode == "replay":
        conn = open_readonly(args.db)
        result = replay_condition_from_db(conn, args.condition)
        out = {
            "condition_key": result.condition_key,
            "lambda": result.lam,
            "n_frames": len(result.frame_ids),
            "winners": result.winners,
            "state_trajectory": result.state_trajectory,
        }
        json.dump(out, sys.stdout, indent=2)
        print()
    else:
        frames = simulate_condition(args.condition, args.n_frames, lam=args.lam)
        out = [
            {
                "turn_event_id": f.turn_event_id,
                "winner": f.winner,
                "broadcast_value": f.broadcast_value,
            }
            for f in frames
        ]
        json.dump(out, sys.stdout, indent=2)
        print()


if __name__ == "__main__":
    _cli()
