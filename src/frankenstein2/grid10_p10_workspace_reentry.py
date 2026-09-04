"""F2-WP-1207 P10: workspace-reentry reconstruction -- closes the gap P9
left open. Canonical location (this repo, this branch); a byte-adapted
mirror lives at frankenstein-repo/scripts/f2wp1207_p10_workspace_reentry.py
(same relationship P7 already has to its own vendored copy there), where P9's
epoch reconciler and the live unified.db path resolution actually live, and
where this module's DB-backed gold test was built and run -- see that repo's
commit for the actual measured numbers (real predecessor epoch data,
attributability trace).

P9 (frankenstein-repo/scripts/f2wp1207_epoch_reconciler.py) gives a new
epoch a typed `f2_reentry_record` pointing at its real predecessor epoch
(evidence-bound termination classification + `last_grid10_frame_id` +
`last_work_ref`). But nothing yet turns that pointer into validated, typed
workspace content, and nothing yet feeds it into P7's
(`grid10_p7_coordination.py`) state(t=0) seed -- `coordinate_real_turn`'s
`read_prior_state` just reads whatever is currently sitting in
`f2_grid10_p6d_state` under the single global `f2wp1207_p7_live`
condition_key, no explicit evidenced connection to "this new epoch's real
predecessor's real last workspace state." That is the gap this module
closes.

Gabriel's spec (F2-WP-1207 P5-P13 roadmap, P10): "Kernkette: last accepted
workspace state -> persist -> runtime death/restart -> typed reentry record
-> workspace reconstruction -> new competition -> measurable influence on
next selection. Nicht einfach alten Kontext blind in den Prompt kippen. Nur
typisierte, bestaetigte Workspace-Artefakte rehydrieren: letzter Broadcast,
letzter Winner, relevante Zellzustaende, offene Goals/Tasks, unresolved
conflicts, last accepted external/world evidence, predecessor frame IDs."

Field-by-field real-data audit (performed against the live
~/.local/share/agentzero/unified.db schema + row population before writing
any of this, per house discipline -- measurement before belief; that DB is
not reachable from this repo/branch, the audit and the gold test both live
in frankenstein-repo):

  INCLUDED (real backing found, wired below):
    - last broadcast / last winner  -> f2_grid10_frame.broadcast_value /
      .broadcast_winner_cell, keyed by f2_reentry_record.last_grid10_frame_id.
    - relevant cell states          -> f2_grid10_cell_state (installation_id-
      scoped rolling accumulator), cross-checked against the predecessor
      epoch's own frame set via updated_by_frame_id for a HIGH/MEDIUM
      confidence split (see `_cell_states`).
    - unresolved conflicts          -> f2_grid10_cell_observation.conflict_flag
      for rows at last_grid10_frame_id -- exactly frame-scoped, no ambiguity.
    - predecessor frame IDs         -> f2_grid10_frame.frame_id for all frames
      of the predecessor epoch (ordered by opened_at), plus P9's own
      last_grid10_frame_id pointer.
    - open goals/tasks              -> entityos_arbeitspaket WHERE
      session_id=<predecessor epoch's session_id> AND stand='laeuft'. Real
      table, real columns. NOTE (honest gap, not glossed over): in the live
      DB inspected 2026-09-04, zero rows of entityos_arbeitspaket share a
      session_id with any real f2_runtime_epoch row (arbeitspaket sessions
      are harness-sess-*/manuell-style ids; GRID10 epoch sessions are UUIDs
      from the live Claude Code hook). The JOIN is real and mechanically
      correct, but currently returns empty for every real epoch observed --
      documented here rather than silently hidden. Exercised with populated
      data in frankenstein-repo's gold test via a synthetic-but-realistic
      row on a DB COPY.

  EXCLUDED (checked, no real backing -- see EXCLUDED_FIELDS below):
    - "last accepted external/world evidence": no table in the current data
      model ties external/world evidence to a runtime_epoch_id/session_id/
      frame_id with "accepted" semantics. `effects` exists but is keyed to
      user_id/episode_id (a tool-call-authorization log, unrelated concept).
      f2_grid10_cell_observation.input_digest_sha256/output_digest_sha256 are
      per-cell stimulus fingerprints (already exposed structurally, not
      elevated to a first-class field since they carry no "accepted"
      semantics of their own). Left out rather than invented.

Persistence convention: same as P7/P9 -- plain sqlite3.Connection supplied by
the caller, no new database, no new tables, NO SCHEMA CHANGE AT ALL (this
module only reads existing P7/P9/GRID10 tables). Cells stay opaque G1..G10.
No Effects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import sqlite3
from typing import Optional

from frankenstein2.grid10_p7_coordination import (
    CELLS,
    P7_LIVE_CONDITION_KEY,
    RealTurn,
    append_transition_log,
    p7_active,
    persist_coordination_result,
    read_prior_state,
    run_coordination_cycle,
)

SCHEMA = "F2WP1207_P10_RECONSTRUCTED_WORKSPACE/v1"

# Documented, checked absence -- see module docstring. Kept as data (not just
# prose) so a caller/test can assert on it mechanically.
EXCLUDED_FIELDS = {
    "last_accepted_external_world_evidence": (
        "No mechanically clean, epoch/frame/session-scoped table for "
        "'accepted external/world evidence' exists in the current data "
        "model (checked 2026-09-04 against live unified.db: `effects` is "
        "keyed to user_id/episode_id from an unrelated tool-call-"
        "authorization log; f2_grid10_cell_observation's "
        "input_digest_sha256/output_digest_sha256 are per-cell stimulus "
        "fingerprints without 'accepted' semantics). Deliberately omitted "
        "rather than invented."
    ),
}


# --------------------------------------------------------------------------
# Typed artifacts -- every field carries its own provenance, nothing is a
# blind dump.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Provenance:
    source_table: str
    source_key: str
    confidence: float  # 0..1
    note: str = ""


@dataclass(frozen=True)
class CellStateArtifact:
    cell_id: str
    state_value: float
    provenance: Provenance


@dataclass(frozen=True)
class OpenTaskArtifact:
    paket_id: str
    auftrag: str
    stand: str
    provenance: Provenance


@dataclass(frozen=True)
class ReconstructedWorkspace:
    schema: str
    successor_epoch_id: str
    predecessor_epoch_id: Optional[str]
    reentry_id: Optional[str]
    last_grid10_frame_id: Optional[str]

    last_broadcast_value: Optional[float] = None
    last_broadcast_provenance: Optional[Provenance] = None
    last_winner_cell_id: Optional[str] = None
    last_winner_provenance: Optional[Provenance] = None

    relevant_cell_states: tuple = field(default_factory=tuple)  # tuple[CellStateArtifact,...]
    unresolved_conflicts: tuple = field(default_factory=tuple)  # tuple[str,...] cell_ids
    unresolved_conflicts_provenance: Optional[Provenance] = None

    predecessor_frame_ids: tuple = field(default_factory=tuple)  # tuple[str,...]
    predecessor_frame_ids_provenance: Optional[Provenance] = None

    open_goals_tasks: tuple = field(default_factory=tuple)  # tuple[OpenTaskArtifact,...]

    predecessor_termination_reason: Optional[str] = None
    predecessor_termination_confidence: Optional[float] = None

    valid: bool = False
    invalid_reason: Optional[str] = None

    def seeded_state(self) -> dict:
        """cell_id -> state_value, for the cells this workspace has real
        state for. Missing cells are left absent -- the caller (P7's own
        state-update formula) already defaults absent cells to 0.0, same
        convention as `read_prior_state`'s cold-start behavior."""
        return {c.cell_id: c.state_value for c in self.relevant_cell_states}


