"""F2-WP-1207 P12: real self-observation of the runtime's own technical state.

Byte-adapted mirror relationship: canonical location (this repo, this
branch); a byte-adapted copy with the real unified.db field audit and the
DB-backed gold test lives at
frankenstein-repo/scripts/f2wp1207_p12_self_observation.py -- same
relationship P7/P10/P11 already have to their own vendored copies there.

Gabriel's spec (F2-WP-1207 P5-P13 roadmap, P12), verbatim: "echte
Selbstbeobachtung der eigenen Runtime. Kette: Runtime/DB/Gates/Effects/
GRID10 -> typed self-observation -> workspace candidate -> competition ->
broadcast -> uptake -> next-turn reentry. Nicht mehr neue Aussenwelt-Effekte
bauen -- Frankenstein soll seinen eigenen technischen Zustand als typisierte
Evidenz in den Workspace einbringen, ohne daraus freie Selbstbeschreibungen
oder erfundene 'Gefuehle' abzuleiten."

Record contract (exact shape, enforced by the ``SelfObservation`` dataclass
below): ``source`` (concrete subsystem/table), ``observed_at`` (ISO ts of the
underlying EVIDENCE, not collection time -- except for synchronous checks
like DB integrity, where evidence time == collection time by construction),
``fact_type``, ``value`` (a single typed scalar: str/int/float/bool -- never
free text), ``evidence_ref`` (points back at the real row/table/query that
produced it), ``freshness_s`` (age of the evidence relative to collection
time), ``confidence`` (evidence-derived -- propagated from an existing
classifier's own confidence where one exists (P9's ``classify_predecessor``),
or set from the mechanical certainty of a direct row match / a proven
absence -- NEVER a synthesized "vibe" number).

FORBIDDEN, structurally: no fact_type/value pair may hold free text like
"Ich bin unsicher" / "Ich erinnere mich..." -- every ``_fact_*`` function
below returns a scalar drawn from a real column or a real COUNT/EXISTS
query, nothing else.

Facts implemented (all real, all independently checkable against a live
unified.db -- see the byte-adapted copy's docstring for the exact
field-by-field audit performed 2026-09-05):

  DB_INTEGRITY           -- ``PRAGMA integrity_check`` on the SAME
                             connection this collector is handed. Always
                             FRESH (synchronous, evidence_time==now).
  LAST_EFFECT_STATUS      -- most recent row in ``f2_grid10_effect_journal``
                             (global, not epoch-scoped -- "what did this
                             installation's runtime last actually do"),
                             value in {"EXECUTED","DENIED","NONE"}. This is
                             the field P11's real gate/journal mechanism
                             drives, and the primary contrastive fact for
                             the gold test.
  RUNTIME_EPOCH_CHANGED    -- whether a ``f2_reentry_record`` row exists
                             linking a real predecessor epoch to THIS
                             epoch (P9's reconciler output). value: bool.
  PREDECESSOR_TERMINATION   -- (only emitted when a reentry record exists)
                             value = the P9-classified termination reason
                             string; confidence = P9's OWN
                             ``predecessor_confidence`` for that
                             classification, propagated verbatim, never
                             re-derived.
  RETRIEVAL_HIT_COUNT        -- real, directly queryable proxy for "did the
                             last retrieval attempt find anything": most
                             recent ``retrieval_episodes`` row for this
                             session_id, value = len(selected_memory_ids).
                             (``~/.claude/star/stern.py``'s
                             ``automatischer_abruf()`` itself is read-only
                             reference material for this convention, per
                             task scope -- never imported/called; this
                             collector computes its own equivalent fact
                             directly from ``retrieval_episodes``, the real
                             table that function's MicroClay shadow path
                             already writes every turn, independent of
                             stern.py's own return-value plumbing.)
  LAST_GRID10_WINNER         -- most recent ``f2_grid10_frame`` row for this
                             installation: value = broadcast_winner_cell.
  GRID10_CONFLICT_PRESENT     -- any conflict_flag=1 row in
                             ``f2_grid10_cell_observation`` for that same
                             last frame. value: bool.
  GRID10_FRAME_FAILURE_COUNT   -- COUNT of ``f2_grid10_frame`` rows with
                             status='FAILED' for this runtime_epoch_id --
                             real column, real CHECK-constrained state,
                             genuinely queryable error signal that belongs
                             to F2WP1207's OWN schema (NOT stern.py's
                             hook.log, which is explicitly out of scope).

EXCLUDED, honestly, not invented (see EXCLUDED_FIELDS below): none of the
above facts require a new table. No genuinely new data had to be invented to
satisfy this phase's fact menu, so this module makes NO schema change at
all -- purely additive by having nothing to add.

Every ``_fact_*`` function is individually fail-closed: any sqlite3.Error or
unexpected exception is caught and that ONE fact is simply omitted from the
returned list -- never propagates, never aborts collection of the other
facts, never breaks the caller's normal turn-processing path (see
``collect_self_observations`` and ``coordinate_real_turn_with_self_
observation``).

Wiring into the P7/P10 competition chain: ``apply_self_observation`` is a
PURE function (no I/O) that takes a prior_state mapping (however it was
seeded -- cold, or P10-reconstructed) and a list of ``SelfObservation``
records, and returns an adjusted prior_state where a single scalar delta
(derived from the FRESH, evidence-backed facts only, via a documented,
epsilon-scale weight table -- same order of magnitude as P7's own
CONFLICT_MARGIN / P11's EFFECT_UPTAKE_EPSILON, not a formula-dominating
term) is added UNIFORMLY to every cell's prior state. Uniform (not
winner-targeted, not any single named cell) so this module makes no
semantic cell-role claim -- self-observation is about the runtime as a
whole, not about G<n> specifically. Because ``proposal_score`` is
``signal + kappa*tanh(state)``, a uniform additive shift to ``state`` still
changes each cell's score by a DIFFERENT amount (tanh is nonlinear) --
enough to measurably move the competition/selection, while remaining a pure
function of the typed facts (not of any live re-read of the DB during
scoring).

Staleness/validity: ``apply_self_observation`` re-derives whether each
record is trustworthy FROM SCRATCH (its own ``freshness_s`` vs a threshold)
-- it never trusts a record's own ``validity`` label at face value. A
forged record that claims ``validity="FRESH"`` but carries an old
``observed_at``/large ``freshness_s`` contributes exactly 0.0, same as a
record honestly marked STALE.
"""
from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional, Sequence

