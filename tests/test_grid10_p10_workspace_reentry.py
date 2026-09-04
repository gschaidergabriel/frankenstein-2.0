import sqlite3
import tempfile
import unittest
from pathlib import Path

from frankenstein2.grid10_p7_coordination import (
    CELLS,
    P7_LIVE_CONDITION_KEY,
    RealTurn,
    coordinate_real_turn,
    derive_signal,
    proposal_score,
)
from frankenstein2.grid10_p10_workspace_reentry import (
    EXCLUDED_FIELDS,
    coordinate_real_turn_with_reentry,
    reconstruct_workspace,
)


def _fresh_db() -> sqlite3.Connection:
    """In-memory DB with the real tables this module touches, schema copied
    verbatim from the live unified.db (see module docstring for the audit).
    Fully hermetic -- never touches a real database."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE star_konfig(
          schluessel TEXT PRIMARY KEY, wert TEXT NOT NULL, typ TEXT NOT NULL,
          quelle TEXT, geaendert REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE f2_grid10_p6d_state (
            condition_key TEXT NOT NULL,
            logical_cell_id TEXT NOT NULL,
            state_value REAL NOT NULL DEFAULT 0.0,
            updated_at TEXT NOT NULL,
            updated_by_frame_id TEXT,
            won_broadcast_count INTEGER NOT NULL DEFAULT 0,
            schema TEXT NOT NULL,
            PRIMARY KEY (condition_key, logical_cell_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE f2_runtime_epoch (
            runtime_epoch_id TEXT PRIMARY KEY, state_root_id TEXT NOT NULL,
            installation_id TEXT NOT NULL, host_binding_id TEXT NOT NULL,
            started_at TEXT NOT NULL, predecessor_epoch_id TEXT,
            termination_reason TEXT, schema TEXT NOT NULL,
            session_id TEXT, boot_id TEXT, ended_at TEXT,
            termination_evidence TEXT, successor_epoch_id TEXT, confidence REAL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE f2_reentry_record (
            reentry_id TEXT PRIMARY KEY, entity_id TEXT,
            installation_id TEXT NOT NULL, state_root_id TEXT NOT NULL,
            predecessor_epoch_id TEXT, successor_epoch_id TEXT NOT NULL,
            predecessor_termination_reason TEXT, predecessor_confidence REAL,
            predecessor_boot_id TEXT, successor_boot_id TEXT,
            last_grid10_frame_id TEXT, last_work_ref TEXT,
            created_at TEXT NOT NULL, schema TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE f2_grid10_frame (
            frame_id TEXT PRIMARY KEY, entity_id TEXT, installation_id TEXT,
            state_root_id TEXT, runtime_epoch_id TEXT, session_id TEXT,
            turn_event_id TEXT, opened_at TEXT, closed_at TEXT, status TEXT,
            schema TEXT, cohort TEXT, broadcast_winner_cell TEXT,
            broadcast_value REAL, experiment_condition TEXT, state_weight REAL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE f2_grid10_cell_state (
            installation_id TEXT NOT NULL, logical_cell_id TEXT NOT NULL,
            state_value REAL NOT NULL DEFAULT 0.0, updated_at TEXT,
            updated_by_frame_id TEXT, won_broadcast_count INTEGER DEFAULT 0,
            schema TEXT, PRIMARY KEY (installation_id, logical_cell_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE f2_grid10_cell_observation (
            observation_id TEXT PRIMARY KEY, frame_id TEXT, logical_cell_id TEXT,
            input_digest_sha256 TEXT, output_digest_sha256 TEXT,
            uptake INTEGER DEFAULT 0, reentry_flag INTEGER DEFAULT 0,
            conflict_flag INTEGER DEFAULT 0, timing_ms REAL,
            cpu_ru_utime_delta_s REAL, rss_delta_kb INTEGER,
            predecessor_observation_id TEXT, schema TEXT, execution_position INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE entityos_arbeitspaket (
            paket_id TEXT PRIMARY KEY, besteller TEXT, session_id TEXT,
            auftrag TEXT, womit TEXT, warum TEXT, stand TEXT, ergebnis TEXT,
            beleg TEXT, erstellt REAL, geaendert REAL
        )
        """
    )
    conn.commit()
    return conn


def _turn(epoch: str, turn_event_id: str) -> RealTurn:
    return RealTurn(
        frame_id=turn_event_id, turn_event_id=turn_event_id,
        runtime_epoch_id=epoch, session_id=f"session-{epoch}",
    )


