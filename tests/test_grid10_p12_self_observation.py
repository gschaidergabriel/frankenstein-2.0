import sqlite3
import tempfile
import unittest
from pathlib import Path

from frankenstein2.grid10_p7_coordination import (
    CELLS,
    RealTurn,
    coordinate_real_turn,
    read_prior_state,
)
from frankenstein2.grid10_p11_effects import migrate_schema as migrate_p11_schema
from frankenstein2.grid10_p12_self_observation import (
    DEFAULT_STALE_THRESHOLD_S,
    SELF_OBS_EPSILON,
    SelfObservation,
    apply_self_observation,
    collect_self_observations,
    coordinate_real_turn_with_self_observation,
)

ENV_ON = {"STERN_F2WP1207_P7_LIVE": "1"}
ENV_OFF = {"STERN_F2WP1207_P7_LIVE": "0"}


def _fresh_db() -> sqlite3.Connection:
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
            runtime_epoch_id TEXT PRIMARY KEY,
            state_root_id TEXT, installation_id TEXT, host_binding_id TEXT,
            started_at TEXT, predecessor_epoch_id TEXT, termination_reason TEXT,
            schema TEXT, session_id TEXT, boot_id TEXT, ended_at TEXT,
            termination_evidence TEXT, successor_epoch_id TEXT, confidence REAL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE f2_reentry_record (
            reentry_id TEXT PRIMARY KEY, entity_id TEXT, installation_id TEXT,
            state_root_id TEXT, predecessor_epoch_id TEXT, successor_epoch_id TEXT NOT NULL,
            predecessor_termination_reason TEXT, predecessor_confidence REAL,
            predecessor_boot_id TEXT, successor_boot_id TEXT, last_grid10_frame_id TEXT,
            last_work_ref TEXT, created_at TEXT NOT NULL, schema TEXT NOT NULL
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
        CREATE TABLE f2_grid10_cell_observation (
            observation_id TEXT PRIMARY KEY, frame_id TEXT, logical_cell_id TEXT,
            input_digest_sha256 TEXT, output_digest_sha256 TEXT, uptake INTEGER,
            reentry_flag INTEGER, conflict_flag INTEGER DEFAULT 0, timing_ms REAL,
            cpu_ru_utime_delta_s REAL, rss_delta_kb INTEGER,
            predecessor_observation_id TEXT, schema TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE retrieval_episodes (
            retrieval_id TEXT PRIMARY KEY, turn_id TEXT, episode_id TEXT,
            causal_id TEXT, session_id TEXT, user_id TEXT, generation INTEGER,
            policy_version INTEGER, mode TEXT, query_hash TEXT,
            query_token_hashes TEXT, selected_memory_ids TEXT,
            shadow_memory_ids TEXT, entry_keys TEXT, budget_chars INTEGER,
            chars_selected INTEGER, status TEXT, ts REAL
        )
        """
    )
    conn.commit()
    migrate_p11_schema(conn)  # real migration path for f2_grid10_effect_journal
    return conn


def _turn(epoch: str, turn_event_id: str = "t-p12-1", session_id: str = None) -> RealTurn:
    return RealTurn(
        frame_id=turn_event_id, turn_event_id=turn_event_id,
        runtime_epoch_id=epoch, session_id=session_id or f"session-{epoch}",
    )


class DbIntegrityFactTests(unittest.TestCase):
    def test_healthy_db_reports_ok_fresh(self):
        conn = _fresh_db()
        obs = collect_self_observations(conn, _turn("epoch-1"))
        facts = {o.fact_type: o for o in obs}
        self.assertIn("DB_INTEGRITY", facts)
        self.assertEqual(facts["DB_INTEGRITY"].value, "ok")
        self.assertEqual(facts["DB_INTEGRITY"].validity, "FRESH")
        self.assertEqual(facts["DB_INTEGRITY"].freshness_s, 0.0)
        self.assertEqual(facts["DB_INTEGRITY"].confidence, 1.0)


class LastEffectStatusFactTests(unittest.TestCase):
    def test_no_rows_yields_none_value_not_crash(self):
        conn = _fresh_db()
        obs = collect_self_observations(conn, _turn("epoch-1"))
        facts = {o.fact_type: o for o in obs}
        self.assertEqual(facts["LAST_EFFECT_STATUS"].value, "NONE")
        self.assertEqual(facts["LAST_EFFECT_STATUS"].validity, "FRESH")

    def test_real_journal_row_is_read_and_typed(self):
        conn = _fresh_db()
        conn.execute(
            "INSERT INTO f2_grid10_effect_journal "
            "(journal_id, request_id, effect_type, schema, frame_id, turn_event_id, "
            " runtime_epoch_id, session_id, condition_key, winner_cell_id, broadcast_value, "
            " payload_json, gate_policy_id, gate_min_broadcast_value, gate_allowed, gate_reason, "
            " gate_decided_at, status, executed_marker_text, executed_at, readback_ok, "
            " readback_row_hash, created_at) "
            "VALUES ('j1','r1','JOURNAL_MARKER','s','f1','t1','epoch-1','s1','ck','G3',0.7,"
            "'{}','p',0.5,1,'ALLOW','2026-09-05T00:00:00Z','EXECUTED','marker',"
            "'2026-09-05T00:00:00Z',1,'hash','2026-09-05T00:00:00Z')"
        )
        conn.commit()
        obs = collect_self_observations(conn, _turn("epoch-1"))
        facts = {o.fact_type: o for o in obs}
        self.assertEqual(facts["LAST_EFFECT_STATUS"].value, "EXECUTED")
        self.assertEqual(facts["LAST_EFFECT_STATUS"].evidence_ref, "journal_id=j1")
        self.assertEqual(facts["LAST_EFFECT_STATUS"].confidence, 0.95)


class RuntimeEpochChangedFactTests(unittest.TestCase):
    def test_no_reentry_record_is_false(self):
        conn = _fresh_db()
        obs = collect_self_observations(conn, _turn("epoch-1"))
        facts = {o.fact_type: o for o in obs}
        self.assertEqual(facts["RUNTIME_EPOCH_CHANGED"].value, False)
        self.assertNotIn("PREDECESSOR_TERMINATION", facts)

    def test_reentry_record_propagates_p9_confidence_verbatim(self):
        conn = _fresh_db()
        conn.execute(
            "INSERT INTO f2_reentry_record (reentry_id, entity_id, installation_id, state_root_id, "
            "predecessor_epoch_id, successor_epoch_id, predecessor_termination_reason, "
            "predecessor_confidence, predecessor_boot_id, successor_boot_id, last_grid10_frame_id, "
            "last_work_ref, created_at, schema) VALUES "
            "('re1', 'e1', 'inst1', 'sr1', 'pred-epoch', 'epoch-1', 'CLEAN_EXIT', 0.95, "
            "'boot-old', 'boot-new', NULL, NULL, '2026-09-05T00:00:00Z', 'schema/v1')"
        )
        conn.commit()
        obs = collect_self_observations(conn, _turn("epoch-1"))
        facts = {o.fact_type: o for o in obs}
        self.assertEqual(facts["RUNTIME_EPOCH_CHANGED"].value, True)
        self.assertIn("PREDECESSOR_TERMINATION", facts)
        self.assertEqual(facts["PREDECESSOR_TERMINATION"].value, "CLEAN_EXIT")
        # NOT invented -- literally P9's own confidence number, unmodified.
        self.assertEqual(facts["PREDECESSOR_TERMINATION"].confidence, 0.95)


class RetrievalHitCountFactTests(unittest.TestCase):
    def test_no_rows_at_all(self):
        conn = _fresh_db()
        obs = collect_self_observations(conn, _turn("epoch-1"))
        facts = {o.fact_type: o for o in obs}
        self.assertEqual(facts["RETRIEVAL_HIT_COUNT"].value, 0)
        self.assertEqual(facts["RETRIEVAL_HIT_COUNT"].confidence, 1.0)

    def test_exact_session_match_beats_fallback(self):
        conn = _fresh_db()
        conn.execute(
            "INSERT INTO retrieval_episodes VALUES "
            "('ret1','t1','ep1','c1','sess-A','u',1,1,'SHADOW','h','[]','[\"a\",\"b\",\"c\"]',"
            "'[]','[]',100,50,'PRESENT',1788000000.0)"
        )
        conn.execute(
            "INSERT INTO retrieval_episodes VALUES "
            "('ret2','t2','ep2','c2','sess-OTHER','u',1,1,'SHADOW','h','[]','[\"a\"]',"
            "'[]','[]',100,50,'PRESENT',1788000100.0)"
        )
        conn.commit()
        obs = collect_self_observations(conn, _turn("epoch-1", session_id="sess-A"))
        facts = {o.fact_type: o for o in obs}
        self.assertEqual(facts["RETRIEVAL_HIT_COUNT"].value, 3)
        self.assertEqual(facts["RETRIEVAL_HIT_COUNT"].confidence, 0.9)
        self.assertEqual(facts["RETRIEVAL_HIT_COUNT"].detail["match_kind"], "exact_session")

    def test_fallback_to_global_when_no_session_match(self):
        conn = _fresh_db()
        conn.execute(
            "INSERT INTO retrieval_episodes VALUES "
            "('ret1','t1','ep1','c1','sess-OTHER','u',1,1,'SHADOW','h','[]','[\"a\",\"b\"]',"
            "'[]','[]',100,50,'PRESENT',1788000000.0)"
        )
        conn.commit()
        obs = collect_self_observations(conn, _turn("epoch-1", session_id="sess-NEW"))
        facts = {o.fact_type: o for o in obs}
        self.assertEqual(facts["RETRIEVAL_HIT_COUNT"].value, 2)
        self.assertEqual(facts["RETRIEVAL_HIT_COUNT"].confidence, 0.5)
        self.assertEqual(facts["RETRIEVAL_HIT_COUNT"].detail["match_kind"], "fallback_global")


class Grid10FrameFactsTests(unittest.TestCase):
    def _seed_epoch_and_frame(self, conn, conflict=False):
        conn.execute(
            "INSERT INTO f2_runtime_epoch (runtime_epoch_id, installation_id, session_id) "
            "VALUES ('epoch-1','inst-1','session-epoch-1')"
        )
        conn.execute(
            "INSERT INTO f2_grid10_frame (frame_id, installation_id, runtime_epoch_id, "
            "opened_at, status, broadcast_winner_cell, broadcast_value) VALUES "
            "('frame-1','inst-1','epoch-1','2026-09-05T00:00:00Z','CLOSED','G5',0.62)"
        )
        conn.execute(
            "INSERT INTO f2_grid10_cell_observation (observation_id, frame_id, logical_cell_id, conflict_flag) "
            "VALUES ('obs-1','frame-1','G5',?)",
            (1 if conflict else 0,),
        )
        conn.commit()

    def test_last_winner_and_no_conflict(self):
        conn = _fresh_db()
        self._seed_epoch_and_frame(conn, conflict=False)
        obs = collect_self_observations(conn, _turn("epoch-1"))
        facts = {o.fact_type: o for o in obs}
        self.assertEqual(facts["LAST_GRID10_WINNER"].value, "G5")
        self.assertEqual(facts["GRID10_CONFLICT_PRESENT"].value, False)
        self.assertEqual(facts["GRID10_FRAME_FAILURE_COUNT"].value, 0)

    def test_conflict_present(self):
        conn = _fresh_db()
        self._seed_epoch_and_frame(conn, conflict=True)
        obs = collect_self_observations(conn, _turn("epoch-1"))
        facts = {o.fact_type: o for o in obs}
        self.assertEqual(facts["GRID10_CONFLICT_PRESENT"].value, True)


class FailClosedTests(unittest.TestCase):
    def test_missing_table_drops_only_that_fact(self):
        conn = _fresh_db()
        conn.execute("DROP TABLE f2_grid10_effect_journal")
        conn.commit()
        obs = collect_self_observations(conn, _turn("epoch-1"))
        facts = {o.fact_type: o for o in obs}
        self.assertNotIn("LAST_EFFECT_STATUS", facts)
        # other, independent sources still present -- one broken source does
        # not take down the whole collection.
        self.assertIn("DB_INTEGRITY", facts)
        self.assertIn("RETRIEVAL_HIT_COUNT", facts)
        self.assertIn("RUNTIME_EPOCH_CHANGED", facts)

    def test_totally_broken_connection_yields_empty_list_not_exception(self):
        conn = sqlite3.connect(":memory:")
        conn.close()  # every real query against this now raises sqlite3.ProgrammingError
        obs = collect_self_observations(conn, _turn("epoch-1"))
        self.assertEqual(obs, [])


class ApplySelfObservationTests(unittest.TestCase):
    def test_empty_observations_zero_delta(self):
        adjusted, delta, contributions = apply_self_observation({}, [])
        self.assertEqual(delta, 0.0)
        self.assertEqual(contributions, [])
        for cell in CELLS:
            self.assertEqual(adjusted[cell], 0.0)

    def test_executed_vs_denied_symmetric_opposite_delta(self):
        base_obs = dict(
            schema="s", source="src", observed_at="2026-09-05T00:00:00Z",
            evidence_ref="ref", freshness_s=0.0, confidence=0.95, validity="FRESH",
        )
        executed = SelfObservation(fact_type="LAST_EFFECT_STATUS", value="EXECUTED", **base_obs)
        denied = SelfObservation(fact_type="LAST_EFFECT_STATUS", value="DENIED", **base_obs)
        _, delta_exec, _ = apply_self_observation({}, [executed])
        _, delta_deny, _ = apply_self_observation({}, [denied])
        self.assertAlmostEqual(delta_exec, SELF_OBS_EPSILON)
        self.assertAlmostEqual(delta_deny, -SELF_OBS_EPSILON)
        self.assertAlmostEqual(delta_exec - delta_deny, 2 * SELF_OBS_EPSILON)

    def test_uniform_across_all_cells(self):
        base_obs = dict(
            schema="s", source="src", observed_at="2026-09-05T00:00:00Z", fact_type="LAST_EFFECT_STATUS",
            value="EXECUTED", evidence_ref="ref", freshness_s=0.0, confidence=0.95, validity="FRESH",
        )
        prior = {c: float(i) for i, c in enumerate(CELLS)}
        adjusted, delta, _ = apply_self_observation(prior, [SelfObservation(**base_obs)])
        for cell in CELLS:
            self.assertAlmostEqual(adjusted[cell], prior[cell] + delta)

    def test_stale_record_contributes_zero_even_if_labeled_fresh(self):
        forged = SelfObservation(
            schema="s", source="src", observed_at="2000-01-01T00:00:00Z", fact_type="LAST_EFFECT_STATUS",
            value="EXECUTED", evidence_ref="ref", freshness_s=999999999.0, confidence=0.95,
            validity="FRESH",  # forged label -- apply_self_observation must NOT trust this
        )
        _, delta, contributions = apply_self_observation({}, [forged])
        self.assertEqual(delta, 0.0)
        self.assertEqual(contributions[0][2], 0.0)

    def test_unverified_freshness_none_contributes_zero(self):
        unverifiable = SelfObservation(
            schema="s", source="src", observed_at=None, fact_type="LAST_EFFECT_STATUS",
            value="EXECUTED", evidence_ref="ref", freshness_s=None, confidence=0.95, validity="UNVERIFIED",
        )
        _, delta, _ = apply_self_observation({}, [unverifiable])
        self.assertEqual(delta, 0.0)


class WiringTests(unittest.TestCase):
    def test_gate_closed_returns_none_zero_io(self):
        conn = _fresh_db()
        turn = _turn("epoch-1")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "log.jsonl"
            result = coordinate_real_turn_with_self_observation(conn, path, turn, env=ENV_OFF)
        self.assertIsNone(result)
        self.assertFalse(path.exists())

    def test_cold_no_self_state_byte_identical_to_plain_p7(self):
        """No self-observation-relevant rows anywhere (true first-turn-ever
        case) -> delta must be 0.0 -> result must match plain
        coordinate_real_turn field-for-field, same proof technique P10 used
        for its own cold-start fallback."""
        conn_p12 = _fresh_db()
        conn_plain = _fresh_db()
        turn_event_id = "cold-turn-1"
        turn_p12 = _turn("epoch-cold", turn_event_id)
        turn_plain = _turn("epoch-cold", turn_event_id)
        with tempfile.TemporaryDirectory() as d:
            path12 = Path(d) / "p12.jsonl"
            path_plain = Path(d) / "plain.jsonl"
            result_p12, meta = coordinate_real_turn_with_self_observation(
                conn_p12, path12, turn_p12, env=ENV_ON, compose_with_reentry=False,
            )
            result_plain = coordinate_real_turn(conn_plain, path_plain, turn_plain, env=ENV_ON)

        self.assertEqual(meta["delta"], 0.0)
        self.assertEqual(result_p12.winner_cell_id, result_plain.winner_cell_id)
        self.assertAlmostEqual(result_p12.broadcast_value, result_plain.broadcast_value, places=15)
        trans_p12 = {t.cell_id: t for t in result_p12.transitions}
        trans_plain = {t.cell_id: t for t in result_plain.transitions}
        for cell in CELLS:
            self.assertAlmostEqual(trans_p12[cell].proposal_score, trans_plain[cell].proposal_score, places=15)
            self.assertAlmostEqual(trans_p12[cell].new_state, trans_plain[cell].new_state, places=15)

    def test_real_journal_row_shifts_next_cycle_via_wiring(self):
        conn = _fresh_db()
        conn.execute(
            "INSERT INTO f2_grid10_effect_journal "
            "(journal_id, request_id, effect_type, schema, frame_id, turn_event_id, "
            " runtime_epoch_id, session_id, condition_key, winner_cell_id, broadcast_value, "
            " payload_json, gate_policy_id, gate_min_broadcast_value, gate_allowed, gate_reason, "
            " gate_decided_at, status, executed_marker_text, executed_at, readback_ok, "
            " readback_row_hash, created_at) "
            "VALUES ('j1','r1','JOURNAL_MARKER','s','f1','t0','epoch-2','s1','ck','G3',0.7,"
            "'{}','p',0.5,1,'ALLOW','2026-09-05T00:00:00Z','EXECUTED','marker',"
            "'2026-09-05T00:00:00Z',1,'hash','2026-09-05T00:00:00Z')"
        )
        conn.commit()
        turn = _turn("epoch-2", "turn-2")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "log.jsonl"
            result, meta = coordinate_real_turn_with_self_observation(
                conn, path, turn, env=ENV_ON, compose_with_reentry=False,
            )
            self.assertGreater(meta["delta"], 0.0)  # EXECUTED -> positive delta
            self.assertTrue(path.exists())
            logged = path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(logged), 1)


if __name__ == "__main__":
    unittest.main()
