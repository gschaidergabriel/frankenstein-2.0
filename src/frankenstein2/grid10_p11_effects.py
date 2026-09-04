"""F2-WP-1207 P11 -- Effects anschliessen (first real GRID10 -> EffectGate door).

Roadmap position, verbatim from the project's own P5-P13 plan: "P11 --
Effects anschliessen. Erst danach duerfen intern ausgewaehlte Zustaende in
echte Aktionen uebersetzt werden: candidate -> typed effect request ->
EffectGate -> EffectJournal -> readback. GRID10/ein Modell darf NIE direkt
externe Wahrheit/Effekte erzeugen." Every phase up to and including P10
(``grid10_p7_coordination.py`` / ``grid10_p10_workspace_reentry.py``) was
explicitly internal-only -- "GRID10 koordiniert intern, EffectGate bleibt
getrennt", repeated in every prior module's own docstring. This module is
the FIRST deliberate, gated door in that wall, and the door stays firmly
gated:

  - The effect TYPE this round is deliberately inert/safe/reversible:
    ``EffectType.JOURNAL_MARKER`` -- "record that this happened", nothing
    more. No file write outside the repo, no shell command, no network
    call, no live hook wiring (``~/.claude/star/stern.py`` is untouched).
  - The journal is a NEW, dedicated table (``f2_grid10_effect_journal``) --
    this module never reads or writes the pre-existing ``effects`` table,
    which belongs to a completely different, already-load-bearing system
    (Claude Code's own tool-call audit trail, written by
    ``zulassen()``/``merken()`` in stern.py, and the exact table
    ``stern.py reconcile --beleg effect:<id>`` verifies against today).
    Different schema, different primary key space, different meaning.
  - GRID10 code (``grid10_p7_coordination.py`` / this module's own
    ``build_effect_request``) has NO path to execution that skips the
    gate: the only function that can write a ``status='EXECUTED'`` row
    (``_execute_journal_marker``) validates it was handed a real
    ``GateDecision`` with ``allowed=True`` bound to the SAME
    ``request_id``, and raises ``EffectGateBypassError`` otherwise. It has
    exactly one call site in this file (grep-verifiable -- see the gold
    test's own structural check), inside ``submit_effect_request``'s ALLOW
    branch.

Pipeline (Gabriel's spec, verbatim): "workspace candidate -> typed effect
request -> effect gate -> effect journal -> execution/denial -> readback ->
workspace uptake -> next-frame reentry. [...] Kein direkter Effekt aus
einer GRID10-Zelle heraus, keine Umgehung des Gates."

  1. candidate       -- a ``P7CoordinationResult`` from
                         ``coordinate_real_turn`` / ``coordinate_real_turn_
                         with_reentry`` (P7/P10, unmodified, imported not
                         reimplemented).
  2. typed request    -- ``build_effect_request()`` -> ``EffectRequest``,
                         a real dataclass (not a free string), carrying
                         provenance back to the triggering frame/turn.
  3. effect gate       -- ``evaluate_gate()``: a REAL decision function, not
                         a rubber stamp. Condition documented in
                         ``EffectGatePolicy`` below.
  4. effect journal     -- ``f2_grid10_effect_journal`` (new table, additive
                         migration in ``migrate_schema()``). Every request
                         gets exactly one row, ALLOWED+EXECUTED or
                         DENIED+not-executed -- denials are visible, nothing
                         silently vanishes.
  5. execution/denial    -- ``submit_effect_request()``: ALLOW -> write +
                         readback (re-SELECT the row, don't assume INSERT
                         succeeded silently); DENY -> journal-only.
  6. readback             -- ``ExecutionResult.readback_ok`` /
                         ``EffectOutcome.readback_row``.
  7. workspace uptake      -- ``apply_effect_uptake()``: feeds the outcome
                         back into the SAME ``f2_grid10_p6d_state`` row
                         P7's own ``read_prior_state`` (and P10's
                         ``reconstruct_workspace``) already read for
                         reentry -- house law "weniger neue Komponenten,
                         mehr Rueckkopplung": no new plumbing, reuses the
                         existing reentry channel.
  8. next-frame reentry     -- automatic: the NEXT ``coordinate_real_turn``
                         call for the same ``condition_key`` picks up the
                         uptake-adjusted state via the unmodified
                         ``read_prior_state``.

Gate's actual decision condition: ``EffectGatePolicy.min_broadcast_value``.
An effect request is only ALLOWED when the triggering turn's
``broadcast_value`` (the winning cell's competitive proposal score --
signal + kappa*tanh(state), see ``grid10_p7_coordination.proposal_score``)
meets or exceeds the policy threshold. Rationale: ``broadcast_value`` is the
one existing, evidenced, per-turn scalar that already represents "how
strong was this turn's actual winning signal" -- gating on it means a
weak/noise-dominated turn (low competitive margin) cannot trigger even this
inert effect, while a genuinely strong turn can. This is deliberately
simple (a single threshold on an existing evidenced value, not a new
inference), matching P7/P10's own precedent of reusing existing signals
rather than inventing new ones. The policy is a real, documented, testable
condition -- not a coin flip and not an unconditional pass.

Persistence convention: identical to P7/P9/P10 -- plain ``sqlite3.Connection``
supplied by the caller, no path resolution, no second database opened here.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Mapping, Optional

import sqlite3

from frankenstein2.grid10_p7_coordination import (
    P7CoordinationResult,
    RealTurn,
    coordinate_real_turn,
)

SCHEMA_REQUEST = "F2WP1207_P11_EFFECT_REQUEST/v1"
SCHEMA_JOURNAL_ROW = "F2WP1207_GRID10_EFFECT_JOURNAL/v1"

# Real, documented gate condition -- see module docstring "Gate's actual
# decision condition". Not retuned without a new preregistration, same
# discipline as P7's LAMBDA_PRIMARY/ALPHA/BETA/GAMMA/KAPPA.
DEFAULT_MIN_BROADCAST_VALUE = 0.5

# Uptake delta magnitude fed back into f2_grid10_p6d_state on execution vs.
# denial -- same order of magnitude as P7's own CONFLICT_MARGIN (0.05), a
# small, real, additive nudge, not a formula-dominating term.
EFFECT_UPTAKE_EPSILON = 0.05

_JOURNAL_DDL = """
CREATE TABLE IF NOT EXISTS f2_grid10_effect_journal (
    journal_id                  TEXT PRIMARY KEY,
    request_id                  TEXT NOT NULL,
    effect_type                 TEXT NOT NULL,
    schema                      TEXT NOT NULL,
    frame_id                    TEXT,
    turn_event_id                TEXT NOT NULL,
    runtime_epoch_id              TEXT NOT NULL,
    session_id                    TEXT,
    condition_key                  TEXT,
    winner_cell_id                  TEXT NOT NULL,
    broadcast_value                  REAL NOT NULL,
    payload_json                      TEXT,
    gate_policy_id                     TEXT NOT NULL,
    gate_min_broadcast_value            REAL NOT NULL,
    gate_allowed                         INTEGER NOT NULL CHECK (gate_allowed IN (0,1)),
    gate_reason                           TEXT NOT NULL,
    gate_decided_at                        TEXT NOT NULL,
    status                                  TEXT NOT NULL CHECK (status IN ('EXECUTED','DENIED')),
    executed_marker_text                     TEXT,
    executed_at                               TEXT,
    readback_ok                                INTEGER CHECK (readback_ok IN (0,1) OR readback_ok IS NULL),
    readback_row_hash                            TEXT,
    created_at                                    TEXT NOT NULL
);
"""
_JOURNAL_IDX_TURN = (
    "CREATE INDEX IF NOT EXISTS ix_f2_grid10_effect_journal_turn "
    "ON f2_grid10_effect_journal (turn_event_id);"
)
_JOURNAL_IDX_EPOCH = (
    "CREATE INDEX IF NOT EXISTS ix_f2_grid10_effect_journal_epoch "
    "ON f2_grid10_effect_journal (runtime_epoch_id);"
)
_JOURNAL_IDX_STATUS = (
    "CREATE INDEX IF NOT EXISTS ix_f2_grid10_effect_journal_status "
    "ON f2_grid10_effect_journal (status);"
)


class Grid10P11EffectsError(RuntimeError):
    """Fail-closed P11 effects error."""


class EffectGateBypassError(Grid10P11EffectsError):
    """Raised when execution is attempted without a valid, matching ALLOW
    GateDecision. The single deliberate structural tripwire in this
    module -- see ``_execute_journal_marker``."""


def _jetzt_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# --------------------------------------------------------------------------
# Schema migration -- purely additive, idempotent, safe to run on a copy
# repeatedly and on the live DB exactly once. NO existing table (including
# the unrelated `effects` table) is touched or read.
# --------------------------------------------------------------------------


def migrate_schema(conn: sqlite3.Connection) -> dict:
    already = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='f2_grid10_effect_journal'"
    ).fetchone()
    conn.execute(_JOURNAL_DDL)
    conn.execute(_JOURNAL_IDX_TURN)
    conn.execute(_JOURNAL_IDX_EPOCH)
    conn.execute(_JOURNAL_IDX_STATUS)
    conn.commit()
    created = already is None
    return {"ok": True, "added": ["TABLE f2_grid10_effect_journal"] if created else []}


# --------------------------------------------------------------------------
# Step 1/2: candidate -> typed effect request
# --------------------------------------------------------------------------


class EffectType(str, Enum):
    """Deliberately minimal for this phase -- see module docstring. Adding a
    new, less-inert effect type is an explicit, separate, future decision,
    not something this enum silently grows into."""

    JOURNAL_MARKER = "JOURNAL_MARKER"


@dataclass(frozen=True)
class EffectRequest:
    schema: str
    request_id: str
    effect_type: EffectType
    turn: RealTurn
    condition_key: str
    winner_cell_id: str
    broadcast_value: float
    payload: Mapping[str, str]
    requested_at: str


def build_effect_request(
    result: P7CoordinationResult,
    *,
    effect_type: EffectType = EffectType.JOURNAL_MARKER,
    marker_text: Optional[str] = None,
) -> EffectRequest:
    """Given a P7 coordination result (the workspace candidate), construct a
    typed effect request. Never called with anything other than a real
    ``P7CoordinationResult`` produced by ``coordinate_real_turn``/
    ``coordinate_real_turn_with_reentry`` -- provenance (frame_id/
    turn_event_id/runtime_epoch_id/session_id) is copied straight from
    ``result.turn``, never re-derived or guessed."""
    text = marker_text or (
        f"P11 journal marker: winner={result.winner_cell_id} "
        f"broadcast_value={result.broadcast_value:.6f} "
        f"condition_key={result.condition_key} "
        f"turn_event_id={result.turn.turn_event_id}"
    )
    return EffectRequest(
        schema=SCHEMA_REQUEST,
        request_id=uuid.uuid4().hex,
        effect_type=effect_type,
        turn=result.turn,
        condition_key=result.condition_key,
        winner_cell_id=result.winner_cell_id,
        broadcast_value=result.broadcast_value,
        payload={"marker_text": text},
        requested_at=_jetzt_iso(),
    )


# --------------------------------------------------------------------------
# Step 3: effect gate -- real condition, not a rubber stamp.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class EffectGatePolicy:
    policy_id: str
    min_broadcast_value: float = DEFAULT_MIN_BROADCAST_VALUE


@dataclass(frozen=True)
class GateDecision:
    request_id: str
    allowed: bool
    reason: str
    policy_id: str
    min_broadcast_value: float
    observed_broadcast_value: float
    decided_at: str


def evaluate_gate(request: EffectRequest, policy: EffectGatePolicy) -> GateDecision:
    """The gate. Allows iff the triggering turn's broadcast_value meets the
    policy threshold -- see module docstring for why this specific,
    existing, evidenced signal was chosen. Returns a GateDecision either
    way; callers (submit_effect_request) branch on ``.allowed``, but the
    function itself never mutates state and never executes anything."""
    allowed = request.broadcast_value >= policy.min_broadcast_value
    if allowed:
        reason = (
            f"ALLOW: broadcast_value={request.broadcast_value:.6f} >= "
            f"policy.min_broadcast_value={policy.min_broadcast_value:.6f} (policy={policy.policy_id})"
        )
    else:
        reason = (
            f"DENY: broadcast_value={request.broadcast_value:.6f} < "
            f"policy.min_broadcast_value={policy.min_broadcast_value:.6f} (policy={policy.policy_id})"
        )
    return GateDecision(
        request_id=request.request_id,
        allowed=allowed,
        reason=reason,
        policy_id=policy.policy_id,
        min_broadcast_value=policy.min_broadcast_value,
        observed_broadcast_value=request.broadcast_value,
        decided_at=_jetzt_iso(),
    )


# --------------------------------------------------------------------------
# Steps 4-6: journal, execution/denial, readback.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ExecutionResult:
    journal_id: str
    readback_ok: bool
    row: Mapping[str, object]


@dataclass(frozen=True)
class EffectOutcome:
    request: EffectRequest
    decision: GateDecision
    executed: bool
    journal_id: str
    readback_ok: Optional[bool]
    readback_row: Optional[Mapping[str, object]]


def _row_hash(journal_id: str, status: str, marker_text: Optional[str]) -> str:
    return hashlib.sha256(
        f"{journal_id}:{status}:{marker_text or ''}".encode("utf-8")
    ).hexdigest()


def _execute_journal_marker(
    conn: sqlite3.Connection, request: EffectRequest, decision: GateDecision
) -> ExecutionResult:
    """The ONLY function in this module (in this repo) that can write a
    ``status='EXECUTED'`` row. Structurally fail-closed: raises
    ``EffectGateBypassError`` unless handed a real ``GateDecision`` with
    ``allowed=True`` bound to the SAME request_id -- a decision for a
    different request, a hand-built ``allowed=True`` object with a
    mismatched request_id, or any DENIED decision are all rejected. This is
    the deliberate single call site (see gold test's structural grep check
    -- exactly one call to this function exists in this file, inside
    ``submit_effect_request``'s ALLOW branch)."""
    if not isinstance(decision, GateDecision):
        raise EffectGateBypassError("execution attempted without a GateDecision object")
    if decision.request_id != request.request_id:
        raise EffectGateBypassError(
            f"GateDecision.request_id={decision.request_id!r} does not match "
            f"EffectRequest.request_id={request.request_id!r} -- refusing to execute"
        )
    if not decision.allowed:
        raise EffectGateBypassError(
            f"execution attempted on a DENIED GateDecision (reason={decision.reason!r})"
        )

    journal_id = uuid.uuid4().hex
    marker_text = request.payload.get("marker_text")
    now = _jetzt_iso()
    conn.execute("BEGIN")
    try:
        conn.execute(
            "INSERT INTO f2_grid10_effect_journal "
            "(journal_id, request_id, effect_type, schema, frame_id, turn_event_id, "
            " runtime_epoch_id, session_id, condition_key, winner_cell_id, broadcast_value, "
            " payload_json, gate_policy_id, gate_min_broadcast_value, gate_allowed, gate_reason, "
            " gate_decided_at, status, executed_marker_text, executed_at, readback_ok, "
            " readback_row_hash, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                journal_id, request.request_id, request.effect_type.value, SCHEMA_JOURNAL_ROW,
                request.turn.frame_id, request.turn.turn_event_id, request.turn.runtime_epoch_id,
                request.turn.session_id, request.condition_key, request.winner_cell_id,
                request.broadcast_value, _canonical_json(dict(request.payload)),
                decision.policy_id, decision.min_broadcast_value, 1, decision.reason,
                decision.decided_at, "EXECUTED", marker_text, now, None, None, now,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    # Readback -- re-SELECT the row, don't assume the INSERT silently
    # succeeded.
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM f2_grid10_effect_journal WHERE journal_id=?", (journal_id,)
    ).fetchone()
    readback_ok = (
        row is not None
        and row["status"] == "EXECUTED"
        and row["executed_marker_text"] == marker_text
        and row["request_id"] == request.request_id
    )
    row_hash = _row_hash(journal_id, "EXECUTED", marker_text)
    conn.execute(
        "UPDATE f2_grid10_effect_journal SET readback_ok=?, readback_row_hash=? WHERE journal_id=?",
        (1 if readback_ok else 0, row_hash, journal_id),
    )
    conn.commit()
    row_dict = dict(row) if row is not None else {}
    row_dict["readback_ok"] = 1 if readback_ok else 0
    row_dict["readback_row_hash"] = row_hash
    return ExecutionResult(journal_id=journal_id, readback_ok=bool(readback_ok), row=row_dict)


def _journal_denial(
    conn: sqlite3.Connection, request: EffectRequest, decision: GateDecision
) -> str:
    """Writes the DENIED journal row -- denials are visible in the audit
    trail too, not just approvals. Refuses (raises) if handed an ALLOW
    decision -- this function's own job is exclusively the deny path."""
    if not isinstance(decision, GateDecision) or decision.allowed:
        raise Grid10P11EffectsError("_journal_denial called with a non-DENY decision")
    journal_id = uuid.uuid4().hex
    now = _jetzt_iso()
    conn.execute("BEGIN")
    try:
        conn.execute(
            "INSERT INTO f2_grid10_effect_journal "
            "(journal_id, request_id, effect_type, schema, frame_id, turn_event_id, "
            " runtime_epoch_id, session_id, condition_key, winner_cell_id, broadcast_value, "
            " payload_json, gate_policy_id, gate_min_broadcast_value, gate_allowed, gate_reason, "
            " gate_decided_at, status, executed_marker_text, executed_at, readback_ok, "
            " readback_row_hash, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                journal_id, request.request_id, request.effect_type.value, SCHEMA_JOURNAL_ROW,
                request.turn.frame_id, request.turn.turn_event_id, request.turn.runtime_epoch_id,
                request.turn.session_id, request.condition_key, request.winner_cell_id,
                request.broadcast_value, _canonical_json(dict(request.payload)),
                decision.policy_id, decision.min_broadcast_value, 0, decision.reason,
                decision.decided_at, "DENIED", None, None, None, None, now,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return journal_id


def submit_effect_request(
    conn: sqlite3.Connection, request: EffectRequest, policy: EffectGatePolicy
) -> EffectOutcome:
    """The single entry point a caller uses to go from a typed effect
    request to a journaled outcome. Evaluates the gate itself; the ALLOW
    branch is the ONLY code path anywhere in this module that reaches
    ``_execute_journal_marker``."""
    decision = evaluate_gate(request, policy)
    if decision.allowed:
        exec_result = _execute_journal_marker(conn, request, decision)
        return EffectOutcome(
            request=request, decision=decision, executed=True,
            journal_id=exec_result.journal_id, readback_ok=exec_result.readback_ok,
            readback_row=exec_result.row,
        )
    journal_id = _journal_denial(conn, request, decision)
    return EffectOutcome(
        request=request, decision=decision, executed=False,
        journal_id=journal_id, readback_ok=None, readback_row=None,
    )


# --------------------------------------------------------------------------
# Steps 7-8: workspace uptake -> next-frame reentry. Reuses the EXISTING
# f2_grid10_p6d_state / read_prior_state reentry channel P7 (and P10 on top
# of it) already have -- no new plumbing.
# --------------------------------------------------------------------------


def effect_uptake_delta(outcome: EffectOutcome) -> float:
    """+epsilon on confirmed execution, -epsilon on denial, 0.0 if execution
    happened but readback could not confirm it (never rewarded on
    unconfirmed writes)."""
    if outcome.executed and outcome.readback_ok:
        return EFFECT_UPTAKE_EPSILON
    if outcome.executed and not outcome.readback_ok:
        return 0.0
    return -EFFECT_UPTAKE_EPSILON


def apply_effect_uptake(
    conn: sqlite3.Connection, condition_key: str, winner_cell_id: str, outcome: EffectOutcome
) -> dict:
    """Adds the evidenced uptake delta directly to the winner cell's
    persisted state in f2_grid10_p6d_state -- the SAME row P7's own
    read_prior_state (and P10's reconstruct_workspace, when composed on
    top) already read for the next real turn. This is what closes the loop
    to "next-frame reentry": nothing new to wire, the next
    coordinate_real_turn call for this condition_key picks the change up
    automatically."""
    ts = _jetzt_iso()
    row = conn.execute(
        "SELECT state_value FROM f2_grid10_p6d_state WHERE condition_key=? AND logical_cell_id=?",
        (condition_key, winner_cell_id),
    ).fetchone()
    old_state = float(row[0]) if row else 0.0
    delta = effect_uptake_delta(outcome)
    new_state = old_state + delta
    conn.execute("BEGIN")
    try:
        if row is None:
            # No P7 cycle has ever persisted this cell for this
            # condition_key yet (e.g. isolated test) -- insert rather than
            # silently no-op, same upsert shape P7's persist_coordination_
            # result already uses elsewhere.
            conn.execute(
                "INSERT INTO f2_grid10_p6d_state "
                "(condition_key, logical_cell_id, state_value, updated_at, "
                " updated_by_frame_id, won_broadcast_count, schema) "
                "VALUES (?,?,?,?,?,?,?)",
                (condition_key, winner_cell_id, new_state, ts, None, 0,
                 "F2WP1207_GRID10_P6D_STATE/v1"),
            )
        else:
            conn.execute(
                "UPDATE f2_grid10_p6d_state SET state_value=?, updated_at=? "
                "WHERE condition_key=? AND logical_cell_id=?",
                (new_state, ts, condition_key, winner_cell_id),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {
        "condition_key": condition_key,
        "cell_id": winner_cell_id,
        "old_state": old_state,
        "delta": delta,
        "new_state": new_state,
        "outcome_executed": outcome.executed,
        "outcome_readback_ok": outcome.readback_ok,
    }


# --------------------------------------------------------------------------
# Full pipeline orchestration -- candidate -> ... -> uptake, one call per
# real turn. Does NOT modify grid10_p7_coordination.py at all (imports its
# unmodified coordinate_real_turn).
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class P11Result:
    coordination: P7CoordinationResult
    request: EffectRequest
    outcome: EffectOutcome
    uptake: dict


def coordinate_real_turn_with_effects(
    conn: sqlite3.Connection,
    evidence_path,
    turn: RealTurn,
    policy: EffectGatePolicy,
    *,
    env: Mapping[str, str] | None = None,
    marker_text: Optional[str] = None,
) -> Optional[P11Result]:
    """Gate-checked (P7's own p7_active gate) end-to-end P11 pipeline for one
    real turn: P7 coordination -> typed effect request -> effect gate ->
    journal -> execution/denial -> readback -> workspace uptake. Returns
    None (zero P11 I/O too) when P7 itself is not active -- same
    zero-behavioral-delta convention as coordinate_real_turn/
    coordinate_real_turn_with_reentry."""
    result = coordinate_real_turn(conn, evidence_path, turn, env=env)
    if result is None:
        return None
    request = build_effect_request(result, marker_text=marker_text)
    outcome = submit_effect_request(conn, request, policy)
    uptake = apply_effect_uptake(conn, result.condition_key, result.winner_cell_id, outcome)
    return P11Result(coordination=result, request=request, outcome=outcome, uptake=uptake)
