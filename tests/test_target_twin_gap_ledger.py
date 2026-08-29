from dataclasses import replace
import unittest

from frankenstein2.target_twin_gap_ledger import (
    EVIDENCE_REQUIRED,
    EXPLICIT_NON_EMULATABLE_GAP,
    FAILURE,
    MATCH,
    NO_REPLAY_OBLIGATION,
    OPEN_REPLAY_OBLIGATION,
    PHYSICAL_ONLY,
    PHYSICAL_ONLY_GAP,
    SURPRISE,
    UNKNOWN,
    PhysicalObservationRef,
    TargetTwinGapLedgerError,
    TwinPrediction,
    build_ledger,
    correlate,
)


RELEASE = "a" * 64
RELEASE_2 = "b" * 64
SCENARIO = "c" * 64
PROFILE = "d" * 64
EVIDENCE = "e" * 64
EVIDENCE_2 = "f" * 64


class TargetTwinGapLedgerTests(unittest.TestCase):
    def prediction(self, *, event_key="pipewire.restart", outcome=FAILURE, sequence=10):
        return TwinPrediction.create(
            release_digest=RELEASE,
            scenario_digest=SCENARIO,
            event_key=event_key,
            predicted_outcome=outcome,
            fidelity="T3",
            sequence=sequence,
        )

    def observation(self, *, event_key="pipewire.restart", outcome=FAILURE,
                    evidence=EVIDENCE, sequence=20):
        return PhysicalObservationRef.create(
            release_digest=RELEASE,
            target_profile_digest=PROFILE,
            event_key=event_key,
            observed_outcome=outcome,
            evidence_digest=evidence,
            sequence=sequence,
        )

    def test_prior_exact_prediction_matches_without_replay_obligation(self):
        entry = correlate(self.prediction(), self.observation())
        self.assertEqual(MATCH, entry.classification)
        self.assertEqual(NO_REPLAY_OBLIGATION, entry.replay_state)
        self.assertTrue(entry.prior_prediction_eligible)

    def test_post_hoc_prediction_cannot_be_retroactively_credited(self):
        prediction = self.prediction(sequence=30)
        observation = self.observation(sequence=20)
        entry = correlate(prediction, observation)
        self.assertEqual(SURPRISE, entry.classification)
        self.assertEqual(OPEN_REPLAY_OBLIGATION, entry.replay_state)
        self.assertFalse(entry.prior_prediction_eligible)

    def test_surprise_emits_open_replay_obligation(self):
        prediction = self.prediction(outcome="SUCCESS")
        observation = self.observation(outcome=FAILURE)
        entry = correlate(prediction, observation)
        self.assertEqual(SURPRISE, entry.classification)
        self.assertEqual(OPEN_REPLAY_OBLIGATION, entry.replay_state)

    def test_known_physical_only_blind_spot_stays_explicit(self):
        prediction = self.prediction(outcome=PHYSICAL_ONLY_GAP)
        observation = self.observation(outcome=FAILURE)
        entry = correlate(prediction, observation)
        self.assertEqual(PHYSICAL_ONLY, entry.classification)
        self.assertEqual(EXPLICIT_NON_EMULATABLE_GAP, entry.replay_state)

    def test_missing_physical_evidence_remains_unknown(self):
        observation = self.observation(outcome=UNKNOWN, evidence=UNKNOWN)
        entry = correlate(None, observation)
        self.assertEqual(UNKNOWN, entry.classification)
        self.assertEqual(EVIDENCE_REQUIRED, entry.replay_state)
        self.assertFalse(entry.prior_prediction_eligible)

    def test_concrete_observation_without_evidence_digest_fails_closed(self):
        with self.assertRaises(TargetTwinGapLedgerError):
            self.observation(outcome=FAILURE, evidence=UNKNOWN)

    def test_prediction_and_observation_identity_are_content_bound(self):
        prediction = self.prediction()
        observation = self.observation()
        with self.assertRaises(TargetTwinGapLedgerError):
            replace(prediction, event_key="different.event")
        with self.assertRaises(TargetTwinGapLedgerError):
            replace(observation, observed_outcome="SUCCESS")

    def test_release_mismatch_fails_closed(self):
        observation = PhysicalObservationRef.create(
            release_digest=RELEASE_2,
            target_profile_digest=PROFILE,
            event_key="pipewire.restart",
            observed_outcome=FAILURE,
            evidence_digest=EVIDENCE,
            sequence=20,
        )
        with self.assertRaises(TargetTwinGapLedgerError):
            correlate(self.prediction(), observation)

    def test_ledger_is_order_independent_after_deterministic_normalization(self):
        p1 = self.prediction(event_key="pipewire.restart", sequence=10)
        o1 = self.observation(event_key="pipewire.restart", evidence=EVIDENCE, sequence=20)
        p2 = self.prediction(event_key="permission.camera", outcome="SUCCESS", sequence=11)
        o2 = self.observation(event_key="permission.camera", outcome=FAILURE,
                              evidence=EVIDENCE_2, sequence=21)
        ledger_a = build_ledger(
            release_digest=RELEASE,
            target_profile_digest=PROFILE,
            correlations=[(p1, o1), (p2, o2)],
        )
        ledger_b = build_ledger(
            release_digest=RELEASE,
            target_profile_digest=PROFILE,
            correlations=[(p2, o2), (p1, o1)],
        )
        self.assertEqual(ledger_a.ledger_id, ledger_b.ledger_id)
        self.assertEqual(1, ledger_a.match_count)
        self.assertEqual(1, ledger_a.surprise_count)
        self.assertEqual(1, ledger_a.open_replay_obligation_count)
        self.assertEqual(0, ledger_a.physical_host_credit)
        self.assertFalse(ledger_a.whole_system_acceptance)

    def test_duplicate_observation_is_rejected(self):
        prediction = self.prediction()
        observation = self.observation()
        with self.assertRaises(TargetTwinGapLedgerError):
            build_ledger(
                release_digest=RELEASE,
                target_profile_digest=PROFILE,
                correlations=[(prediction, observation), (prediction, observation)],
            )

    def test_repository_ledger_cannot_be_mutated_into_physical_credit(self):
        ledger = build_ledger(
            release_digest=RELEASE,
            target_profile_digest=PROFILE,
            correlations=[(self.prediction(), self.observation())],
        )
        with self.assertRaises(TargetTwinGapLedgerError):
            replace(ledger, physical_host_credit=1)
        with self.assertRaises(TargetTwinGapLedgerError):
            replace(ledger, whole_system_acceptance=True)


if __name__ == "__main__":
    unittest.main()