from frankenstein2.grid10_p7_coordination import (
    CELLS,
    P7_LIVE_CONDITION_KEY,
    RealTurn,
    coordinate_real_turn,
    p7_active,
    persist_coordination_result,
    read_prior_state,
    run_coordination_cycle,
)

try:  # composing with P10 reentry is optional -- degrade gracefully if absent
    from frankenstein2.grid10_p10_workspace_reentry import reconstruct_workspace
except Exception:  # pragma: no cover - defensive, mirrors other modules' style
    reconstruct_workspace = None  # type: ignore[assignment]

SCHEMA = "F2WP1207_P12_SELF_OBSERVATION/v1"
SCHEMA_LOG_LINE = "F2WP1207_P12_SELF_OBSERVATION_LOG/v1"

# Documented, checked absence -- kept as data (not just prose) so a caller/
# test can assert on it mechanically, same convention P10 established with
# its own EXCLUDED_FIELDS.
EXCLUDED_FIELDS: dict = {}

# Epsilon-scale, same order of magnitude as P7's CONFLICT_MARGIN (0.05) and
# P11's EFFECT_UPTAKE_EPSILON (0.05) -- a small, real, additive nudge, not a
# formula-dominating term. Not retuned without a new preregistration, same
# discipline as every prior phase's own tunables.
SELF_OBS_EPSILON = 0.05

