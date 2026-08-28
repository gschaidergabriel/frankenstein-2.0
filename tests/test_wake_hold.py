import unittest
from frankenstein2.wake_hold import (
    HOLD_CHECKPOINT_SCHEMA,
    HOLD_NO_MATCH,
    OP_EQUALS,
    OP_PRESENT,
    WAKE_ALL,
    WAKE_ANY,
    WAKE_MATCH,
    WAKE_UNKNOWN,
    HoldCheckpoint,
    WakeCondition,
    WakeHoldError,
    WakeObservation,
    evaluate_wake,
)

DIGEST = "a" * 64


def condition(cid="c1", key="job.status", operator=OP_EQUALS, expected="done"):
    return WakeCondition(cid, key, operator, ("source:event",), expected)


def checkpoint(policy=WAKE_ANY, conditions=None):
    return HoldCheckpoint.create(
        hold_id="hold-1", state_id="agency-1", generation=7, state_sha256=DIGEST,
        wake_policy=policy, wake_conditions=conditions or (condition(),),
        provenance_refs=("state:agency-1",),
    )


def observation(oid="o1", key="job.status", value="done"):
    return WakeObservation(oid, key, value, ("observation:explicit",))


def evaluate(cp, observations, *, evaluation_id="eval-1"):
    return evaluate_wake(
        cp, evaluation_id=evaluation_id, observed_state_id="agency-1",
        observed_generation=7, observed_state_sha256=DIGEST, observations=observations,
    )


