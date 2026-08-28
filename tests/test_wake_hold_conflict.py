import unittest

from frankenstein2.wake_hold import (
    ABSTAIN_CONFLICTING_OBSERVATIONS,
    HOLD_CHECKPOINT_SCHEMA,
    OP_EQUALS,
    OP_PRESENT,
    WAKE_ANY,
    WAKE_EVALUATION_SCHEMA,
    HoldCheckpoint,
    WakeCondition,
    WakeObservation,
    evaluate_wake,
)

DIGEST = "a" * 64


def checkpoint(*conditions):
    return HoldCheckpoint.create(
        hold_id="hold-conflict",
        state_id="agency-1",
        generation=7,
        state_sha256=DIGEST,
        wake_policy=WAKE_ANY,
        wake_conditions=conditions,
        provenance_refs=("state:agency-1",),
    )


def observation(oid, key, value):
    return WakeObservation(oid, key, value, (f"observation:{oid}",))


def evaluate(cp, observations):
    return evaluate_wake(
        cp,
        evaluation_id="eval-conflict",
        observed_state_id="agency-1",
        observed_generation=7,
        observed_state_sha256=DIGEST,
        observations=observations,
    )


class WakeConflictTests(unittest.TestCase):
    def test_conflicting_same_key_equals_observations_abstain(self):
        cp = checkpoint(WakeCondition("c1", "door_state", OP_EQUALS, ("spec:door",), "open"))
        result = evaluate(
            cp,
            (
                observation("o1", "door_state", "open"),
                observation("o2", "door_state", "closed"),
            ),
        )
        self.assertFalse(result.wake)
        self.assertEqual(result.classification, ABSTAIN_CONFLICTING_OBSERVATIONS)
        self.assertEqual(result.conflicting_condition_ids, ("c1",))
        self.assertEqual(result.matched_condition_ids, ())
        self.assertEqual(result.unmatched_condition_ids, ())
        self.assertEqual(result.unknown_condition_ids, ())

    def test_conflict_dominates_other_any_policy_match(self):
        cp = checkpoint(
            WakeCondition("c1", "door_state", OP_EQUALS, ("spec:door",), "open"),
            WakeCondition("c2", "receipt.present", OP_PRESENT, ("spec:receipt",), None),
        )
        result = evaluate(
            cp,
            (
                observation("o1", "door_state", "open"),
                observation("o2", "door_state", "closed"),
                observation("o3", "receipt.present", "yes"),
            ),
        )
        self.assertFalse(result.wake)
        self.assertEqual(result.classification, ABSTAIN_CONFLICTING_OBSERVATIONS)
        self.assertEqual(result.conflicting_condition_ids, ("c1",))
        self.assertEqual(result.matched_condition_ids, ("c2",))

    def test_same_key_same_value_is_corroboration_not_conflict(self):
        cp = checkpoint(WakeCondition("c1", "door_state", OP_EQUALS, ("spec:door",), "open"))
        result = evaluate(
            cp,
            (
                observation("o1", "door_state", "open"),
                observation("o2", "door_state", "open"),
            ),
        )
        self.assertTrue(result.wake)
        self.assertEqual(result.conflicting_condition_ids, ())

    def test_conflict_receipt_is_deterministic_under_observation_order(self):
        cp = checkpoint(WakeCondition("c1", "door_state", OP_EQUALS, ("spec:door",), "open"))
        a = observation("o1", "door_state", "open")
        b = observation("o2", "door_state", "closed")
        left = evaluate(cp, (a, b))
        right = evaluate(cp, (b, a))
        self.assertEqual(left.sha256(), right.sha256())
        self.assertEqual(left.as_dict(), right.as_dict())
        self.assertEqual(left.schema, WAKE_EVALUATION_SCHEMA)
        self.assertEqual(left.schema, "FRANKENSTEIN2_WAKE_EVALUATION/v2")
        self.assertEqual(cp.schema, HOLD_CHECKPOINT_SCHEMA)


if __name__ == "__main__":
    unittest.main(verbosity=2)