# How old a fact's underlying evidence may be before it is no longer trusted
# as "current". 24h -- these are runtime-health facts, not archival record;
# a day-old "last effect status" is not a safe stand-in for "right now".
DEFAULT_STALE_THRESHOLD_S = 86400.0

# fact_type/value -> multiplier on SELF_OBS_EPSILON. Documented, exhaustive
# for the facts that carry a directly-comparable typed value; facts not
# listed here (e.g. LAST_GRID10_WINNER, PREDECESSOR_TERMINATION) are
# observational/typed workspace content but do not (yet) carry a scoring
# contribution of their own -- honestly not everything needs to move a
# number to be real self-observation.
_WEIGHTS: dict = {
    ("LAST_EFFECT_STATUS", "EXECUTED"): 1.0,
    ("LAST_EFFECT_STATUS", "DENIED"): -1.0,
    ("LAST_EFFECT_STATUS", "NONE"): 0.0,
    ("DB_INTEGRITY", "ok"): 0.0,
    ("DB_INTEGRITY", "corrupt"): -4.0,
    ("RUNTIME_EPOCH_CHANGED", True): 0.5,
    ("RUNTIME_EPOCH_CHANGED", False): 0.0,
    ("GRID10_CONFLICT_PRESENT", True): -0.5,
    ("GRID10_CONFLICT_PRESENT", False): 0.0,
}


class Grid10P12SelfObservationError(RuntimeError):
    """Fail-closed P12 self-observation error."""


def _jetzt() -> datetime:
    return datetime.now(timezone.utc)


