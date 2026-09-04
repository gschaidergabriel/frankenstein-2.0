"""F2-WP-1207 P7 -- additive, shadow-gated GRID10 internal coordination cycle.

Roadmap position: "P7 -- GRID10 wird Koordinationsschicht statt Logger. Wenn
Zellwirkungen kausal bestaetigt sind: echter Frame-Lifecycle TypedEntry ->
GRID10 competition -> selection -> uptake -> v1 processing -> reentry.
Wichtig: zunaechst KEINE direkte Aussenwirkung -- GRID10 koordiniert intern,
EffectGate bleibt getrennt." (Gabriel, F2-WP-1207 P5-P13 roadmap.)

This module wires exactly that cycle -- proposals -> competition -> selection
-> broadcast -> uptake -> recurrent state update -> next-turn reentry -- for
one already-identified real turn (frame_id/turn_event_id/runtime_epoch_id
supplied by the caller; this module does not create GRID10 frames itself,
that stays the job of the existing P4 frame-lifecycle code). It is additive
and shadow/live-gated end to end:

- Gate: ``p7_active()`` follows the SAME pattern as the P0 shadow gate
  (``_f2wp1207_shadow_aktiv`` in frankenstein-repo/scripts/stern.py): an
  env-var override (``STERN_F2WP1207_P7_LIVE``, checked fresh every call, "0"
  or "1" wins outright) falls back to a persistent ``star_konfig`` key
  (``f2wp1207.p7_active``), default OFF ("0" / missing).
- When the gate is closed, ``coordinate_real_turn`` returns ``None``
  immediately, before any read or write -- zero added DB I/O, zero added log
  lines, zero behavioral delta versus not having this module at all.
- When open, one coordination cycle runs entirely inside the existing
  ``f2_grid10_p6d_state`` table (no new table, no schema migration) under a
  single new, reserved ``condition_key`` (``P7_LIVE_CONDITION_KEY``) that
  does not collide with any existing sweep/probe condition_key
  (p6d_baseline/p6d_cf_a/p6d_cf_b/p6d_decay_01/05/09/p6d_impulse/p6d_reset/
  p6d_shuffle/sw00/sw025/sw05/sw075/sw075_frozen/sw075_shuffle/sw10, checked
  against the live table at design time).
- Cells stay opaque G1..G10 throughout -- no semantic role naming.
- No Effects, no EffectGate call of any kind -- this module only reads/writes
  ``f2_grid10_p6d_state`` and appends to a caller-supplied evidence log.

Recurrent-state formula: reused, not reinvented. ``state_update`` /
``proposal_score`` and their accepted primary parameters (LAMBDA_PRIMARY=0.7,
ALPHA=0.4, BETA=0.4, GAMMA=0.3, KAPPA=0.6) are copied verbatim from
``workpackages/evidence_inbox/F2-WP-1207/p6d_recurrent_dynamics/p6d_runner.py``
(the accepted P6d mechanism, preregistered in PREREG_P6D_20260904.md,
reconstructed at commit 283b217 on the separate, not-yet-merged branch
``self-integration/wp1207-p6d-runner-reconstruction-20260904`` -- a different
agent's in-flight workpackage, paket-1788513679806-e244c6, explicitly out of
scope for this task). This module reads that file for reference/citation
only and copies the two pure formula functions inline rather than importing
it, deliberately: importing across an unmerged branch's not-yet-landed,
evidence_inbox-scoped file would create a live dependency this module cannot
safely rely on being present. The winner-take-uptake / margin-based-conflict
rule (0.05 margin) is the same rule ``p6d_runner.py`` uses in its own
``simulate_condition`` (documented there as "a template for future runs").

Persistence convention: plain ``sqlite3.Connection`` supplied by the caller
(no path resolution, no second database opened here) -- the same convention
GRID10 tables have always used in stern.py and in p6d_runner.py, not the
heavier WP-206 ``CanonicalPersistentAgencyStore`` (that store guards a
different, unrelated table family).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from math import tanh
from pathlib import Path
from typing import Mapping

CELLS: tuple[str, ...] = tuple(f"G{i}" for i in range(1, 11))

# Copied from p6d_runner.py (PREREG_P6D_20260904.md primary parameters) --
# see module docstring for provenance. Keep numerically identical to that
# file; do not retune independently of a new preregistration.
LAMBDA_PRIMARY = 0.7
ALPHA = 0.4
BETA = 0.4
GAMMA = 0.3
KAPPA = 0.6
CONFLICT_MARGIN = 0.05

P7_SCHEMA = "F2WP1207_GRID10_P7_COORDINATION/v1"
P7_STATE_ROW_SCHEMA = "F2WP1207_GRID10_P6D_STATE/v1"  # reuses existing table's own schema tag
P7_TRANSITION_LOG_SCHEMA = "F2WP1207_P7_STATE_TRANSITION/v1"

# Reserved condition_key for the live (real-turn) P7 coordination cycle.
# Distinct from every historical p6d_*/sw* sweep condition_key already
# present in f2_grid10_p6d_state / f2_grid10_sweep_state.
P7_LIVE_CONDITION_KEY = "f2wp1207_p7_live"

ENV_OVERRIDE = "STERN_F2WP1207_P7_LIVE"
KONFIG_KEY = "f2wp1207.p7_active"


class Grid10P7CoordinationError(RuntimeError):
    """Fail-closed P7 coordination error."""


def _jetzt_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# --------------------------------------------------------------------------
# Gate -- same pattern as _f2wp1207_shadow_aktiv() in stern.py
# --------------------------------------------------------------------------


def p7_active(conn: sqlite3.Connection, *, env: Mapping[str, str] | None = None) -> bool:
    """Env override wins outright ("0"/"1"); else the persistent
    ``star_konfig`` flag, default OFF. Read fresh every call, same as the
    P0 gate -- no caching, callers may run as long-lived processes."""
    environ = env if env is not None else os.environ
    override = environ.get(ENV_OVERRIDE)
    if override in ("0", "1"):
        return override == "1"
    try:
        row = conn.execute(
            "SELECT wert FROM star_konfig WHERE schluessel=?", (KONFIG_KEY,)
        ).fetchone()
    except sqlite3.Error:
        return False
    return (row[0] if row else "0") == "1"


def set_p7_active(conn: sqlite3.Connection, active: bool, *, quelle: str) -> None:
    """Persistent flip, mirroring stern.py's ``_konfig_dyn_set`` upsert.
    Callers doing isolated testing should prefer the env override above and
    never call this against the real unified.db -- see module docstring /
    task rollback notes."""
    conn.execute(
        "INSERT INTO star_konfig (schluessel, wert, typ, quelle, geaendert) VALUES (?,?,?,?,?) "
        "ON CONFLICT(schluessel) DO UPDATE SET wert=excluded.wert, quelle=excluded.quelle, "
        "geaendert=excluded.geaendert",
        (KONFIG_KEY, "1" if active else "0", "str", quelle, datetime.now(timezone.utc).timestamp()),
    )
    conn.commit()


# --------------------------------------------------------------------------
# Pure mechanism -- no I/O, independently testable
# --------------------------------------------------------------------------


def derive_signal(turn_event_id: str, cell_id: str) -> float:
    """Deterministic pseudo-random value in [0,1), same recipe as
    p6d_runner.py's ``derive_signal``: first 8 hex chars of
    sha256(turn_event_id:cell:signal), scaled to [0,1)."""
    digest = hashlib.sha256(f"{turn_event_id}:{cell_id}:signal".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 2**32


def proposal_score(signal: float, state: float, *, kappa: float = KAPPA) -> float:
    """proposal_score = signal + kappa * tanh(state)."""
    return signal + kappa * tanh(state)


def state_update(
    state: float,
    uptake: float,
    broadcast: float,
    conflict: float,
    *,
    lam: float = LAMBDA_PRIMARY,
    alpha: float = ALPHA,
    beta: float = BETA,
    gamma: float = GAMMA,
) -> float:
    """state(t+1) = lambda*state(t) + alpha*uptake(t) + beta*broadcast(t) - gamma*conflict(t)."""
    return lam * state + alpha * uptake + beta * broadcast - gamma * conflict


@dataclass(frozen=True)
class RealTurn:
    """Identity of the already-created GRID10 frame this coordination cycle
    runs for. This module never mints frame_id/turn_event_id itself -- those
    come from the existing P4 frame-lifecycle write."""

    frame_id: str
    turn_event_id: str
    runtime_epoch_id: str
    session_id: str


@dataclass(frozen=True)
class CellTransition:
    cell_id: str
    signal: float
    old_state: float
    proposal_score: float
    uptake: int
    conflict: int
    broadcast_term: float
    lambda_term: float
    alpha_term: float
    beta_term: float
    gamma_term: float
    new_state: float


@dataclass(frozen=True)
class P7CoordinationResult:
    schema: str
    turn: RealTurn
    condition_key: str
    winner_cell_id: str
    broadcast_value: float
    transitions: tuple[CellTransition, ...] = field(default_factory=tuple)


def run_coordination_cycle(
    turn: RealTurn, prior_state: Mapping[str, float]
) -> P7CoordinationResult:
    """Pure: proposals -> competition -> selection -> broadcast -> uptake ->
    recurrent state update. No DB, no filesystem. ``prior_state`` maps
    cell_id -> state_value; missing cells default to 0.0 (matches
    p6d_runner's replay convention: "no history ever accumulates" before the
    first frame of a condition)."""
    signals = {cell: derive_signal(turn.turn_event_id, cell) for cell in CELLS}
    states = {cell: float(prior_state.get(cell, 0.0)) for cell in CELLS}
    scores = {cell: proposal_score(signals[cell], states[cell]) for cell in CELLS}

    winner = max(scores, key=lambda c: scores[c])
    broadcast_value = scores[winner]

    transitions: list[CellTransition] = []
    for cell in CELLS:
        uptake = 1 if cell == winner else 0
        conflict = (
            1
            if (cell != winner and abs(scores[cell] - broadcast_value) <= CONFLICT_MARGIN)
            else 0
        )
        broadcast_term = broadcast_value if cell == winner else 0.0
        old_state = states[cell]
        lambda_term = LAMBDA_PRIMARY * old_state
        alpha_term = ALPHA * uptake
        beta_term = BETA * broadcast_term
        gamma_term = GAMMA * conflict
        new_state = lambda_term + alpha_term + beta_term - gamma_term
        transitions.append(
            CellTransition(
                cell_id=cell,
                signal=signals[cell],
                old_state=old_state,
                proposal_score=scores[cell],
                uptake=uptake,
                conflict=conflict,
                broadcast_term=broadcast_term,
                lambda_term=lambda_term,
                alpha_term=alpha_term,
                beta_term=beta_term,
                gamma_term=gamma_term,
                new_state=new_state,
            )
        )

    return P7CoordinationResult(
        schema=P7_SCHEMA,
        turn=turn,
        condition_key=P7_LIVE_CONDITION_KEY,
        winner_cell_id=winner,
        broadcast_value=broadcast_value,
        transitions=tuple(transitions),
    )


# --------------------------------------------------------------------------
# I/O -- plain sqlite3.Connection supplied by the caller, existing tables only
# --------------------------------------------------------------------------


def read_prior_state(conn: sqlite3.Connection, condition_key: str) -> dict[str, float]:
    rows = conn.execute(
        "SELECT logical_cell_id, state_value FROM f2_grid10_p6d_state WHERE condition_key=?",
        (condition_key,),
    ).fetchall()
    return {cell_id: float(state_value) for cell_id, state_value in rows}


def persist_coordination_result(conn: sqlite3.Connection, result: P7CoordinationResult) -> None:
    """Single transaction, one UPSERT per cell into the existing
    f2_grid10_p6d_state table (PK condition_key/logical_cell_id) -- same
    upsert shape stern.py already uses for f2_grid10_cell_state."""
    ts = _jetzt_iso()
    conn.execute("BEGIN")
    try:
        for transition in result.transitions:
            conn.execute(
                "INSERT INTO f2_grid10_p6d_state "
                "(condition_key, logical_cell_id, state_value, updated_at, "
                " updated_by_frame_id, won_broadcast_count, schema) "
                "VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(condition_key, logical_cell_id) DO UPDATE SET "
                "state_value=excluded.state_value, updated_at=excluded.updated_at, "
                "updated_by_frame_id=excluded.updated_by_frame_id, "
                "won_broadcast_count=won_broadcast_count + (CASE WHEN ?=? THEN 1 ELSE 0 END)",
                (
                    result.condition_key,
                    transition.cell_id,
                    transition.new_state,
                    ts,
                    result.turn.frame_id,
                    1 if transition.cell_id == result.winner_cell_id else 0,
                    P7_STATE_ROW_SCHEMA,
                    transition.cell_id,
                    result.winner_cell_id,
                ),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def append_transition_log(evidence_path: Path, result: P7CoordinationResult) -> None:
    """Append one JSON line describing the full state transition -- which
    frame/condition/turn, old->new state per cell, and every formula term
    that contributed -- for later audit/replay. Caller supplies the sink
    path explicitly; this module never assumes or hardcodes a cross-repo
    runtime path (the live stern.py evidence stream lives in a different
    repository and is out of this task's scope)."""
    line = {
        "schema": P7_TRANSITION_LOG_SCHEMA,
        "ts": _jetzt_iso(),
        "frame_id": result.turn.frame_id,
        "turn_event_id": result.turn.turn_event_id,
        "runtime_epoch_id": result.turn.runtime_epoch_id,
        "session_id": result.turn.session_id,
        "condition_key": result.condition_key,
        "winner_cell_id": result.winner_cell_id,
        "broadcast_value": result.broadcast_value,
        "transitions": [
            {
                "cell_id": t.cell_id,
                "signal": t.signal,
                "old_state": t.old_state,
                "proposal_score": t.proposal_score,
                "uptake": t.uptake,
                "conflict": t.conflict,
                "broadcast_term": t.broadcast_term,
                "lambda_term": t.lambda_term,
                "alpha_term": t.alpha_term,
                "beta_term": t.beta_term,
                "gamma_term": t.gamma_term,
                "new_state": t.new_state,
            }
            for t in result.transitions
        ],
    }
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    with open(evidence_path, "a", encoding="utf-8") as f:
        f.write(_canonical_json(line) + "\n")


# --------------------------------------------------------------------------
# Orchestration -- the single entry point a caller (e.g. a future stern.py
# call site) would invoke per real turn
# --------------------------------------------------------------------------


def coordinate_real_turn(
    conn: sqlite3.Connection,
    evidence_path: Path,
    turn: RealTurn,
    *,
    env: Mapping[str, str] | None = None,
) -> P7CoordinationResult | None:
    """Gate-checked entry point. Returns ``None`` (zero reads, zero writes,
    zero log lines) when P7 is not active -- see module docstring. When
    active: read current live state -> run the pure coordination cycle ->
    persist -> log -> return the result for the caller's own use (e.g.
    next-turn reentry is simply the next call's ``read_prior_state`` picking
    up what this call just persisted)."""
    if not p7_active(conn, env=env):
        return None
    prior_state = read_prior_state(conn, P7_LIVE_CONDITION_KEY)
    result = run_coordination_cycle(turn, prior_state)
    persist_coordination_result(conn, result)
    append_transition_log(evidence_path, result)
    return result
