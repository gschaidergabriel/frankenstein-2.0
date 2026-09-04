import sqlite3
import tempfile
import unittest
from pathlib import Path

from frankenstein2.grid10_p7_coordination import (
    CELLS,
    P7_LIVE_CONDITION_KEY,
    RealTurn,
    coordinate_real_turn,
    read_prior_state,
)
from frankenstein2.grid10_p11_effects import (
    EffectGateBypassError,
    EffectGatePolicy,
    EffectType,
    Grid10P11EffectsError,
    apply_effect_uptake,
    build_effect_request,
    coordinate_real_turn_with_effects,
    evaluate_gate,
    migrate_schema,
    submit_effect_request,
    _execute_journal_marker,  # gold-test-style bypass check, see below
    _journal_denial,
)


def _fresh_db() -> sqlite3.Connection:
    """In-memory DB, schema copied from the live tables this module touches
    (same convention as test_grid10_p10_workspace_reentry.py). Fully
    hermetic. f2_grid10_effect_journal is created via migrate_schema() --
    exercising the real migration path, not a hand-copied DDL."""
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
    conn.commit()
    migrate_schema(conn)
    return conn


def _turn(epoch: str, turn_event_id: str) -> RealTurn:
    return RealTurn(
        frame_id=turn_event_id, turn_event_id=turn_event_id,
        runtime_epoch_id=epoch, session_id=f"session-{epoch}",
    )


ENV_ON = {"STERN_F2WP1207_P7_LIVE": "1"}
ENV_OFF = {"STERN_F2WP1207_P7_LIVE": "0"}


class MigrationTests(unittest.TestCase):
    def test_creates_table_idempotently(self):
        conn = _fresh_db()
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='f2_grid10_effect_journal'"
        ).fetchone()
        self.assertIsNotNone(row)
        second = migrate_schema(conn)
        self.assertEqual(second["added"], [])  # idempotent: nothing added the 2nd time

    def test_does_not_touch_effects_table(self):
        conn = _fresh_db()
        conn.execute("CREATE TABLE effects (effect_id TEXT PRIMARY KEY, episode_id TEXT)")
        conn.commit()
        migrate_schema(conn)
        # untouched: still 0 rows, schema unchanged
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM effects").fetchone()[0], 0)


class RequestAndGateTests(unittest.TestCase):
    def _real_result(self, conn, turn_event_id="t-gate-1"):
        turn = _turn("epoch-gate", turn_event_id)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "log.jsonl"
            return coordinate_real_turn(conn, path, turn, env=ENV_ON)

    def test_build_effect_request_is_typed_and_carries_provenance(self):
        conn = _fresh_db()
        result = self._real_result(conn)
        req = build_effect_request(result)
        self.assertEqual(req.effect_type, EffectType.JOURNAL_MARKER)
        self.assertEqual(req.turn.turn_event_id, result.turn.turn_event_id)
        self.assertEqual(req.turn.runtime_epoch_id, result.turn.runtime_epoch_id)
        self.assertEqual(req.winner_cell_id, result.winner_cell_id)
        self.assertAlmostEqual(req.broadcast_value, result.broadcast_value)
        self.assertIn("marker_text", req.payload)

    def test_gate_allows_above_threshold_denies_below(self):
        conn = _fresh_db()
        result = self._real_result(conn)
        req = build_effect_request(result)

        low_policy = EffectGatePolicy(policy_id="test-allow", min_broadcast_value=result.broadcast_value - 0.01)
        high_policy = EffectGatePolicy(policy_id="test-deny", min_broadcast_value=result.broadcast_value + 0.01)

        allow_decision = evaluate_gate(req, low_policy)
        deny_decision = evaluate_gate(req, high_policy)
        self.assertTrue(allow_decision.allowed)
        self.assertFalse(deny_decision.allowed)
        self.assertEqual(allow_decision.request_id, req.request_id)
        self.assertEqual(deny_decision.request_id, req.request_id)