def _jetzt_iso() -> str:
    return _jetzt().strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _parse_any_ts(value) -> Optional[datetime]:
    """Accepts an ISO-8601 string (with or without trailing 'Z') or a numeric
    unix-epoch value (int/float, or a numeric string) -- the two timestamp
    conventions actually used across the tables this module reads
    (``created_at``/``opened_at`` etc. are ISO strings; ``retrieval_episodes.
    ts`` is a REAL unix-seconds float). Returns None (never raises) on
    anything unparseable -- caller treats that as UNVERIFIED freshness."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except Exception:
            return None
    if isinstance(value, str):
        s = value.strip()
        try:
            return datetime.fromtimestamp(float(s), tz=timezone.utc)
        except ValueError:
            pass
        try:
            t = s.replace("Z", "+00:00")
            dt = datetime.fromisoformat(t)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return None
    return None


@dataclass(frozen=True)
class SelfObservation:
    schema: str
    source: str
    observed_at: Optional[str]
    fact_type: str
    value: object
    evidence_ref: str
    freshness_s: Optional[float]
    confidence: float
    validity: str  # "FRESH" | "STALE" | "UNVERIFIED"
    detail: Mapping[str, object] = field(default_factory=dict)


def _finalize(
    *, source: str, observed_at_raw, fact_type: str, value: object, evidence_ref: str,
    confidence: float, now: datetime, threshold_s: float, detail: Optional[Mapping[str, object]] = None,
) -> SelfObservation:
    observed_dt = _parse_any_ts(observed_at_raw)
    if observed_dt is None:
        return SelfObservation(
            schema=SCHEMA, source=source, observed_at=None, fact_type=fact_type, value=value,
            evidence_ref=evidence_ref, freshness_s=None, confidence=confidence, validity="UNVERIFIED",
            detail=dict(detail or {}),
        )
    freshness_s = max(0.0, (now - observed_dt).total_seconds())
    validity = "FRESH" if freshness_s <= threshold_s else "STALE"
    return SelfObservation(
        schema=SCHEMA, source=source,
        observed_at=observed_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        fact_type=fact_type, value=value, evidence_ref=evidence_ref,
        freshness_s=freshness_s, confidence=confidence, validity=validity,
        detail=dict(detail or {}),
    )


# --------------------------------------------------------------------------
# Individual fact collectors -- each fail-closed, each reads ONE real source.
# --------------------------------------------------------------------------


def _fact_db_integrity(conn: sqlite3.Connection, *, now: datetime, threshold_s: float) -> Optional[SelfObservation]:
    try:
        rows = conn.execute("PRAGMA integrity_check").fetchall()
    except sqlite3.Error:
        return None
    ok = len(rows) == 1 and str(rows[0][0]).lower() == "ok"
    value = "ok" if ok else "corrupt"
    detail = {} if ok else {"messages": [str(r[0]) for r in rows[:10]]}
    return _finalize(
        source="sqlite:PRAGMA integrity_check", observed_at_raw=now, fact_type="DB_INTEGRITY",
        value=value, evidence_ref="PRAGMA integrity_check() on this connection at collection time",
        confidence=1.0, now=now, threshold_s=threshold_s, detail=detail,
    )


def _fact_last_effect_status(conn: sqlite3.Connection, *, now: datetime, threshold_s: float) -> Optional[SelfObservation]:
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT journal_id, status, gate_allowed, readback_ok, created_at "
            "FROM f2_grid10_effect_journal ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return _finalize(
            source="f2_grid10_effect_journal", observed_at_raw=now, fact_type="LAST_EFFECT_STATUS",
            value="NONE", evidence_ref="f2_grid10_effect_journal: 0 rows",
            confidence=1.0, now=now, threshold_s=threshold_s,
        )
    return _finalize(
        source="f2_grid10_effect_journal", observed_at_raw=row["created_at"], fact_type="LAST_EFFECT_STATUS",
        value=row["status"], evidence_ref=f"journal_id={row['journal_id']}",
        confidence=0.95, now=now, threshold_s=threshold_s,
        detail={"gate_allowed": row["gate_allowed"], "readback_ok": row["readback_ok"]},
    )


def _fact_runtime_epoch_changed(
    conn: sqlite3.Connection, successor_epoch_id: str, *, now: datetime, threshold_s: float,
) -> Optional[SelfObservation]:
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT reentry_id, predecessor_epoch_id, predecessor_termination_reason, "
            "predecessor_confidence, created_at FROM f2_reentry_record "
            "WHERE successor_epoch_id=? ORDER BY created_at DESC LIMIT 1",
            (successor_epoch_id,),
        ).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return _finalize(
            source="f2_reentry_record", observed_at_raw=now, fact_type="RUNTIME_EPOCH_CHANGED",
            value=False, evidence_ref=f"f2_reentry_record: 0 rows for successor_epoch_id={successor_epoch_id}",
            confidence=1.0, now=now, threshold_s=threshold_s,
        )
    return _finalize(
        source="f2_reentry_record", observed_at_raw=row["created_at"], fact_type="RUNTIME_EPOCH_CHANGED",
        value=True, evidence_ref=f"reentry_id={row['reentry_id']}",
        confidence=0.95, now=now, threshold_s=threshold_s,
        detail={"predecessor_epoch_id": row["predecessor_epoch_id"]},
    ), row  # type: ignore[return-value]


def _fact_predecessor_termination(row: sqlite3.Row, *, now: datetime, threshold_s: float) -> Optional[SelfObservation]:
    if row is None or row["predecessor_confidence"] is None:
        return None
    return _finalize(
        source="f2_reentry_record", observed_at_raw=row["created_at"], fact_type="PREDECESSOR_TERMINATION",
        value=row["predecessor_termination_reason"], evidence_ref=f"reentry_id={row['reentry_id']}",
        confidence=float(row["predecessor_confidence"]), now=now, threshold_s=threshold_s,
    )


def _fact_retrieval_hit_count(
    conn: sqlite3.Connection, session_id: Optional[str], *, now: datetime, threshold_s: float,
) -> Optional[SelfObservation]:
    try:
        conn.row_factory = sqlite3.Row
        row = None
        if session_id:
            row = conn.execute(
                "SELECT retrieval_id, selected_memory_ids, ts FROM retrieval_episodes "
                "WHERE session_id=? ORDER BY ts DESC LIMIT 1",
                (session_id,),
            ).fetchone()
        match_kind = "exact_session"
        if row is None:
            row = conn.execute(
                "SELECT retrieval_id, selected_memory_ids, ts FROM retrieval_episodes "
                "ORDER BY ts DESC LIMIT 1"
            ).fetchone()
            match_kind = "fallback_global"
    except sqlite3.Error:
        return None
    if row is None:
        return _finalize(
            source="retrieval_episodes", observed_at_raw=now, fact_type="RETRIEVAL_HIT_COUNT",
            value=0, evidence_ref="retrieval_episodes: 0 rows",
            confidence=1.0, now=now, threshold_s=threshold_s, detail={"match_kind": "none"},
        )
    try:
        n = len(json.loads(row["selected_memory_ids"] or "[]"))
    except Exception:
        n = 0
    confidence = 0.9 if match_kind == "exact_session" else 0.5
    return _finalize(
        source="retrieval_episodes", observed_at_raw=row["ts"], fact_type="RETRIEVAL_HIT_COUNT",
        value=n, evidence_ref=f"retrieval_id={row['retrieval_id']}",
        confidence=confidence, now=now, threshold_s=threshold_s, detail={"match_kind": match_kind},
    )


def _installation_id_for_epoch(conn: sqlite3.Connection, runtime_epoch_id: str) -> Optional[str]:
    """RealTurn carries no installation_id field (see grid10_p7_coordination.
    RealTurn) -- the real, correctly-sourced way to get it is the epoch's own
    row, same table P10's reconstruct_workspace reads for other purposes."""
    try:
        row = conn.execute(
            "SELECT installation_id FROM f2_runtime_epoch WHERE runtime_epoch_id=?",
            (runtime_epoch_id,),
        ).fetchone()
    except sqlite3.Error:
        return None
    return row[0] if row else None