class WakeHoldTests(unittest.TestCase):
    def test_checkpoint_is_deterministic_and_order_normalized(self):
        a = WakeCondition("b", "b.key", OP_PRESENT, ("p:2",), None)
        b = WakeCondition("a", "a.key", OP_EQUALS, ("p:1",), "yes")
        cp1 = checkpoint(conditions=(a, b))
        cp2 = checkpoint(conditions=(b, a))
        self.assertEqual(cp1.schema, HOLD_CHECKPOINT_SCHEMA)
        self.assertEqual(cp1.wake_conditions, cp2.wake_conditions)
        self.assertEqual(cp1.sha256(), cp2.sha256())

    def test_any_policy_wakes_only_from_explicit_match(self):
        result = evaluate(checkpoint(), (observation(),))
        self.assertIs(result.wake, True)
        self.assertEqual(result.classification, WAKE_MATCH)
        self.assertEqual(result.matched_condition_ids, ("c1",))
        self.assertEqual(result.unknown_condition_ids, ())

    def test_missing_observation_is_unknown_not_no_match(self):
        result = evaluate(checkpoint(), ())
        self.assertIsNone(result.wake)
        self.assertEqual(result.classification, WAKE_UNKNOWN)
        self.assertEqual(result.matched_condition_ids, ())
        self.assertEqual(result.unmatched_condition_ids, ())
        self.assertEqual(result.unknown_condition_ids, ("c1",))

    def test_explicit_nonmatching_observation_is_definite_no_match(self):
        result = evaluate(checkpoint(), (observation(value="running"),))
        self.assertIs(result.wake, False)
        self.assertEqual(result.classification, HOLD_NO_MATCH)
        self.assertEqual(result.unmatched_condition_ids, ("c1",))
        self.assertEqual(result.unknown_condition_ids, ())

    def test_all_policy_is_three_valued(self):
        cp = checkpoint(
            policy=WAKE_ALL,
            conditions=(
                condition("c1", "job.status", OP_EQUALS, "done"),
                WakeCondition("c2", "receipt.present", OP_PRESENT, ("spec:receipt",), None),
            ),
        )
        partial = evaluate(cp, (observation(),))
        self.assertIsNone(partial.wake)
        self.assertEqual(partial.classification, WAKE_UNKNOWN)
        self.assertEqual(partial.matched_condition_ids, ("c1",))
        self.assertEqual(partial.unknown_condition_ids, ("c2",))

        full = evaluate(
            cp,
            (observation(), observation("o2", "receipt.present", "yes")),
            evaluation_id="eval-2",
        )
        self.assertIs(full.wake, True)
        self.assertEqual(full.classification, WAKE_MATCH)

        definite_failure = evaluate(
            cp,
            (
                observation(value="running"),
                observation("o2", "receipt.present", "yes"),
            ),
            evaluation_id="eval-3",
        )
        self.assertIs(definite_failure.wake, False)
        self.assertEqual(definite_failure.classification, HOLD_NO_MATCH)

    def test_any_policy_match_overrides_other_unknown_condition(self):
        cp = checkpoint(
            policy=WAKE_ANY,
            conditions=(
                condition("c1", "job.status", OP_EQUALS, "done"),
                condition("c2", "other.status", OP_EQUALS, "ready"),
            ),
        )
        result = evaluate(cp, (observation(),))
        self.assertIs(result.wake, True)
        self.assertEqual(result.matched_condition_ids, ("c1",))
        self.assertEqual(result.unknown_condition_ids, ("c2",))

    def test_any_policy_without_match_preserves_unknown(self):
        cp = checkpoint(
            policy=WAKE_ANY,
            conditions=(
                condition("c1", "job.status", OP_EQUALS, "done"),
                condition("c2", "other.status", OP_EQUALS, "ready"),
            ),
        )
        result = evaluate(cp, (observation(value="running"),))
        self.assertIsNone(result.wake)
        self.assertEqual(result.unmatched_condition_ids, ("c1",))
        self.assertEqual(result.unknown_condition_ids, ("c2",))

    def test_state_id_fence_fails_closed(self):
        with self.assertRaisesRegex(WakeHoldError, "state_id fence mismatch"):
            evaluate_wake(checkpoint(), evaluation_id="eval-1", observed_state_id="other",
                          observed_generation=7, observed_state_sha256=DIGEST, observations=(observation(),))

    def test_generation_fence_fails_closed(self):
        with self.assertRaisesRegex(WakeHoldError, "generation fence mismatch"):
            evaluate_wake(checkpoint(), evaluation_id="eval-1", observed_state_id="agency-1",
                          observed_generation=8, observed_state_sha256=DIGEST, observations=(observation(),))

    def test_digest_fence_fails_closed(self):
        with self.assertRaisesRegex(WakeHoldError, "state_sha256 fence mismatch"):
            evaluate_wake(checkpoint(), evaluation_id="eval-1", observed_state_id="agency-1",
                          observed_generation=7, observed_state_sha256="b" * 64, observations=(observation(),))

    def test_duplicate_observation_identity_is_rejected(self):
        with self.assertRaisesRegex(WakeHoldError, "duplicate observation_id"):
            evaluate(checkpoint(), (observation(), observation(value="running")))

    def test_contradictory_same_key_equals_observations_are_unknown(self):
        cp = checkpoint()
        result = evaluate(
            cp,
            (
                observation("o1", "job.status", "done"),
                observation("o2", "job.status", "running"),
            ),
        )
        self.assertIsNone(result.wake)
        self.assertEqual(result.classification, WAKE_UNKNOWN)
        self.assertEqual(result.matched_condition_ids, ())
        self.assertEqual(result.unmatched_condition_ids, ())
        self.assertEqual(result.unknown_condition_ids, ("c1",))

    def test_same_key_same_value_repeated_evidence_can_match(self):
        result = evaluate(
            checkpoint(),
            (
                observation("o1", "job.status", "done"),
                observation("o2", "job.status", "done"),
            ),
        )
        self.assertIs(result.wake, True)
        self.assertEqual(result.classification, WAKE_MATCH)

    def test_present_operator_is_not_ambiguous_when_multiple_values_exist(self):
        cp = checkpoint(
            conditions=(WakeCondition("c1", "receipt.present", OP_PRESENT, ("p",), None),)
        )
        result = evaluate(
            cp,
            (
                observation("o1", "receipt.present", "a"),
                observation("o2", "receipt.present", "b"),
            ),
        )
        self.assertIs(result.wake, True)
        self.assertEqual(result.classification, WAKE_MATCH)

    def test_invalid_condition_shapes_fail_closed(self):
        with self.assertRaisesRegex(WakeHoldError, "requires expected_value"):
            WakeCondition("c", "k", OP_EQUALS, ("p",), None)
        with self.assertRaisesRegex(WakeHoldError, "must not carry expected_value"):
            WakeCondition("c", "k", OP_PRESENT, ("p",), "x")

    def test_deterministic_receipt_has_no_effect_completion_or_scheduler_authority(self):
        cp = checkpoint()
        result1 = evaluate(cp, (observation(),))
        result2 = evaluate(cp, (observation(),))
        self.assertEqual(result1.sha256(), result2.sha256())
        payload = result1.as_dict()
        self.assertNotIn("effect", payload)
        self.assertNotIn("completion", payload)
        self.assertNotIn("schedule", payload)
        self.assertNotIn("resume", payload)

    def test_unknown_receipt_binds_observation_identity_and_is_deterministic(self):
        cp = checkpoint()
        obs = (
            observation("o1", "job.status", "done"),
            observation("o2", "job.status", "running"),
        )
        left = evaluate(cp, obs)
        right = evaluate(cp, tuple(reversed(obs)))
        self.assertEqual(left.sha256(), right.sha256())
        self.assertEqual(left.observation_ids, ("o1", "o2"))
        self.assertEqual(left.unknown_condition_ids, ("c1",))


if __name__ == "__main__":
    unittest.main()
