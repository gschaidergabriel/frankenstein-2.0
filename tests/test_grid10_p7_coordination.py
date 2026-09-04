import json
import sqlite3
import tempfile
import unittest
from math import tanh
from pathlib import Path

from frankenstein2.grid10_p7_coordination import (
    ALPHA,
    BETA,
    CELLS,
    GAMMA,
    KAPPA,
    LAMBDA_PRIMARY,
    P7_LIVE_CONDITION_KEY,
    RealTurn,
    coordinate_real_turn,
    derive_signal,
    p7_active,
    proposal_score,
    read_prior_state,
    run_coordination_cycle,
    set_p7_active,
    state_update,
)

# Historical condition_keys already present in the real f2_grid10_p6d_state /
# f2_grid10_sweep_state tables at design time (2026-09-04) -- the reserved
# live key must never collide with any of these.
_EXISTING_CONDITION_KEYS = {
    "p6d_baseline", "p6d_cf_a", "p6d_cf_b", "p6d_decay_01", "p6d_decay_05",
    "p6d_decay_09", "p6d_impulse", "p6d_reset", "p6d_shuffle",
    "sw00", "sw025", "sw05", "sw075", "sw075_frozen", "sw075_shuffle", "sw10",
}


def _fresh_db() -> sqlite3.Connection:
    """In-memory DB with just the two real tables this module touches,
    schema copied verbatim from the live unified.db. Never touches the real
    database -- fully hermetic."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE star_konfig(
          schluessel TEXT PRIMARY KEY,
          wert TEXT NOT NULL,
          typ TEXT NOT NULL,
          quelle TEXT,
          geaendert REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE f2_grid10_p6d_state (
            condition_key TEXT NOT NULL,
            logical_cell_id TEXT NOT NULL CHECK (logical_cell_id IN
                ('G1','G2','G3','G4','G5','G6','G7','G8','G9','G10')),
            state_value REAL NOT NULL DEFAULT 0.0,
            updated_at TEXT NOT NULL,
            updated_by_frame_id TEXT,
            won_broadcast_count INTEGER NOT NULL DEFAULT 0,
            schema TEXT NOT NULL,
            PRIMARY KEY (condition_key, logical_cell_id)
        )
        """
    )
    conn.commit()
    return conn


def _turn(n: int = 0) -> RealTurn:
    return RealTurn(
        frame_id=f"frame-{n}",
        turn_event_id=f"turn-{n}",
        runtime_epoch_id="epoch-1",
        session_id="session-1",
    )


class ReservedKeyTests(unittest.TestCase):
    def test_live_condition_key_does_not_collide_with_history(self):
        self.assertNotIn(P7_LIVE_CONDITION_KEY, _EXISTING_CONDITION_KEYS)


class PureMechanismTests(unittest.TestCase):
    def test_derive_signal_deterministic_and_bounded(self):
        a = derive_signal("turn-x", "G3")
        b = derive_signal("turn-x", "G3")
        self.assertEqual(a, b)
        self.assertTrue(0.0 <= a < 1.0)
        self.assertNotEqual(a, derive_signal("turn-x", "G4"))

    def test_proposal_score_matches_formula(self):
        self.assertAlmostEqual(proposal_score(0.3, 0.5, kappa=KAPPA), 0.3 + KAPPA * tanh(0.5))

    def test_state_update_matches_formula(self):
        got = state_update(0.2, 1.0, 0.9, 0.0, lam=LAMBDA_PRIMARY, alpha=ALPHA, beta=BETA, gamma=GAMMA)
        want = LAMBDA_PRIMARY * 0.2 + ALPHA * 1.0 + BETA * 0.9 - GAMMA * 0.0
        self.assertAlmostEqual(got, want)

    def test_run_coordination_cycle_all_zero_prior_state(self):
        turn = _turn(0)
        result = run_coordination_cycle(turn, {})
        self.assertEqual(len(result.transitions), 10)
        self.assertEqual({t.cell_id for t in result.transitions}, set(CELLS))
        # exactly one winner, uptake=1 only for the winner
        winners = [t for t in result.transitions if t.uptake == 1]
        self.assertEqual(len(winners), 1)
        self.assertEqual(winners[0].cell_id, result.winner_cell_id)
        # broadcast term is nonzero only for the winner
        for t in result.transitions:
            if t.cell_id == result.winner_cell_id:
                self.assertEqual(t.broadcast_term, result.broadcast_value)
            else:
                self.assertEqual(t.broadcast_term, 0.0)
        # recompute the winner independently from raw signal+state formula
        signals = {c: derive_signal(turn.turn_event_id, c) for c in CELLS}
        scores = {c: proposal_score(signals[c], 0.0) for c in CELLS}
        expected_winner = max(scores, key=lambda c: scores[c])
        self.assertEqual(result.winner_cell_id, expected_winner)

    def test_run_coordination_cycle_reentry_uses_prior_state(self):
        turn0 = _turn(0)
        r0 = run_coordination_cycle(turn0, {})
        prior = {t.cell_id: t.new_state for t in r0.transitions}
        turn1 = _turn(1)
        r1 = run_coordination_cycle(turn1, prior)
        # at least one cell's state actually moved due to nonzero prior state
        self.assertTrue(any(
            t1.old_state != 0.0 for t1 in r1.transitions
        ))
        # old_state in cycle 1 matches what cycle 0 persisted (reentry proof)
        for t1 in r1.transitions:
            self.assertAlmostEqual(t1.old_state, prior[t1.cell_id])