def _fact_last_grid10_winner(
    conn: sqlite3.Connection, installation_id: Optional[str], *, now: datetime, threshold_s: float,
) -> Optional[SelfObservation]:
    if not installation_id:
        return None
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT frame_id, broadcast_winner_cell, broadcast_value, opened_at FROM f2_grid10_frame "
            "WHERE installation_id=? AND broadcast_winner_cell IS NOT NULL "
            "ORDER BY opened_at DESC LIMIT 1",
            (installation_id,),
        ).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    return _finalize(
        source="f2_grid10_frame", observed_at_raw=row["opened_at"], fact_type="LAST_GRID10_WINNER",
        value=row["broadcast_winner_cell"], evidence_ref=f"frame_id={row['frame_id']}",
        confidence=0.95, now=now, threshold_s=threshold_s,
        detail={"broadcast_value": row["broadcast_value"]},
    ), row  # type: ignore[return-value]


def _fact_grid10_conflict_present(
    conn: sqlite3.Connection, frame_id: Optional[str], *, now: datetime, threshold_s: float,
) -> Optional[SelfObservation]:
    if not frame_id:
        return None
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM f2_grid10_cell_observation WHERE frame_id=? AND conflict_flag=1",
            (frame_id,),
        ).fetchone()[0]
    except sqlite3.Error:
        return None
    return _finalize(
        source="f2_grid10_cell_observation", observed_at_raw=now, fact_type="GRID10_CONFLICT_PRESENT",
        value=bool(n > 0), evidence_ref=f"frame_id={frame_id},conflict_flag=1,count={n}",
        confidence=0.95, now=now, threshold_s=threshold_s,
    )


def _fact_grid10_frame_failure_count(
    conn: sqlite3.Connection, runtime_epoch_id: str, *, now: datetime, threshold_s: float,
) -> Optional[SelfObservation]:
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM f2_grid10_frame WHERE runtime_epoch_id=? AND status='FAILED'",
            (runtime_epoch_id,),
        ).fetchone()[0]
    except sqlite3.Error:
        return None
    return _finalize(
        source="f2_grid10_frame", observed_at_raw=now, fact_type="GRID10_FRAME_FAILURE_COUNT",
        value=int(n), evidence_ref=f"runtime_epoch_id={runtime_epoch_id},status='FAILED'",
        confidence=1.0, now=now, threshold_s=threshold_s,
    )