def _seed_predecessor(conn, *, installation_id="inst-1", state_root_id="root-1",
                       predecessor_epoch="epoch-pred", predecessor_session="session-pred",
                       cell_states):
    conn.execute(
        "INSERT INTO f2_runtime_epoch (runtime_epoch_id, state_root_id, installation_id, "
        "host_binding_id, started_at, schema, session_id) VALUES (?,?,?,?,?,?,?)",
        (predecessor_epoch, state_root_id, installation_id, "host-1", "t0", "v2", predecessor_session),
    )
    frame_id = "frame-pred-last"
    conn.execute(
        "INSERT INTO f2_grid10_frame (frame_id, installation_id, state_root_id, "
        "runtime_epoch_id, session_id, opened_at, status, schema, broadcast_winner_cell, "
        "broadcast_value) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (frame_id, installation_id, state_root_id, predecessor_epoch, predecessor_session,
         "t1", "CLOSED", "schema", "G4", 0.77),
    )
    for cell, val in cell_states.items():
        conn.execute(
            "INSERT INTO f2_grid10_cell_state (installation_id, logical_cell_id, state_value, "
            "updated_at, updated_by_frame_id, schema) VALUES (?,?,?,?,?,?)",
            (installation_id, cell, val, "t1", frame_id, "schema"),
        )
    conn.execute(
        "INSERT INTO f2_grid10_cell_observation (observation_id, frame_id, logical_cell_id, "
        "conflict_flag, schema) VALUES (?,?,?,?,?)",
        ("obs-1", frame_id, "G7", 1, "schema"),
    )
    conn.execute(
        "INSERT INTO entityos_arbeitspaket (paket_id, besteller, session_id, auftrag, stand, "
        "erstellt, geaendert) VALUES (?,?,?,?,?,?,?)",
        ("paket-1", "tester", predecessor_session, "open task", "laeuft", 0.0, 0.0),
    )
    conn.commit()
    return frame_id, installation_id, state_root_id, predecessor_epoch, predecessor_session


def _link_reentry(conn, *, installation_id, state_root_id, predecessor_epoch, successor_epoch,
                   frame_id, reason="UNKNOWN_UNCLEAN_TERMINATION", confidence=0.2):
    conn.execute(
        "INSERT INTO f2_reentry_record (reentry_id, installation_id, state_root_id, "
        "predecessor_epoch_id, successor_epoch_id, predecessor_termination_reason, "
        "predecessor_confidence, last_grid10_frame_id, created_at, schema) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("reentry-1", installation_id, state_root_id, predecessor_epoch, successor_epoch,
         reason, confidence, frame_id, "t2", "schema"),
    )
    conn.commit()


class ExcludedFieldTests(unittest.TestCase):
    def test_external_world_evidence_documented_as_excluded(self):
        self.assertIn("last_accepted_external_world_evidence", EXCLUDED_FIELDS)
        self.assertGreater(len(EXCLUDED_FIELDS["last_accepted_external_world_evidence"]), 20)


class ReconstructionTests(unittest.TestCase):
    def test_no_reentry_record_returns_none(self):
        conn = _fresh_db()
        self.assertIsNone(reconstruct_workspace(conn, "successor-x"))

    def test_valid_reconstruction_typed_fields_and_provenance(self):
        conn = _fresh_db()
        cell_states = {c: 0.5 + i * 0.01 for i, c in enumerate(CELLS)}
        frame_id, inst, root, pred_epoch, pred_session = _seed_predecessor(conn, cell_states=cell_states)
        _link_reentry(conn, installation_id=inst, state_root_id=root, predecessor_epoch=pred_epoch,
                      successor_epoch="succ-1", frame_id=frame_id)

        ws = reconstruct_workspace(conn, "succ-1")
        self.assertTrue(ws.valid)
        self.assertEqual(ws.last_winner_cell_id, "G4")
        self.assertAlmostEqual(ws.last_broadcast_value, 0.77)
        self.assertEqual(set(ws.seeded_state().keys()), set(CELLS))
        for cell, val in cell_states.items():
            self.assertAlmostEqual(ws.seeded_state()[cell], val)
        self.assertEqual(ws.unresolved_conflicts, ("G7",))
        self.assertEqual(len(ws.open_goals_tasks), 1)
        self.assertEqual(ws.open_goals_tasks[0].paket_id, "paket-1")
        # every included field carries provenance with a confidence in [0,1]
        for artifact in ws.relevant_cell_states:
            self.assertGreaterEqual(artifact.provenance.confidence, 0.0)
            self.assertLessEqual(artifact.provenance.confidence, 1.0)

    def test_multiple_candidates_picks_most_recently_active_predecessor(self):
        conn = _fresh_db()
        cell_states_old = {c: 0.1 for c in CELLS}
        cell_states_new = {c: 0.9 for c in CELLS}
        # older predecessor
        conn.execute(
            "INSERT INTO f2_runtime_epoch (runtime_epoch_id, state_root_id, installation_id, "
            "host_binding_id, started_at, schema, session_id) VALUES (?,?,?,?,?,?,?)",
            ("epoch-old", "root-1", "inst-1", "host-1", "t0", "v2", "session-old"),
        )
        conn.execute(
            "INSERT INTO f2_grid10_frame (frame_id, installation_id, state_root_id, "
            "runtime_epoch_id, session_id, opened_at, status, schema, broadcast_winner_cell, "
            "broadcast_value) VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("frame-old", "inst-1", "root-1", "epoch-old", "session-old", "t0", "CLOSED", "schema", "G1", 0.1),
        )
        conn.execute(
            "INSERT INTO f2_reentry_record (reentry_id, installation_id, state_root_id, "
            "predecessor_epoch_id, successor_epoch_id, last_grid10_frame_id, created_at, schema) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ("reentry-old", "inst-1", "root-1", "epoch-old", "succ-2", "frame-old", "t9", "schema"),
        )
        # newer (real, most recently active) predecessor
        frame_id, inst, root, pred_epoch, pred_session = _seed_predecessor(
            conn, predecessor_epoch="epoch-new", predecessor_session="session-new",
            cell_states=cell_states_new,
        )
        conn.execute("UPDATE f2_grid10_frame SET opened_at='t9' WHERE frame_id=?", (frame_id,))
        conn.commit()
        _link_reentry(conn, installation_id=inst, state_root_id=root, predecessor_epoch=pred_epoch,
                      successor_epoch="succ-2", frame_id=frame_id)

        ws = reconstruct_workspace(conn, "succ-2")
        self.assertTrue(ws.valid)
        self.assertEqual(ws.predecessor_epoch_id, "epoch-new")


