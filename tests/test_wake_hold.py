import unittest

from frankenstein2.wake_hold import (
    WAKE_HOLD_STATE_SCHEMA,
    WakeCondition,
    WakeDecision,
    WakeHoldError,
    WakeHoldState,
    WakeObservation,
    WakeProbe,
)


class WakeHoldTest(unittest.TestCase):
    def cond(self, cid, key, operator="PRESENT", expected=None, refs=("src:condition",)):
        return WakeCondition.create(
            condition_id=cid,
            key=key,
            operator=operator,
            expected_value=expected,
            provenance_refs=refs,
        )

    def obs(self, oid, key, value=None, refs=("src:observation",)):
        return WakeObservation.create(
            observation_id=oid,
            key=key,
            value=value,
            provenance_refs=refs,
        )

    def state(self, *, policy="ANY", conditions=None):
        if conditions is None:
            conditions = [self.cond("cond-a", "signal.a")]
        return WakeHoldState.create(
            state_id="wake-state-1",
            generation=3,
            hold_id="hold-1",
            match_policy=policy,
            conditions=conditions,
            checkpoint_refs=("checkpoint:agency:abc", "checkpoint:pulse:def"),
        )

    def probe(self, state, *, observations=(), probe_id="probe-1", **overrides):
        return WakeProbe.create(
            probe_id=probe_id,
            expected_state_id=overrides.get("expected_state_id", state.state_id),
            expected_generation=overrides.get("expected_generation", state.generation),
            expected_state_sha256=overrides.get("expected_state_sha256", state.sha256()),
            observations=observations,
            probe_refs=("entry:observation-batch-1",),
        )

    def test_state_canonical_order_and_digest_are_stable(self):
        a = self.cond("cond-a", "signal.a", refs=("z", "a"))
        b = self.cond("cond-b", "signal.b", "EQUALS", "ready", refs=("b",))
        left = WakeHoldState.create(
            state_id="wake-state-1",
            generation=3,
            hold_id="hold-1",
            match_policy="ALL",
            conditions=(b, a),
            checkpoint_refs=("z:checkpoint", "a:checkpoint"),
        )
        right = WakeHoldState.create(
            state_id="wake-state-1",
            generation=3,
            hold_id="hold-1",
            match_policy="ALL",
            conditions=(a, b),
            checkpoint_refs=("a:checkpoint", "z:checkpoint"),
        )
        self.assertEqual(left.canonical_json(), right.canonical_json())
        self.assertEqual(left.sha256(), right.sha256())

    def test_state_is_explicit_hold_not_scheduler_state(self):
        state = self.state()
        self.assertEqual(state.schema, WAKE_HOLD_STATE_SCHEMA)
        self.assertEqual(
            state.classification,
            "EXPLICIT_HOLD_CHECKPOINT_NOT_SCHEDULER_STATE",
        )
        self.assertNotIn("resume", state.as_dict())
        self.assertNotIn("scheduled", state.as_dict())

    def test_conditions_must_be_typed_nonempty_and_unique(self):
        with self.assertRaises(WakeHoldError):
            self.state(conditions=())
        with self.assertRaises(WakeHoldError):
            WakeHoldState.create(
                state_id="wake-state-1",
                generation=0,
                hold_id="hold-1",
                match_policy="ANY",
                conditions=("not-a-condition",),
                checkpoint_refs=("checkpoint:1",),
            )
        duplicate = self.cond("cond-a", "signal.a")
        with self.assertRaises(WakeHoldError):
            self.state(conditions=(duplicate, duplicate))

    def test_checkpoint_and_condition_provenance_are_required(self):
        with self.assertRaises(WakeHoldError):
            WakeCondition.create(
                condition_id="cond-a",
                key="signal.a",
                operator="PRESENT",
                provenance_refs=(),
            )
        with self.assertRaises(WakeHoldError):
            WakeHoldState.create(
                state_id="wake-state-1",
                generation=0,
                hold_id="hold-1",
                match_policy="ANY",
                conditions=(self.cond("cond-a", "signal.a"),),
                checkpoint_refs=(),
            )

    def test_operator_contract_is_fail_closed(self):
        with self.assertRaises(WakeHoldError):
            self.cond("cond-a", "signal.a", "UNKNOWN")
        with self.assertRaises(WakeHoldError):
            self.cond("cond-a", "signal.a", "PRESENT", expected="must-not-exist")
        with self.assertRaises(WakeHoldError):
            self.cond("cond-a", "signal.a", "INT_GTE", expected=True)
        with self.assertRaises(WakeHoldError):
            self.cond("cond-a", "signal.a", "INT_LTE", expected="5")

    def test_probe_requires_exact_state_id_generation_and_digest(self):
        state = self.state()
        with self.assertRaises(WakeHoldError):
            state.evaluate(self.probe(state, expected_state_id="wake-state-other"))
        with self.assertRaises(WakeHoldError):
            state.evaluate(self.probe(state, expected_generation=4))
        with self.assertRaises(WakeHoldError):
            state.evaluate(self.probe(state, expected_state_sha256="0" * 64))

    def test_probe_observations_are_typed_and_key_unambiguous(self):
        state = self.state()
        with self.assertRaises(WakeHoldError):
            WakeProbe.create(
                probe_id="probe-1",
                expected_state_id=state.state_id,
                expected_generation=state.generation,
                expected_state_sha256=state.sha256(),
                observations=("not-an-observation",),
                probe_refs=("entry:1",),
            )
        with self.assertRaises(WakeHoldError):
            self.probe(
                state,
                observations=(
                    self.obs("obs-1", "signal.a", "first"),
                    self.obs("obs-2", "signal.a", "second"),
                ),
            )

    def test_probe_requires_explicit_provenance_even_when_observations_empty(self):
        state = self.state()
        with self.assertRaises(WakeHoldError):
            WakeProbe.create(
                probe_id="probe-1",
                expected_state_id=state.state_id,
                expected_generation=state.generation,
                expected_state_sha256=state.sha256(),
                observations=(),
                probe_refs=(),
            )

    def test_present_matches_only_an_explicit_observation(self):
        state = self.state(conditions=(self.cond("cond-a", "signal.a"),))
        no_obs = state.evaluate(self.probe(state, observations=()))
        with_obs = state.evaluate(
            self.probe(state, observations=(self.obs("obs-a", "signal.a", None),))
        )
        self.assertEqual(no_obs.decision, "HOLD_REMAINS")
        self.assertEqual(with_obs.decision, "WAKE_MATCH")

    def test_equals_is_type_exact_so_bool_does_not_equal_integer(self):
        state = self.state(
            conditions=(self.cond("cond-a", "signal.a", "EQUALS", expected=1),)
        )
        bool_result = state.evaluate(
            self.probe(state, observations=(self.obs("obs-a", "signal.a", True),))
        )
        int_result = state.evaluate(
            self.probe(state, observations=(self.obs("obs-a", "signal.a", 1),))
        )
        self.assertEqual(bool_result.decision, "HOLD_REMAINS")
        self.assertEqual(int_result.decision, "WAKE_MATCH")

    def test_integer_thresholds_are_deterministic_and_reject_bool_as_value(self):
        state = self.state(
            policy="ALL",
            conditions=(
                self.cond("gte", "counter.a", "INT_GTE", expected=5),
                self.cond("lte", "counter.b", "INT_LTE", expected=10),
            ),
        )
        matched = state.evaluate(
            self.probe(
                state,
                observations=(
                    self.obs("obs-a", "counter.a", 5),
                    self.obs("obs-b", "counter.b", 9),
                ),
            )
        )
        mismatched = state.evaluate(
            self.probe(
                state,
                observations=(
                    self.obs("obs-a", "counter.a", True),
                    self.obs("obs-b", "counter.b", 9),
                ),
                probe_id="probe-2",
            )
        )
        self.assertEqual(matched.decision, "WAKE_MATCH")
        self.assertEqual(mismatched.decision, "HOLD_REMAINS")

    def test_any_policy_needs_one_match(self):
        state = self.state(
            policy="ANY",
            conditions=(
                self.cond("a", "signal.a", "EQUALS", "ready"),
                self.cond("b", "signal.b", "EQUALS", "ready"),
            ),
        )
        result = state.evaluate(
            self.probe(
                state,
                observations=(self.obs("obs-b", "signal.b", "ready"),),
            )
        )
        self.assertEqual(result.decision, "WAKE_MATCH")
        self.assertEqual(result.matched_condition_ids, ("b",))
        self.assertEqual(result.unmatched_condition_ids, ("a",))

    def test_all_policy_requires_every_condition(self):
        state = self.state(
            policy="ALL",
            conditions=(
                self.cond("a", "signal.a"),
                self.cond("b", "signal.b"),
            ),
        )
        partial = state.evaluate(
            self.probe(
                state,
                observations=(self.obs("obs-a", "signal.a", "seen"),),
            )
        )
        full = state.evaluate(
            self.probe(
                state,
                observations=(
                    self.obs("obs-a", "signal.a", "seen"),
                    self.obs("obs-b", "signal.b", "seen"),
                ),
                probe_id="probe-2",
            )
        )
        self.assertEqual(partial.decision, "HOLD_REMAINS")
        self.assertEqual(full.decision, "WAKE_MATCH")

    def test_evaluation_is_pure_and_does_not_advance_generation(self):
        state = self.state()
        before = state.sha256()
        result = state.evaluate(
            self.probe(state, observations=(self.obs("obs-a", "signal.a", "seen"),))
        )
        self.assertEqual(state.generation, 3)
        self.assertEqual(state.sha256(), before)
        self.assertEqual(result.generation, 3)

    def test_decision_is_not_resume_goal_effect_or_completion_authority(self):
        state = self.state()
        result = state.evaluate(
            self.probe(state, observations=(self.obs("obs-a", "signal.a", "seen"),))
        )
        self.assertIsInstance(result, WakeDecision)
        self.assertEqual(result.decision, "WAKE_MATCH")
        self.assertEqual(
            result.classification,
            "PURE_WAKE_MATCH_NOT_WORLD_FACT_NOT_RESUME_AUTHORITY",
        )
        payload = result.as_dict()
        forbidden = {
            "resume",
            "resume_goal",
            "goal_adopted",
            "effect_authorized",
            "effect_executed",
            "completion_verified",
        }
        self.assertTrue(forbidden.isdisjoint(payload.keys()))

    def test_decision_binds_state_and_probe_digests(self):
        state = self.state()
        probe = self.probe(
            state,
            observations=(self.obs("obs-a", "signal.a", "seen"),),
        )
        result = state.evaluate(probe)
        self.assertEqual(result.state_sha256, state.sha256())
        self.assertEqual(result.probe_sha256, probe.sha256())
        self.assertEqual(result.observation_ids, ("obs-a",))
        self.assertEqual(result.sha256(), result.sha256())


if __name__ == "__main__":
    unittest.main()