class GateTests(unittest.TestCase):
    def test_default_off_when_flag_absent(self):
        conn = _fresh_db()
        self.assertFalse(p7_active(conn, env={}))

    def test_persistent_flag_on(self):
        conn = _fresh_db()
        set_p7_active(conn, True, quelle="test")
        self.assertTrue(p7_active(conn, env={}))
        set_p7_active(conn, False, quelle="test")
        self.assertFalse(p7_active(conn, env={}))

    def test_env_override_wins_over_persistent_flag(self):
        conn = _fresh_db()
        set_p7_active(conn, True, quelle="test")
        self.assertFalse(p7_active(conn, env={"STERN_F2WP1207_P7_LIVE": "0"}))
        set_p7_active(conn, False, quelle="test")
        self.assertTrue(p7_active(conn, env={"STERN_F2WP1207_P7_LIVE": "1"}))


class OffStateZeroDeltaTests(unittest.TestCase):
    """Proves: with the gate closed (default, nothing set), a real-turn call
    produces exactly zero database or log delta."""

    def test_off_state_produces_no_writes(self):
        conn = _fresh_db()
        with tempfile.TemporaryDirectory() as tmp:
            evidence_path = Path(tmp) / "evidence.jsonl"

            before_p6d = conn.execute("SELECT COUNT(*) FROM f2_grid10_p6d_state").fetchone()[0]
            before_konfig = conn.execute("SELECT COUNT(*) FROM star_konfig").fetchone()[0]
            self.assertFalse(evidence_path.exists())

            result = coordinate_real_turn(conn, evidence_path, _turn(0), env={})

            self.assertIsNone(result)
            after_p6d = conn.execute("SELECT COUNT(*) FROM f2_grid10_p6d_state").fetchone()[0]
            after_konfig = conn.execute("SELECT COUNT(*) FROM star_konfig").fetchone()[0]
            self.assertEqual(before_p6d, after_p6d)
            self.assertEqual(before_konfig, after_konfig)
            self.assertFalse(evidence_path.exists())  # no log file ever created


class OnStateRealFlowTests(unittest.TestCase):
    """Proves: with the gate open via an ISOLATED env override (never the
    persistent flag), a real turn flows end to end and is logged/persisted,
    and reentry across two turns is real (second turn reads what the first
    turn wrote)."""

    def test_on_state_via_env_override_persists_and_logs(self):
        conn = _fresh_db()
        env = {"STERN_F2WP1207_P7_LIVE": "1"}
        with tempfile.TemporaryDirectory() as tmp:
            evidence_path = Path(tmp) / "evidence.jsonl"

            result0 = coordinate_real_turn(conn, evidence_path, _turn(0), env=env)
            self.assertIsNotNone(result0)
            self.assertEqual(result0.condition_key, P7_LIVE_CONDITION_KEY)

            rows = conn.execute(
                "SELECT logical_cell_id, state_value, won_broadcast_count, updated_by_frame_id "
                "FROM f2_grid10_p6d_state WHERE condition_key=? ORDER BY logical_cell_id",
                (P7_LIVE_CONDITION_KEY,),
            ).fetchall()
            self.assertEqual(len(rows), 10)
            winner_rows = [r for r in rows if r[2] == 1]
            self.assertEqual(len(winner_rows), 1)
            self.assertEqual(winner_rows[0][0], result0.winner_cell_id)
            for _, _, _, frame_id in rows:
                self.assertEqual(frame_id, "frame-0")

            self.assertTrue(evidence_path.exists())
            lines = evidence_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            logged = json.loads(lines[0])
            self.assertEqual(logged["schema"], "F2WP1207_P7_STATE_TRANSITION/v1")
            self.assertEqual(logged["frame_id"], "frame-0")
            self.assertEqual(len(logged["transitions"]), 10)

            # persistent flag was NEVER touched -- only the env override was used
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM star_konfig").fetchone()[0], 0)

            # second real turn: reentry actually reads back what turn 0 wrote
            prior = read_prior_state(conn, P7_LIVE_CONDITION_KEY)
            self.assertEqual(len(prior), 10)
            result1 = coordinate_real_turn(conn, evidence_path, _turn(1), env=env)
            self.assertIsNotNone(result1)
            for t in result1.transitions:
                self.assertAlmostEqual(t.old_state, prior[t.cell_id])

            lines_after = evidence_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines_after), 2)


if __name__ == "__main__":
    unittest.main()
