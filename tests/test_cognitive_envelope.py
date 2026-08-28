from __future__ import annotations

import dataclasses
import unittest

from frankenstein2.cognitive_envelope import (
    CANDIDATE_CONTAIN,
    CANDIDATE_NONE,
    CANDIDATE_REDUCE,
    CANDIDATE_UNKNOWN,
    CognitiveEnvelopeError,
    CognitiveEnvelopePolicy,
    DISPOSITION_DEGRADED,
    DISPOSITION_HARD_LIMIT,
    DISPOSITION_UNKNOWN,
    DISPOSITION_WITHIN,
    EnvelopeBand,
    SignalReadout,
    STATUS_OPTIONAL_MISSING,
    STATUS_UNKNOWN_REQUIRED,
    evaluate_control_snapshot,
)


def band(signal_id: str, *, generation: int = 1, required: bool = True) -> EnvelopeBand:
    return EnvelopeBand.create(
        signal_id=signal_id,
        expected_generation=generation,
        hard_min=0,
        soft_min=20,
        soft_max=80,
        hard_max=100,
        required=required,
        evidence_refs=(f"policy:{signal_id}",),
    )


def readout(signal_id: str, value: int, *, generation: int = 1) -> SignalReadout:
    return SignalReadout.create(
        signal_id=signal_id,
        generation=generation,
        value=value,
        evidence_refs=(f"measurement:{signal_id}",),
        provenance_refs=(f"sensor:{signal_id}",),
    )


def policy(*bands: EnvelopeBand) -> CognitiveEnvelopePolicy:
    return CognitiveEnvelopePolicy.create(
        policy_id="grid10-envelope-v1",
        generation=4,
        bands=bands,
        evidence_refs=("authority:trigger4",),
    )


class CognitiveEnvelopeTests(unittest.TestCase):
    def test_canonical_order_and_digest_are_input_order_invariant(self):
        a = policy(band("latency"), band("rss"))
        b = policy(band("rss"), band("latency"))
        first = evaluate_control_snapshot(a, (readout("rss", 50), readout("latency", 40)))
        second = evaluate_control_snapshot(b, (readout("latency", 40), readout("rss", 50)))
        self.assertEqual(a.sha256(), b.sha256())
        self.assertEqual(first.sha256(), second.sha256())
        self.assertEqual(first.disposition, DISPOSITION_WITHIN)
        self.assertEqual(first.regulation_candidate, CANDIDATE_NONE)

    def test_soft_limit_is_degraded_candidate_only(self):
        snapshot = evaluate_control_snapshot(policy(band("rss")), (readout("rss", 10),))
        self.assertEqual(snapshot.disposition, DISPOSITION_DEGRADED)
        self.assertEqual(snapshot.regulation_candidate, CANDIDATE_REDUCE)
        self.assertIn("NOT_CONTROL_WRITER_OR_EFFECT_AUTHORITY", snapshot.classification)

    def test_candidate_falsifier_snapshot_authority_fields_cannot_be_forged(self):
        snapshot = evaluate_control_snapshot(policy(band("rss")), (readout("rss", 50),))
        with self.assertRaises(CognitiveEnvelopeError):
            dataclasses.replace(snapshot, classification="FORGED_CONTROL_WRITER_EFFECT_AUTHORITY")
        with self.assertRaises(CognitiveEnvelopeError):
            dataclasses.replace(snapshot, disposition="FORGED_EFFECT_GRANTED")
        with self.assertRaises(CognitiveEnvelopeError):
            dataclasses.replace(snapshot, regulation_candidate="FORGED_APPLY_NOW")

    def test_candidate_falsifier_signal_result_status_cannot_be_forged(self):
        snapshot = evaluate_control_snapshot(policy(band("rss")), (readout("rss", 50),))
        result = snapshot.signal_results[0]
        with self.assertRaises(CognitiveEnvelopeError):
            dataclasses.replace(result, status="FORGED_HARD_LIMIT_CLEAR")
        with self.assertRaises(CognitiveEnvelopeError):
            dataclasses.replace(result, schema="FORGED_SCHEMA")

    def test_hard_limit_dominates_degraded(self):
        snapshot = evaluate_control_snapshot(
            policy(band("rss"), band("latency")),
            (readout("rss", -1), readout("latency", 10)),
        )
        self.assertEqual(snapshot.disposition, DISPOSITION_HARD_LIMIT)
        self.assertEqual(snapshot.regulation_candidate, CANDIDATE_CONTAIN)

    def test_missing_required_signal_is_explicit_unknown(self):
        snapshot = evaluate_control_snapshot(policy(band("rss")), ())
        self.assertEqual(snapshot.disposition, DISPOSITION_UNKNOWN)
        self.assertEqual(snapshot.regulation_candidate, CANDIDATE_UNKNOWN)
        self.assertEqual(snapshot.signal_results[0].status, STATUS_UNKNOWN_REQUIRED)
        self.assertIsNone(snapshot.signal_results[0].readout_sha256)

    def test_optional_missing_signal_does_not_mint_unknown(self):
        snapshot = evaluate_control_snapshot(
            policy(band("rss"), band("optional", required=False)),
            (readout("rss", 50),),
        )
        self.assertEqual(snapshot.disposition, DISPOSITION_WITHIN)
        statuses = {result.signal_id: result.status for result in snapshot.signal_results}
        self.assertEqual(statuses["optional"], STATUS_OPTIONAL_MISSING)

    def test_generation_mismatch_fails_closed(self):
        with self.assertRaisesRegex(CognitiveEnvelopeError, "generation fence mismatch"):
            evaluate_control_snapshot(policy(band("rss", generation=4)), (readout("rss", 50, generation=3),))

    def test_unexpected_and_duplicate_readouts_fail_closed(self):
        with self.assertRaisesRegex(CognitiveEnvelopeError, "unexpected signal"):
            evaluate_control_snapshot(policy(band("rss")), (readout("other", 50),))
        with self.assertRaisesRegex(CognitiveEnvelopeError, "duplicate signal"):
            evaluate_control_snapshot(policy(band("rss")), (readout("rss", 50), readout("rss", 60)))

    def test_duplicate_policy_signal_and_invalid_limits_fail_closed(self):
        with self.assertRaisesRegex(CognitiveEnvelopeError, "duplicate signal_id"):
            policy(band("rss"), band("rss"))
        with self.assertRaisesRegex(CognitiveEnvelopeError, "hard_min"):
            EnvelopeBand.create(
                signal_id="rss",
                expected_generation=1,
                hard_min=30,
                soft_min=20,
                soft_max=80,
                hard_max=100,
                required=True,
                evidence_refs=("policy:rss",),
            )

    def test_boolean_values_and_empty_evidence_are_rejected(self):
        with self.assertRaises(CognitiveEnvelopeError):
            readout("rss", True)  # type: ignore[arg-type]
        with self.assertRaisesRegex(CognitiveEnvelopeError, "at least one"):
            SignalReadout.create(
                signal_id="rss",
                generation=1,
                value=50,
                evidence_refs=(),
                provenance_refs=("sensor:rss",),
            )

    def test_snapshot_binds_policy_and_readout_identity(self):
        base = evaluate_control_snapshot(policy(band("rss")), (readout("rss", 50),))
        changed = evaluate_control_snapshot(policy(band("rss")), (readout("rss", 51),))
        self.assertNotEqual(base.readout_set_sha256, changed.readout_set_sha256)
        self.assertNotEqual(base.sha256(), changed.sha256())
        self.assertEqual(base.policy_sha256, changed.policy_sha256)


if __name__ == "__main__":
    unittest.main(verbosity=2)