class SubmitAndJournalTests(unittest.TestCase):
    def _request(self, conn, turn_event_id="t-submit-1"):
        turn = _turn("epoch-submit", turn_event_id)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "log.jsonl"
            result = coordinate_real_turn(conn, path, turn, env=ENV_ON)
        return result, build_effect_request(result)

    def test_allowed_request_writes_executed_row_with_confirmed_readback(self):
        conn = _fresh_db()
        result, req = self._request(conn)
        policy = EffectGatePolicy("allow-all", min_broadcast_value=-999.0)
        outcome = submit_effect_request(conn, req, policy)

        self.assertTrue(outcome.executed)
        self.assertTrue(outcome.readback_ok)
        row = conn.execute(
            "SELECT status, gate_allowed, readback_ok, executed_marker_text, request_id "
            "FROM f2_grid10_effect_journal WHERE journal_id=?",
            (outcome.journal_id,),
        ).fetchone()
        self.assertEqual(row[0], "EXECUTED")
        self.assertEqual(row[1], 1)
        self.assertEqual(row[2], 1)
        self.assertIsNotNone(row[3])
        self.assertEqual(row[4], req.request_id)

    def test_denied_request_writes_denied_row_no_execution(self):
        conn = _fresh_db()
        result, req = self._request(conn)
        policy = EffectGatePolicy("deny-all", min_broadcast_value=999.0)
        outcome = submit_effect_request(conn, req, policy)

        self.assertFalse(outcome.executed)
        self.assertIsNone(outcome.readback_ok)
        row = conn.execute(
            "SELECT status, gate_allowed, readback_ok, executed_marker_text, executed_at "
            "FROM f2_grid10_effect_journal WHERE journal_id=?",
            (outcome.journal_id,),
        ).fetchone()
        self.assertEqual(row[0], "DENIED")
        self.assertEqual(row[1], 0)
        self.assertIsNone(row[2])
        self.assertIsNone(row[3])
        self.assertIsNone(row[4])

    def test_every_request_gets_exactly_one_journal_row_regardless_of_outcome(self):
        conn = _fresh_db()
        _, req_allow = self._request(conn, "t-a")
        _, req_deny = self._request(conn, "t-b")
        submit_effect_request(conn, req_allow, EffectGatePolicy("allow-all", -999.0))
        submit_effect_request(conn, req_deny, EffectGatePolicy("deny-all", 999.0))
        n = conn.execute("SELECT COUNT(*) FROM f2_grid10_effect_journal").fetchone()[0]
        self.assertEqual(n, 2)


class BypassImpossibilityTests(unittest.TestCase):
    """Structural proof: nothing can reach the EXECUTED-row writer except
    through evaluate_gate's real ALLOW branch (via submit_effect_request)."""

    def _request(self, conn):
        turn = _turn("epoch-bypass", "t-bypass")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "log.jsonl"
            result = coordinate_real_turn(conn, path, turn, env=ENV_ON)
        return build_effect_request(result)

    def test_direct_call_with_denied_decision_is_rejected(self):
        conn = _fresh_db()
        req = self._request(conn)
        deny_policy = EffectGatePolicy("deny-all", 999.0)
        decision = evaluate_gate(req, deny_policy)
        self.assertFalse(decision.allowed)
        with self.assertRaises(EffectGateBypassError):
            _execute_journal_marker(conn, req, decision)
        # and no row was written by the rejected attempt
        n = conn.execute("SELECT COUNT(*) FROM f2_grid10_effect_journal").fetchone()[0]
        self.assertEqual(n, 0)

    def test_direct_call_with_handcrafted_mismatched_allow_decision_is_rejected(self):
        conn = _fresh_db()
        req = self._request(conn)
        from frankenstein2.grid10_p11_effects import GateDecision
        forged = GateDecision(
            request_id="not-the-real-request-id", allowed=True, reason="forged",
            policy_id="forged", min_broadcast_value=-999.0,
            observed_broadcast_value=req.broadcast_value, decided_at="forged",
        )
        with self.assertRaises(EffectGateBypassError):
            _execute_journal_marker(conn, req, forged)

    def test_direct_call_with_non_gatedecision_object_is_rejected(self):
        conn = _fresh_db()
        req = self._request(conn)
        with self.assertRaises(EffectGateBypassError):
            _execute_journal_marker(conn, req, {"allowed": True})  # not a real GateDecision

    def test_journal_denial_refuses_an_allow_decision(self):
        conn = _fresh_db()
        req = self._request(conn)
        allow_decision = evaluate_gate(req, EffectGatePolicy("allow-all", -999.0))
        with self.assertRaises(Grid10P11EffectsError):
            _journal_denial(conn, req, allow_decision)

    def test_single_call_site_of_execute_journal_marker_in_source(self):
        """grep-style structural check on the module's own source: exactly
        one call to _execute_journal_marker( outside its own def line."""
        import frankenstein2.grid10_p11_effects as mod
        src = Path(mod.__file__).read_text(encoding="utf-8")
        call_sites = [
            i for i, line in enumerate(src.splitlines())
            if "_execute_journal_marker(" in line and "def _execute_journal_marker(" not in line
        ]
        self.assertEqual(len(call_sites), 1, f"expected exactly 1 call site, found {call_sites}")