class WiringAndFallbackTests(unittest.TestCase):
    def test_fallback_identical_to_unmodified_coordinate_real_turn_when_no_reentry_record(self):
        env = {"STERN_F2WP1207_P7_LIVE": "1"}
        turn_event_id = "shared-turn-1"

        conn_wrapper = _fresh_db()
        turn_wrapper = _turn("epoch-nofallback", turn_event_id)
        with tempfile.TemporaryDirectory() as d:
            path_wrapper = Path(d) / "log_wrapper.jsonl"
            result_wrapper, meta = coordinate_real_turn_with_reentry(conn_wrapper, path_wrapper, turn_wrapper, env=env)

        conn_plain = _fresh_db()
        turn_plain = _turn("epoch-plain", turn_event_id)
        with tempfile.TemporaryDirectory() as d:
            path_plain = Path(d) / "log_plain.jsonl"
            result_plain = coordinate_real_turn(conn_plain, path_plain, turn_plain, env=env)

        self.assertFalse(meta["used_reentry"])
        self.assertEqual(result_wrapper.winner_cell_id, result_plain.winner_cell_id)
        self.assertEqual(result_wrapper.broadcast_value, result_plain.broadcast_value)
        for a, b in zip(
            sorted(result_wrapper.transitions, key=lambda t: t.cell_id),
            sorted(result_plain.transitions, key=lambda t: t.cell_id),
        ):
            self.assertEqual(a.cell_id, b.cell_id)
            self.assertEqual(a.old_state, 0.0)
            self.assertEqual(a.old_state, b.old_state)
            self.assertEqual(a.proposal_score, b.proposal_score)
            self.assertEqual(a.new_state, b.new_state)

    def test_gate_off_returns_none_none_zero_io(self):
        conn = _fresh_db()
        turn = _turn("epoch-x", "turn-x")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "log.jsonl"
            result, meta = coordinate_real_turn_with_reentry(conn, path, turn, env={"STERN_F2WP1207_P7_LIVE": "0"})
        self.assertIsNone(result)
        self.assertIsNone(meta)
        self.assertFalse(path.exists())

    def test_valid_reentry_seeds_state_and_changes_selection_measurably(self):
        env = {"STERN_F2WP1207_P7_LIVE": "1"}
        turn_event_id = "shared-turn-2"
        cell_states = {c: 0.9 for c in CELLS}  # strong uniform history

        conn = _fresh_db()
        frame_id, inst, root, pred_epoch, pred_session = _seed_predecessor(conn, cell_states=cell_states)
        _link_reentry(conn, installation_id=inst, state_root_id=root, predecessor_epoch=pred_epoch,
                      successor_epoch="succ-3", frame_id=frame_id)
        turn_a = _turn("succ-3", turn_event_id)
        with tempfile.TemporaryDirectory() as d:
            path_a = Path(d) / "log_a.jsonl"
            result_a, meta_a = coordinate_real_turn_with_reentry(conn, path_a, turn_a, env=env)
        self.assertTrue(meta_a["used_reentry"])

        conn_cold = _fresh_db()
        turn_b = _turn("epoch-cold", turn_event_id)
        with tempfile.TemporaryDirectory() as d:
            path_b = Path(d) / "log_b.jsonl"
            result_b = coordinate_real_turn(conn_cold, path_b, turn_b, env=env)

        # signals identical (same turn_event_id)
        for cell in CELLS:
            self.assertEqual(derive_signal(turn_event_id, cell), derive_signal(turn_event_id, cell))

        trans_a = {t.cell_id: t for t in result_a.transitions}
        trans_b = {t.cell_id: t for t in result_b.transitions}
        for cell in CELLS:
            self.assertAlmostEqual(trans_a[cell].old_state, 0.9)
            self.assertEqual(trans_b[cell].old_state, 0.0)
            expected_score_a = proposal_score(trans_a[cell].signal, 0.9)
            self.assertAlmostEqual(trans_a[cell].proposal_score, expected_score_a)
        # broadcast value strictly higher under seeded history (kappa*tanh(0.9) > 0 added to every score)
        self.assertGreater(result_a.broadcast_value, result_b.broadcast_value)


if __name__ == "__main__":
    unittest.main()