# --------------------------------------------------------------------------
# Reconstruction -- read-only, no schema change, no writes.
# --------------------------------------------------------------------------


def _find_reentry_record(conn: sqlite3.Connection, successor_epoch_id: str) -> Optional[sqlite3.Row]:
    """A successor epoch can have MULTIPLE f2_reentry_record rows -- P9's
    reconcile() closes every open epoch sharing the same
    installation_id/state_root_id, not just one, so several unrelated
    predecessors can legitimately chain to the same successor in one
    reconcile() call. Picking `created_at DESC` alone is not a reliable
    tie-break (all rows from one reconcile() call share the same `now`
    timestamp) and would nondeterministically select an arbitrary
    predecessor. Instead: prefer the candidate whose last_grid10_frame_id
    resolves to a REAL f2_grid10_frame row with the MOST RECENT opened_at --
    i.e. the predecessor that was actually most recently active, the most
    relevant real workspace to inherit. Falls back to created_at DESC among
    candidates with no resolvable frame."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM f2_reentry_record WHERE successor_epoch_id=? ORDER BY created_at DESC",
        (successor_epoch_id,),
    ).fetchall()
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]
    best = None
    best_opened_at = None
    for row in rows:
        frame_id = row["last_grid10_frame_id"]
        if not frame_id:
            continue
        frame = conn.execute(
            "SELECT opened_at FROM f2_grid10_frame WHERE frame_id=?", (frame_id,)
        ).fetchone()
        if frame is None:
            continue
        opened_at = frame[0]
        if best_opened_at is None or opened_at > best_opened_at:
            best, best_opened_at = row, opened_at
    return best if best is not None else rows[0]


def _predecessor_epoch_row(conn: sqlite3.Connection, predecessor_epoch_id: str) -> Optional[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return conn.execute(
        "SELECT * FROM f2_runtime_epoch WHERE runtime_epoch_id=?",
        (predecessor_epoch_id,),
    ).fetchone()


def _last_frame_row(conn: sqlite3.Connection, frame_id: str) -> Optional[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return conn.execute(
        "SELECT * FROM f2_grid10_frame WHERE frame_id=?", (frame_id,)
    ).fetchone()


def _predecessor_frame_ids(conn: sqlite3.Connection, predecessor_epoch_id: str) -> tuple:
    rows = conn.execute(
        "SELECT frame_id FROM f2_grid10_frame WHERE runtime_epoch_id=? "
        "ORDER BY opened_at ASC",
        (predecessor_epoch_id,),
    ).fetchall()
    return tuple(r[0] for r in rows)


def _cell_states(
    conn: sqlite3.Connection, installation_id: str, predecessor_frame_ids: tuple
) -> tuple:
    """Real state per cell from the installation-scoped rolling accumulator
    f2_grid10_cell_state. This table is NOT epoch-scoped (a real, documented
    architectural gap in the current data model -- it upserts per
    installation_id/logical_cell_id, latest value only). Confidence:
      HIGH (0.9)   -- updated_by_frame_id belongs to the predecessor epoch's
                       own frame set (state provably unmoved since).
      MEDIUM (0.5) -- row exists but updated_by_frame_id is outside the
                       predecessor epoch's frame set (rolling accumulator may
                       have been advanced by a different/later epoch sharing
                       the same installation_id -- honestly flagged, not
                       hidden)."""
    rows = conn.execute(
        "SELECT logical_cell_id, state_value, updated_by_frame_id, updated_at "
        "FROM f2_grid10_cell_state WHERE installation_id=?",
        (installation_id,),
    ).fetchall()
    frame_set = set(predecessor_frame_ids)
    out = []
    for cell_id, state_value, updated_by_frame_id, updated_at in rows:
        if updated_by_frame_id in frame_set:
            conf = 0.9
            note = "updated_by_frame_id belongs to predecessor epoch's own frame set"
        else:
            conf = 0.5
            note = (
                "f2_grid10_cell_state is installation-scoped, not epoch-scoped -- "
                "updated_by_frame_id does not belong to predecessor epoch's frame "
                "set, rolling accumulator may have moved since (documented gap)"
            )
        out.append(
            CellStateArtifact(
                cell_id=cell_id,
                state_value=float(state_value),
                provenance=Provenance(
                    source_table="f2_grid10_cell_state",
                    source_key=f"installation_id={installation_id},logical_cell_id={cell_id},"
                    f"updated_by_frame_id={updated_by_frame_id},updated_at={updated_at}",
                    confidence=conf,
                    note=note,
                ),
            )
        )
    return tuple(out)


def _unresolved_conflicts(conn: sqlite3.Connection, last_frame_id: str) -> tuple:
    rows = conn.execute(
        "SELECT logical_cell_id FROM f2_grid10_cell_observation "
        "WHERE frame_id=? AND conflict_flag=1 ORDER BY logical_cell_id",
        (last_frame_id,),
    ).fetchall()
    return tuple(r[0] for r in rows)


def _open_goals_tasks(conn: sqlite3.Connection, predecessor_session_id: Optional[str]) -> tuple:
    if not predecessor_session_id:
        return tuple()
    try:
        rows = conn.execute(
            "SELECT paket_id, auftrag, stand FROM entityos_arbeitspaket "
            "WHERE session_id=? AND stand='laeuft' ORDER BY erstellt DESC",
            (predecessor_session_id,),
        ).fetchall()
    except sqlite3.Error:
        return tuple()
    return tuple(
        OpenTaskArtifact(
            paket_id=paket_id,
            auftrag=auftrag,
            stand=stand,
            provenance=Provenance(
                source_table="entityos_arbeitspaket",
                source_key=f"paket_id={paket_id},session_id={predecessor_session_id}",
                confidence=0.9,
                note="stand='laeuft' at reconstruction time",
            ),
        )
        for paket_id, auftrag, stand in rows
    )


def reconstruct_workspace(conn: sqlite3.Connection, successor_epoch_id: str) -> Optional[ReconstructedWorkspace]:
    """Given a successor epoch id, find its P9 f2_reentry_record (if any) and
    build a validated, typed, per-field-provenanced ReconstructedWorkspace.
    Returns None if no reentry record exists at all (fresh install / no
    predecessor) -- the caller's fallback is then simply "call P7 exactly as
    before". Never raises for missing/absent data -- degrades to
    valid=False with an explicit invalid_reason instead."""
    try:
        reentry = _find_reentry_record(conn, successor_epoch_id)
    except sqlite3.Error:
        return None
    if reentry is None:
        return None

    predecessor_epoch_id = reentry["predecessor_epoch_id"]
    last_frame_id = reentry["last_grid10_frame_id"]

    if not last_frame_id:
        return ReconstructedWorkspace(
            schema=SCHEMA,
            successor_epoch_id=successor_epoch_id,
            predecessor_epoch_id=predecessor_epoch_id,
            reentry_id=reentry["reentry_id"],
            last_grid10_frame_id=None,
            predecessor_termination_reason=reentry["predecessor_termination_reason"],
            predecessor_termination_confidence=reentry["predecessor_confidence"],
            valid=False,
            invalid_reason="reentry record has no last_grid10_frame_id (predecessor never ran a GRID10 frame)",
        )

    frame = _last_frame_row(conn, last_frame_id)
    if frame is None:
        return ReconstructedWorkspace(
            schema=SCHEMA,
            successor_epoch_id=successor_epoch_id,
            predecessor_epoch_id=predecessor_epoch_id,
            reentry_id=reentry["reentry_id"],
            last_grid10_frame_id=last_frame_id,
            predecessor_termination_reason=reentry["predecessor_termination_reason"],
            predecessor_termination_confidence=reentry["predecessor_confidence"],
            valid=False,
            invalid_reason=f"last_grid10_frame_id={last_frame_id} does not resolve to a real f2_grid10_frame row",
        )

    installation_id = frame["installation_id"]
    pred_frame_ids = _predecessor_frame_ids(conn, predecessor_epoch_id) if predecessor_epoch_id else (last_frame_id,)
    cell_states = _cell_states(conn, installation_id, pred_frame_ids)
    conflicts = _unresolved_conflicts(conn, last_frame_id)

    predecessor_session_id = None
    if predecessor_epoch_id:
        pred_epoch = _predecessor_epoch_row(conn, predecessor_epoch_id)
        if pred_epoch is not None:
            predecessor_session_id = pred_epoch["session_id"]
    goals = _open_goals_tasks(conn, predecessor_session_id)

    valid = bool(cell_states) and frame["broadcast_value"] is not None
    invalid_reason = None if valid else "no relevant_cell_states or broadcast_value resolved for last frame"

    return ReconstructedWorkspace(
        schema=SCHEMA,
        successor_epoch_id=successor_epoch_id,
        predecessor_epoch_id=predecessor_epoch_id,
        reentry_id=reentry["reentry_id"],
        last_grid10_frame_id=last_frame_id,
        last_broadcast_value=frame["broadcast_value"],
        last_broadcast_provenance=Provenance(
            "f2_grid10_frame", f"frame_id={last_frame_id}", 0.95, "direct row match on P9's last_grid10_frame_id"
        ),
        last_winner_cell_id=frame["broadcast_winner_cell"],
        last_winner_provenance=Provenance(
            "f2_grid10_frame", f"frame_id={last_frame_id}", 0.95, "direct row match on P9's last_grid10_frame_id"
        ),
        relevant_cell_states=cell_states,
        unresolved_conflicts=conflicts,
        unresolved_conflicts_provenance=Provenance(
            "f2_grid10_cell_observation", f"frame_id={last_frame_id},conflict_flag=1", 0.95, "frame-scoped, exact"
        ),
        predecessor_frame_ids=pred_frame_ids,
        predecessor_frame_ids_provenance=Provenance(
            "f2_grid10_frame", f"runtime_epoch_id={predecessor_epoch_id}", 0.95, "all frames of predecessor epoch"
        ),
        open_goals_tasks=goals,
        predecessor_termination_reason=reentry["predecessor_termination_reason"],
        predecessor_termination_confidence=reentry["predecessor_confidence"],
        valid=valid,
        invalid_reason=invalid_reason,
    )


# --------------------------------------------------------------------------
# Wiring into coordinate_real_turn's state-seeding -- strictly additive.
# Does NOT modify grid10_p7_coordination.py at all (zero behavioral change
# to its own coordinate_real_turn / to the sha256-pinned vendored copy's
# p7-bridge-turn call site in frankenstein-repo). Reuses its pure functions
# (run_coordination_cycle / persist_coordination_result /
# append_transition_log / p7_active / read_prior_state) unmodified and
# unduplicated -- only the SOURCE of prior_state differs.
# --------------------------------------------------------------------------


def coordinate_real_turn_with_reentry(
    conn: sqlite3.Connection,
    evidence_path,
    turn: RealTurn,
    *,
    env=None,
):
    """Gate-checked, exactly like coordinate_real_turn. When a valid
    reconstructed workspace exists for turn.runtime_epoch_id, seeds
    state(t=0) from it instead of read_prior_state's default. When no valid
    reentry record exists (fresh install / no predecessor / low-confidence
    classification that failed validity), falls back to calling
    read_prior_state EXACTLY as coordinate_real_turn does -- same table,
    same condition_key, same call -- so the result is provably identical to
    unmodified P7 behavior in that case (see frankenstein-repo's gold test)."""
    if not p7_active(conn, env=env):
        return None, None

    workspace = reconstruct_workspace(conn, turn.runtime_epoch_id)
    if workspace is not None and workspace.valid:
        prior_state = workspace.seeded_state()
        used_reentry = True
    else:
        prior_state = read_prior_state(conn, P7_LIVE_CONDITION_KEY)
        used_reentry = False

    result = run_coordination_cycle(turn, prior_state)
    persist_coordination_result(conn, result)
    append_transition_log(evidence_path, result)
    return result, {"used_reentry": used_reentry, "workspace": workspace}