# --------------------------------------------------------------------------
# Collection -- fail-closed per source, never raises.
# --------------------------------------------------------------------------


def collect_self_observations(
    conn: sqlite3.Connection,
    turn: RealTurn,
    *,
    now: Optional[datetime] = None,
    threshold_s: float = DEFAULT_STALE_THRESHOLD_S,
) -> list:
    """Reads every real source this module knows about for the given turn's
    identity (runtime_epoch_id/session_id) and returns a list of
    ``SelfObservation``. Never raises: any individual source that errors
    (missing table, closed connection, malformed row, etc.) is silently
    omitted -- the rest of the list is still returned. An entirely broken
    connection yields an empty list, never an exception."""
    n = now or _jetzt()
    out: list = []

    def _add(x):
        if x is None:
            return
        if isinstance(x, tuple):
            out.append(x[0])
        else:
            out.append(x)

    try:
        _add(_fact_db_integrity(conn, now=n, threshold_s=threshold_s))
    except Exception:
        pass
    try:
        _add(_fact_last_effect_status(conn, now=n, threshold_s=threshold_s))
    except Exception:
        pass

    reentry_row = None
    try:
        result = _fact_runtime_epoch_changed(conn, turn.runtime_epoch_id, now=n, threshold_s=threshold_s)
        if isinstance(result, tuple):
            out.append(result[0])
            reentry_row = result[1]
        elif result is not None:
            out.append(result)
    except Exception:
        pass
    try:
        _add(_fact_predecessor_termination(reentry_row, now=n, threshold_s=threshold_s))
    except Exception:
        pass
    try:
        _add(_fact_retrieval_hit_count(conn, turn.session_id, now=n, threshold_s=threshold_s))
    except Exception:
        pass

    try:
        installation_id = _installation_id_for_epoch(conn, turn.runtime_epoch_id)
    except Exception:
        installation_id = None
    last_frame_row = None
    try:
        result = _fact_last_grid10_winner(conn, installation_id, now=n, threshold_s=threshold_s)
        if isinstance(result, tuple):
            out.append(result[0])
            last_frame_row = result[1]
        elif result is not None:
            out.append(result)
    except Exception:
        pass
    try:
        frame_id = last_frame_row["frame_id"] if last_frame_row is not None else None
        _add(_fact_grid10_conflict_present(conn, frame_id, now=n, threshold_s=threshold_s))
    except Exception:
        pass
    try:
        _add(_fact_grid10_frame_failure_count(conn, turn.runtime_epoch_id, now=n, threshold_s=threshold_s))
    except Exception:
        pass

    return out


# --------------------------------------------------------------------------
# Pure application -- no I/O, independently testable, authoritative about
# staleness (re-derives from freshness_s/threshold, never trusts a record's
# own `validity` label).
# --------------------------------------------------------------------------


def _contribution(obs: SelfObservation, threshold_s: float) -> float:
    if obs.freshness_s is None or obs.freshness_s > threshold_s:
        return 0.0
    key = (obs.fact_type, obs.value)
    if key in _WEIGHTS:
        return SELF_OBS_EPSILON * _WEIGHTS[key]
    if obs.fact_type == "RETRIEVAL_HIT_COUNT" and isinstance(obs.value, (int, float)) and not isinstance(obs.value, bool):
        return SELF_OBS_EPSILON * 0.05 * min(float(obs.value), 10.0)
    if obs.fact_type == "GRID10_FRAME_FAILURE_COUNT" and isinstance(obs.value, (int, float)) and not isinstance(obs.value, bool):
        return -SELF_OBS_EPSILON * 0.2 * min(float(obs.value), 5.0)
    return 0.0


