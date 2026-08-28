import unittest

from frankenstein2.wake_hold import (
    OP_PRESENT,
    WAKE_ANY,
    WAKE_CONDITION_MATCH,
    WAKE_EVALUATION_SCHEMA,
    HoldCheckpoint,
    WakeCondition,
    WakeObservation,
    evaluate_wake,
)

DIGEST = "a" * 64


def checkpoint():
    return HoldCheckpoint.create(
        hold_id="hold-provenance",
        state_id="agency-1",
        generation=7,
        state_sha256=DIGEST,
        wake_policy=WAKE_ANY,
        wake_conditions=(
            WakeCondition("c1", "receipt.present", OP_PRESENT, ("spec:receipt",), None),
        ),
        provenance_refs=("state:agency-1",),
    )


def observation(
    oid="o1",
    key="receipt.present",
    value="yes",
    refs=("evidence:one",),
):
    return WakeObservation(oid, key, value, refs)


def evaluate(observations):
    return evaluate_wake(
        checkpoint(),
        evaluation_id="eval-provenance",
        observed_state_id="agency-1",
        observed_generation=7,
        observed_state_sha256=DIGEST,
        observations=observations,
    )


class WakeReceiptProvenanceTests(unittest.TestCase):
    def test_same_observation_identity_and_value_but_different_provenance_changes_receipt(self):
        left = evaluate((observation(refs=("evidence:left",)),))
        right = evaluate((observation(refs=("evidence:right",)),))
        self.assertTrue(left.wake and right.wake)
        self.assertEqual(left.classification, WAKE_CONDITION_MATCH)
        self.assertEqual(right.classification, WAKE_CONDITION_MATCH)
        self.assertEqual(left.observation_ids, right.observation_ids)
        self.assertNotEqual(left.observations_sha256, right.observations_sha256)
        self.assertNotEqual(left.sha256(), right.sha256())

    def test_same_identity_and_provenance_but_different_value_changes_receipt_even_when_present_matches(self):
        left = evaluate((observation(value="yes"),))
        right = evaluate((observation(value="different"),))
        self.assertTrue(left.wake and right.wake)
        self.assertEqual(left.classification, WAKE_CONDITION_MATCH)
        self.assertEqual(right.classification, WAKE_CONDITION_MATCH)
        self.assertEqual(left.observation_ids, right.observation_ids)
        self.assertNotEqual(left.observations_sha256, right.observations_sha256)
        self.assertNotEqual(left.sha256(), right.sha256())

    def test_observation_and_provenance_order_are_canonicalized(self):
        cp = HoldCheckpoint.create(
            hold_id="hold-order",
            state_id="agency-1",
            generation=7,
            state_sha256=DIGEST,
            wake_policy=WAKE_ANY,
            wake_conditions=(
                WakeCondition("c1", "a.key", OP_PRESENT, ("spec:a",), None),
                WakeCondition("c2", "b.key", OP_PRESENT, ("spec:b",), None),
            ),
            provenance_refs=("state:agency-1",),
        )
        a_left = observation("a", "a.key", "one", ("evidence:z", "evidence:a"))
        b_left = observation("b", "b.key", "two", ("evidence:b",))
        a_right = observation("a", "a.key", "one", ("evidence:a", "evidence:z"))
        b_right = observation("b", "b.key", "two", ("evidence:b",))
        left = evaluate_wake(
            cp,
            evaluation_id="eval-order",
            observed_state_id="agency-1",
            observed_generation=7,
            observed_state_sha256=DIGEST,
            observations=(b_left, a_left),
        )
        right = evaluate_wake(
            cp,
            evaluation_id="eval-order",
            observed_state_id="agency-1",
            observed_generation=7,
            observed_state_sha256=DIGEST,
            observations=(a_right, b_right),
        )
        self.assertEqual(left.observations_sha256, right.observations_sha256)
        self.assertEqual(left.canonical_json(), right.canonical_json())
        self.assertEqual(left.sha256(), right.sha256())

    def test_generation3_receipt_payload_digest_is_explicit_without_new_authority(self):
        result = evaluate((observation(),))
        self.assertEqual(result.schema, WAKE_EVALUATION_SCHEMA)
        self.assertEqual(result.schema, "FRANKENSTEIN2_WAKE_EVALUATION/v1")
        self.assertEqual(len(result.observations_sha256), 64)
        payload = result.as_dict()
        self.assertIn("observations_sha256", payload)
        self.assertNotIn("effect", payload)
        self.assertNotIn("completion", payload)
        self.assertNotIn("schedule", payload)
        self.assertNotIn("resume", payload)


if __name__ == "__main__":
    unittest.main(verbosity=2)