class UptakeAndReentryTests(unittest.TestCase):
    def test_uptake_delta_signs(self):
        from frankenstein2.grid10_p11_effects import EffectOutcome, effect_uptake_delta

        class Dummy:
            def __init__(self, executed, readback_ok):
                self.executed = executed
                self.readback_ok = readback_ok

        self.assertGreater(effect_uptake_delta(Dummy(True, True)), 0.0)
        self.assertEqual(effect_uptake_delta(Dummy(True, False)), 0.0)
        self.assertLess(effect_uptake_delta(Dummy(False, None)), 0.0)

    def test_uptake_is_picked_up_by_next_read_prior_state_call(self):
        """Proves the reentry loop: apply_effect_uptake's delta on the
        winner cell is visible to the NEXT coordinate_real_turn's own
        read_prior_state for the same condition_key -- no new plumbing."""
        conn = _fresh_db()
        turn = _turn("epoch-reentry", "t-reentry-1")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "log.jsonl"
            outcome_result = coordinate_real_turn_with_effects(
                conn, path, turn, EffectGatePolicy("allow-all", -999.0), env=ENV_ON,
            )
        self.assertIsNotNone(outcome_result)
        self.assertTrue(outcome_result.outcome.executed)
        winner = outcome_result.coordination.winner_cell_id

        prior = read_prior_state(conn, P7_LIVE_CONDITION_KEY)
        self.assertAlmostEqual(prior[winner], outcome_result.uptake["new_state"])
        self.assertNotEqual(outcome_result.uptake["delta"], 0.0)


class FullPipelineTests(unittest.TestCase):
    def test_gate_closed_returns_none_zero_io(self):
        conn = _fresh_db()
        turn = _turn("epoch-off", "t-off")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "log.jsonl"
            out = coordinate_real_turn_with_effects(
                conn, path, turn, EffectGatePolicy("whatever", 0.0), env=ENV_OFF,
            )
        self.assertIsNone(out)
        self.assertFalse(path.exists())
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM f2_grid10_effect_journal").fetchone()[0], 0)

    def test_same_internal_state_allow_vs_deny_produces_attributable_difference(self):
        """Mirrors the gold test's ALLOW-vs-DENY design at the unit level:
        SAME winner/broadcast_value (same turn_event_id, fresh identical
        cold-start DBs), gate ALLOWS in one, DENIES in the other -- journal
        has a row in both, only ALLOW shows execution evidence, and the
        uptake fed toward next-turn reentry differs and is attributable."""
        turn_event_id = "t-same-stimulus"

        conn_allow = _fresh_db()
        conn_deny = _fresh_db()
        turn_a = _turn("epoch-allow", turn_event_id)
        turn_d = _turn("epoch-deny", turn_event_id)

        with tempfile.TemporaryDirectory() as d:
            out_allow = coordinate_real_turn_with_effects(
                conn_allow, Path(d) / "a.jsonl", turn_a,
                EffectGatePolicy("allow-all", -999.0), env=ENV_ON,
            )
        with tempfile.TemporaryDirectory() as d:
            out_deny = coordinate_real_turn_with_effects(
                conn_deny, Path(d) / "b.jsonl", turn_d,
                EffectGatePolicy("deny-all", 999.0), env=ENV_ON,
            )

        # same internal state: identical winner + broadcast_value (both cold start, same turn_event_id)
        self.assertEqual(out_allow.coordination.winner_cell_id, out_deny.coordination.winner_cell_id)
        self.assertAlmostEqual(out_allow.coordination.broadcast_value, out_deny.coordination.broadcast_value)

        # (a) journal has a row in both cases
        row_allow = conn_allow.execute(
            "SELECT status, gate_allowed FROM f2_grid10_effect_journal WHERE journal_id=?",
            (out_allow.outcome.journal_id,),
        ).fetchone()
        row_deny = conn_deny.execute(
            "SELECT status, gate_allowed FROM f2_grid10_effect_journal WHERE journal_id=?",
            (out_deny.outcome.journal_id,),
        ).fetchone()
        self.assertEqual(tuple(row_allow), ("EXECUTED", 1))
        self.assertEqual(tuple(row_deny), ("DENIED", 0))

        # (b) only ALLOW has execution evidence
        self.assertTrue(out_allow.outcome.executed)
        self.assertTrue(out_allow.outcome.readback_ok)
        self.assertFalse(out_deny.outcome.executed)
        self.assertIsNone(out_deny.outcome.readback_ok)

        # (c) uptake/readback that would feed the next turn differs and is attributable
        self.assertGreater(out_allow.uptake["delta"], 0.0)
        self.assertLess(out_deny.uptake["delta"], 0.0)
        self.assertNotAlmostEqual(out_allow.uptake["new_state"], out_deny.uptake["new_state"])
        winner = out_allow.coordination.winner_cell_id
        prior_allow = read_prior_state(conn_allow, P7_LIVE_CONDITION_KEY)[winner]
        prior_deny = read_prior_state(conn_deny, P7_LIVE_CONDITION_KEY)[winner]
        self.assertAlmostEqual(prior_allow - prior_deny, 2 * 0.05, places=9)  # 2*EFFECT_UPTAKE_EPSILON, attributable


if __name__ == "__main__":
    unittest.main()