def apply_self_observation(
    prior_state: Mapping[str, float],
    observations: Sequence[SelfObservation],
    *,
    threshold_s: float = DEFAULT_STALE_THRESHOLD_S,
) -> tuple:
    """Pure. Returns (adjusted_state, delta, contributions) where
    ``adjusted_state`` adds the SAME scalar ``delta`` to every cell's prior
    state (uniform -- no cell singled out, see module docstring), and
    ``contributions`` is a per-fact (fact_type, value, contribution) list for
    audit/attributability. Facts whose (re-derived) freshness exceeds
    ``threshold_s`` contribute exactly 0.0, regardless of what their own
    ``validity`` label claims."""
    contributions = [(o.fact_type, o.value, _contribution(o, threshold_s)) for o in observations]
    delta = sum(c for _, _, c in contributions)
    adjusted = {cell: float(prior_state.get(cell, 0.0)) + delta for cell in CELLS}
    return adjusted, delta, contributions


def append_self_observation_log(
    evidence_path: Path, turn: RealTurn, observations: Sequence[SelfObservation], delta: float,
) -> None:
    line = {
        "schema": SCHEMA_LOG_LINE,
        "ts": _jetzt_iso(),
        "runtime_epoch_id": turn.runtime_epoch_id,
        "turn_event_id": turn.turn_event_id,
        "session_id": turn.session_id,
        "delta": delta,
        "observations": [
            {
                "source": o.source, "observed_at": o.observed_at, "fact_type": o.fact_type,
                "value": o.value, "evidence_ref": o.evidence_ref, "freshness_s": o.freshness_s,
                "confidence": o.confidence, "validity": o.validity, "detail": dict(o.detail),
            }
            for o in observations
        ],
    }
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    with open(evidence_path, "a", encoding="utf-8") as f:
        f.write(_canonical_json(line) + "\n")


# --------------------------------------------------------------------------
# Wiring -- the real entry point a caller uses per real turn. Strictly
# additive: does not modify grid10_p7_coordination.py / grid10_p10_
# workspace_reentry.py at all, reuses their unmodified functions.
# --------------------------------------------------------------------------


def coordinate_real_turn_with_self_observation(
    conn: sqlite3.Connection,
    evidence_path: Path,
    turn: RealTurn,
    *,
    env=None,
    compose_with_reentry: bool = True,
    stale_threshold_s: float = DEFAULT_STALE_THRESHOLD_S,
):
    """Gate-checked (P7's own p7_active gate), exactly like coordinate_real_
    turn / coordinate_real_turn_with_reentry. Reads real self-observation
    facts for this turn, optionally composes with P10's reconstructed
    workspace for the state(t=0) baseline (falls back to read_prior_state
    exactly as P10/P7 do when no valid workspace exists), applies the
    self-observation delta uniformly, runs one coordination cycle, persists,
    and logs. Returns (result, meta) or None if the gate is closed -- same
    zero-behavioral-delta convention as every prior phase's entry point."""
    if not p7_active(conn, env=env):
        return None

    observations = collect_self_observations(conn, turn, threshold_s=stale_threshold_s)

    base_state: Mapping[str, float]
    used_reentry = False
    if compose_with_reentry and reconstruct_workspace is not None:
        try:
            workspace = reconstruct_workspace(conn, turn.runtime_epoch_id)
        except Exception:
            workspace = None
        if workspace is not None and workspace.valid:
            base_state = workspace.seeded_state()
            used_reentry = True
        else:
            base_state = read_prior_state(conn, P7_LIVE_CONDITION_KEY)
    else:
        base_state = read_prior_state(conn, P7_LIVE_CONDITION_KEY)

    adjusted_state, delta, contributions = apply_self_observation(
        base_state, observations, threshold_s=stale_threshold_s
    )
    result = run_coordination_cycle(turn, adjusted_state)
    persist_coordination_result(conn, result)
    append_self_observation_log(evidence_path, turn, observations, delta)
    return result, {
        "used_reentry": used_reentry,
        "observations": observations,
        "delta": delta,
        "contributions": contributions,
    }
