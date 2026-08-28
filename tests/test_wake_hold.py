import unittest
from frankenstein2.wake_hold import (
    ABSTAIN_NOT_OBSERVED,
    HOLD_CHECKPOINT_SCHEMA,
    HOLD_CONDITION_NOT_MATCHED,
    OP_EQUALS,
    OP_PRESENT,
    WAKE_ALL,
    WAKE_ANY,
    WAKE_CONDITION_MATCH,
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


def evaluate(cp, observations):
    return evaluate_wake(
        cp, evaluation_id="eval-1", observed_state_id="agency-1",
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
        self.assertTrue(result.wake)
        self.assertEqual(result.classification, WAKE_CONDITION_MATCH)
        self.assertEqual(result.matched_condition_ids, ("c1",))
        self.assertEqual(result.unmatched_condition_ids, ())
        self.assertEqual(result.unknown_condition_ids, ())

    def test_empty_observation_set_is_unknown_not_nonmatch(self):
        result = evaluate(checkpoint(), ())
        self.assertFalse(result.wake)
        self.assertEqual(result.classification, ABSTAIN_NOT_OBSERVED)
        self.assertEqual(result.matched_condition_ids, ())
        self.assertEqual(result.unmatched_condition_ids, ())
        self.assertEqual(result.unknown_condition_ids, ("c1",))

    def test_unrelated_observation_is_unknown_not_nonmatch(self):
        result = evaluate(checkpoint(), (observation(key="other.key", value="running"),))
        self.assertFalse(result.wake)
        self.assertEqual(result.classification, ABSTAIN_NOT_OBSERVED)
        self.assertEqual(result.unmatched_condition_ids, ())
        self.assertEqual(result.unknown_condition_ids, ("c1",))

    def test_explicit_nonmatching_observation_stays_on_hold(self):
        result = evaluate(checkpoint(), (observation(value="running"),))
        self.assertFalse(result.wake)
        self.assertEqual(result.classification, HOLD_CONDITION_NOT_MATCHED)
        self.assertEqual(result.unmatched_condition_ids, ("c1",))
        self.assertEqual(result.unknown_condition_ids, ())

    def test_present_condition_missing_is_unknown(self):
        cp = checkpoint(conditions=(WakeCondition("c1", "receipt.present", OP_PRESENT, ("p",), None),))
        result = evaluate(cp, ())
        self.assertEqual(result.classification, ABSTAIN_NOT_OBSERVED)
        self.assertEqual(result.unknown_condition_ids, ("c1",))

    def test_present_condition_explicitly_observed_matches(self):
        cp = checkpoint(conditions=(WakeCondition("c1", "receipt.present", OP_PRESENT, ("p",), None),))
        result = evaluate(cp, (observation(key="receipt.present", value="anything"),))
        self.assertTrue(result.wake)
        self.assertEqual(result.classification, WAKE_CONDITION_MATCH)

    def test_any_policy_match_dominates_unknown(self):
        cp = checkpoint(
            policy=WAKE_ANY,
            conditions=(
                condition("c1", "job.status", OP_EQUALS, "done"),
                condition("c2", "other.status", OP_EQUALS, "ready"),
            ),
        )
        result = evaluate(cp, (observation(),))
        self.assertTrue(result.wake)
        self.assertEqual(result.classification, WAKE_CONDITION_MATCH)
        self.assertEqual(result.matched_condition_ids, ("c1",))
        self.assertEqual(result.unknown_condition_ids, ("c2",))

    def test_any_policy_unknown_dominates_explicit_nonmatch(self):
        cp = checkpoint(
            policy=WAKE_ANY,
            conditions=(
                condition("c1", "job.status", OP_EQUALS, "done"),
                condition("c2", "other.status", OP_EQUALS, "ready"),
            ),
        )
        result = evaluate(cp, (observation(value="running"),))
        self.assertFalse(result.wake)
        self.assertEqual(result.classification, ABSTAIN_NOT_OBSERVED)
        self.assertEqual(result.unmatched_condition_ids, ("c1",))
        self.assertEqual(result.unknown_condition_ids, ("c2",))

    def test_all_policy_requires_all_explicit_matches(self):
        cp = checkpoint(
            policy=WAKE_ALL,
            conditions=(
                condition("c1", "job.status", OP_EQUALS, "done"),
                WakeCondition("c2", "receipt.present", OP_PRESENT, ("spec:receipt",), None),
            ),
        )
        partial = evaluate(cp, (observation(),))
        self.assertFalse(partial.wake)
        self.assertEqual(partial.classification, ABSTAIN_NOT_OBSERVED)
        self.assertEqual(partial.unknown_condition_ids, ("c2",))
        complete = evaluate(cp, (observation(), observation("o2", "receipt.present", "yes")))
        self.assertTrue(complete.wake)
        self.assertEqual(complete.classification, WAKE_CONDITION_MATCH)

    def test_all_policy_explicit_nonmatch_is_decisive_even_with_unknown(self):
        cp = checkpoint(
            policy=WAKE_ALL,
            conditions=(
                condition("c1", "job.status", OP_EQUALS, "done"),
                condition("c2", "other.status", OP_EQUALS, "ready"),
            ),
        )
        result = evaluate(cp, (observation(value="running"),))
        self.assertFalse(result.wake)
        self.assertEqual(result.classification, HOLD_CONDITION_NOT_MATCHED)
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

    def test_invalid_condition_shapes_fail_closed(self):
        with self.assertRaisesRegex(WakeHoldError, "requires expected_value"):
            WakeCondition("c", "k", OP_EQUALS, ("p",), None)
        with self.assertRaisesRegex(WakeHoldError, "must not carry expected_value"):
            WakeCondition("c", "k", OP_PRESENT, ("p",), "x")

    def test_deterministic_receipt_binds_unknown_and_has_no_authority_fields(self):
        cp = checkpoint()
        result1 = evaluate(cp, ())
        result2 = evaluate(cp, ())
        self.assertEqual(result1.sha256(), result2.sha256())
        self.assertEqual(result1.classification, ABSTAIN_NOT_OBSERVED)
        payload = result1.as_dict()
        self.assertIn("unknown_condition_ids", payload)
        self.assertNotIn("effect", payload)
        self.assertNotIn("completion", payload)
        self.assertNotIn("schedule", payload)
        self.assertNotIn("resume", payload)


if __name__ == "__main__":
    unittest.main()
