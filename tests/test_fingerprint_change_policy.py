import unittest

from frankenstein2.fingerprint_change_policy import (
    POLICY_IDENTITY_CHANGED,
    POLICY_PROJECTION_CHANGED,
    FingerprintChangePolicyError,
    evaluate_fingerprint_change,
)
from frankenstein2.state_fingerprint import fingerprint_state_projection

SCHEMA = "FRANKENSTEIN2_TEST_PROJECTION/v1"


def fingerprint(generation: int, value: str, *, schema: str = SCHEMA):
    return fingerprint_state_projection(
        projection_schema=schema,
        generation=generation,
        projection={"value": value},
    )


class FingerprintChangePolicyTests(unittest.TestCase):
    def test_generation_only_change_is_not_projection_change_signal(self):
        previous = fingerprint(0, "same")
        current = fingerprint(1, "same")
        decision = evaluate_fingerprint_change(
            previous,
            current,
            policy=POLICY_PROJECTION_CHANGED,
        )
        self.assertFalse(decision.projection_changed)
        self.assertTrue(decision.identity_changed)
        self.assertFalse(decision.candidate_signal)

    def test_identity_change_policy_is_explicit_and_separate(self):
        previous = fingerprint(0, "same")
        current = fingerprint(1, "same")
        decision = evaluate_fingerprint_change(
            previous,
            current,
            policy=POLICY_IDENTITY_CHANGED,
        )
        self.assertFalse(decision.projection_changed)
        self.assertTrue(decision.identity_changed)
        self.assertTrue(decision.candidate_signal)

    def test_projection_change_is_candidate_signal_under_projection_policy(self):
        previous = fingerprint(0, "before")
        current = fingerprint(1, "after")
        decision = evaluate_fingerprint_change(
            previous,
            current,
            policy=POLICY_PROJECTION_CHANGED,
        )
        self.assertTrue(decision.projection_changed)
        self.assertTrue(decision.identity_changed)
        self.assertTrue(decision.candidate_signal)

    def test_identical_fingerprint_has_no_signal(self):
        previous = fingerprint(0, "same")
        current = fingerprint(0, "same")
        for policy in (POLICY_PROJECTION_CHANGED, POLICY_IDENTITY_CHANGED):
            with self.subTest(policy=policy):
                decision = evaluate_fingerprint_change(previous, current, policy=policy)
                self.assertFalse(decision.projection_changed)
                self.assertFalse(decision.identity_changed)
                self.assertFalse(decision.candidate_signal)

    def test_projection_schema_mismatch_fails_closed(self):
        previous = fingerprint(0, "same")
        current = fingerprint(1, "same", schema="FRANKENSTEIN2_OTHER_PROJECTION/v1")
        with self.assertRaisesRegex(FingerprintChangePolicyError, "projection schema mismatch"):
            evaluate_fingerprint_change(
                previous,
                current,
                policy=POLICY_PROJECTION_CHANGED,
            )

    def test_generation_rollback_fails_closed(self):
        previous = fingerprint(3, "same")
        current = fingerprint(2, "same")
        with self.assertRaisesRegex(FingerprintChangePolicyError, "moved backwards"):
            evaluate_fingerprint_change(
                previous,
                current,
                policy=POLICY_IDENTITY_CHANGED,
            )

    def test_unknown_policy_fails_closed(self):
        with self.assertRaisesRegex(FingerprintChangePolicyError, "unsupported"):
            evaluate_fingerprint_change(
                fingerprint(0, "same"),
                fingerprint(1, "same"),
                policy="FINGERPRINT_CHANGED",
            )

    def test_decision_has_no_action_effect_wake_or_completion_authority(self):
        decision = evaluate_fingerprint_change(
            fingerprint(0, "before"),
            fingerprint(1, "after"),
            policy=POLICY_PROJECTION_CHANGED,
        )
        payload = decision.as_dict()
        for forbidden in (
            "selected_action",
            "act",
            "delegate",
            "effect",
            "completion",
            "wake",
            "resume",
        ):
            self.assertNotIn(forbidden, payload)

    def test_decision_is_deterministic(self):
        previous = fingerprint(4, "before")
        current = fingerprint(5, "after")
        left = evaluate_fingerprint_change(
            previous,
            current,
            policy=POLICY_PROJECTION_CHANGED,
        )
        right = evaluate_fingerprint_change(
            previous,
            current,
            policy=POLICY_PROJECTION_CHANGED,
        )
        self.assertEqual(left.canonical_json(), right.canonical_json())
        self.assertEqual(left.sha256(), right.sha256())


if __name__ == "__main__":
    unittest.main(verbosity=2)
