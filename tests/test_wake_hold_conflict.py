import unittest

from frankenstein2.wake_hold import (
    ABSTAIN_CONFLICTING_OBSERVATIONS,
    HOLD_CHECKPOINT_SCHEMA,
    OP_EQUALS,
    OP_PRESENT,
    WAKE_ANY,
    WAKE_CONDITION_MATCH,
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


def observation(oid, key, value, provenance_refs=None):
    if provenance_refs is None:
        provenance_refs = (f"observation:{oid}",)
    return WakeObservation(oid, key, value, provenance_refs)


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

    def test_clean_any_match_is_decisive_over_other_condition_conflict(self):
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
        self.assertTrue(result.wake)
        self.assertEqual(result.classification, WAKE_CONDITION_MATCH)
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
        self.assertEqual(left.schema, "FRANKENSTEIN2_WAKE_EVALUATION/v1")
        self.assertEqual(cp.schema, HOLD_CHECKPOINT_SCHEMA)

    def test_receipt_digest_changes_when_observation_value_changes(self):
        cp = checkpoint(WakeCondition("c1", "door_state", OP_PRESENT, ("spec:door",), None))
        left = evaluate(cp, (observation("o1", "door_state", "open"),))
        right = evaluate(cp, (observation("o1", "door_state", "closed"),))
        self.assertEqual(left.observation_ids, right.observation_ids)
        self.assertEqual(left.classification, right.classification)
        self.assertNotEqual(left.observations_sha256, right.observations_sha256)
        self.assertNotEqual(left.sha256(), right.sha256())

    def test_receipt_digest_changes_when_observation_provenance_changes(self):
        cp = checkpoint(WakeCondition("c1", "door_state", OP_PRESENT, ("spec:door",), None))
        left = evaluate(
            cp,
            (observation("o1", "door_state", "open", ("sensor:left", "packet:1")),),
        )
        right = evaluate(
            cp,
            (observation("o1", "door_state", "open", ("sensor:right", "packet:1")),),
        )
        self.assertEqual(left.observation_ids, right.observation_ids)
        self.assertEqual(left.classification, right.classification)
        self.assertNotEqual(left.observations_sha256, right.observations_sha256)
        self.assertNotEqual(left.sha256(), right.sha256())

    def test_observation_payload_digest_is_order_normalized(self):
        cp = checkpoint(WakeCondition("c1", "door_state", OP_PRESENT, ("spec:door",), None))
        a = observation("o1", "door_state", "open", ("packet:1", "sensor:left"))
        b = observation("o2", "door_state", "closed", ("packet:2", "sensor:right"))
        left = evaluate(cp, (a, b))
        right = evaluate(cp, (b, a))
        self.assertEqual(left.observations_sha256, right.observations_sha256)
        self.assertEqual(left.sha256(), right.sha256())
        self.assertEqual(len(left.observations_sha256), 64)


if __name__ == "__main__":
    unittest.main(verbosity=2)
