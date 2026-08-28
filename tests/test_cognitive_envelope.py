from dataclasses import FrozenInstanceError
import math
import unittest

from frankenstein2.cognitive_envelope import (
    ControlSnapshot,
    EnvelopePolicy,
    EnvelopeState,
    RegulationCandidate,
    SignalBand,
    SignalReadout,
    evaluate_cognitive_envelope,
)


def policy() -> EnvelopePolicy:
    return EnvelopePolicy(
        policy_id="policy:grid10-envelope",
        generation=7,
        bands=(
            SignalBand("latency_ms", 0.0, 0.0, 100.0, 250.0),
            SignalBand("uncertainty", 0.0, 0.0, 0.40, 1.0),
        ),
        evidence_refs=("evidence:policy-review",),
        provenance_refs=("repo:policy@abc123",),
    )


def readout(signal_id: str, value: float | None, generation: int = 3) -> SignalReadout:
    return SignalReadout(
        signal_id=signal_id,
        generation=generation,
        value=value,
        evidence_refs=(f"evidence:{signal_id}:sample",),
        provenance_refs=(f"sensor:{signal_id}@v1",),
    )


class CognitiveEnvelopeTests(unittest.TestCase):
    def test_in_envelope_is_read_only_and_deterministic(self) -> None:
        first = evaluate_cognitive_envelope(
            policy(),
            [readout("latency_ms", 80.0), readout("uncertainty", 0.2)],
        )
        reordered = evaluate_cognitive_envelope(
            policy(),
            [readout("uncertainty", 0.2), readout("latency_ms", 80.0)],
        )
        self.assertIsInstance(first, ControlSnapshot)
        self.assertEqual(first.state, EnvelopeState.IN_ENVELOPE)
        self.assertEqual(first.regulation_candidate, RegulationCandidate.MAINTAIN_CURRENT_LIMITS)
        self.assertFalse(first.fail_closed)
        self.assertFalse(first.effect_authority)
        self.assertFalse(first.completion_authority)
        self.assertFalse(first.state_mutation_authority)
        self.assertEqual(first.snapshot_digest, reordered.snapshot_digest)
        self.assertEqual(first.assessments, reordered.assessments)
        with self.assertRaises(FrozenInstanceError):
            first.state = EnvelopeState.HARD_LIMIT  # type: ignore[misc]

    def test_soft_band_exceedance_is_degraded_candidate_only(self) -> None:
        snapshot = evaluate_cognitive_envelope(
            policy(),
            [readout("latency_ms", 140.0), readout("uncertainty", 0.2)],
        )
        self.assertEqual(snapshot.state, EnvelopeState.DEGRADED)
        self.assertEqual(snapshot.regulation_candidate, RegulationCandidate.REQUEST_DEGRADED_MODE)
        self.assertFalse(snapshot.fail_closed)

    def test_hard_limit_precedes_other_states(self) -> None:
        snapshot = evaluate_cognitive_envelope(
            policy(),
            [readout("latency_ms", 300.0), readout("uncertainty", None)],
        )
        self.assertEqual(snapshot.state, EnvelopeState.HARD_LIMIT)
        self.assertEqual(snapshot.regulation_candidate, RegulationCandidate.REQUEST_CONTAINMENT)
        self.assertTrue(snapshot.fail_closed)

    def test_missing_required_readout_is_unknown_fail_closed(self) -> None:
        snapshot = evaluate_cognitive_envelope(policy(), [readout("latency_ms", 50.0)])
        self.assertEqual(snapshot.state, EnvelopeState.UNKNOWN)
        self.assertEqual(snapshot.regulation_candidate, RegulationCandidate.FAIL_CLOSED_HOLD)
        self.assertTrue(snapshot.fail_closed)
        missing = next(x for x in snapshot.assessments if x.signal_id == "uncertainty")
        self.assertEqual(missing.reason, "REQUIRED_READOUT_MISSING")
        self.assertIsNone(missing.readout_digest)

    def test_missing_provenance_or_evidence_is_unknown(self) -> None:
        missing_evidence = SignalReadout(
            signal_id="latency_ms",
            generation=1,
            value=50.0,
            evidence_refs=(),
            provenance_refs=("sensor:latency",),
        )
        snapshot = evaluate_cognitive_envelope(
            policy(),
            [missing_evidence, readout("uncertainty", 0.1)],
        )
        self.assertEqual(snapshot.state, EnvelopeState.UNKNOWN)
        self.assertEqual(snapshot.assessments[0].reason, "EVIDENCE_MISSING")

    def test_nonfinite_value_is_unknown_and_digestable(self) -> None:
        snapshot = evaluate_cognitive_envelope(
            policy(),
            [readout("latency_ms", math.nan), readout("uncertainty", 0.1)],
        )
        self.assertEqual(snapshot.state, EnvelopeState.UNKNOWN)
        latency = next(x for x in snapshot.assessments if x.signal_id == "latency_ms")
        self.assertEqual(latency.reason, "VALUE_UNKNOWN_OR_NONFINITE")
        self.assertIsNone(latency.value)
        self.assertEqual(len(snapshot.snapshot_digest), 64)

    def test_duplicate_or_unexpected_readouts_fail_closed_by_rejection(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate readout"):
            evaluate_cognitive_envelope(
                policy(),
                [readout("latency_ms", 50.0), readout("latency_ms", 60.0)],
            )
        with self.assertRaisesRegex(ValueError, "absent from policy"):
            evaluate_cognitive_envelope(
                policy(),
                [
                    readout("latency_ms", 50.0),
                    readout("uncertainty", 0.1),
                    readout("unbound", 1.0),
                ],
            )

    def test_policy_validation_rejects_ambiguous_or_invalid_bands(self) -> None:
        with self.assertRaises(ValueError):
            SignalBand("x", 0.0, 10.0, 5.0, 20.0)
        band = SignalBand("x", 0.0, 1.0, 2.0, 3.0)
        with self.assertRaisesRegex(ValueError, "duplicate signal_id"):
            EnvelopePolicy(
                policy_id="p",
                generation=1,
                bands=(band, band),
                evidence_refs=("e",),
                provenance_refs=("p",),
            )

    def test_identity_generation_policy_and_evidence_are_digest_bound(self) -> None:
        base_readouts = [readout("latency_ms", 50.0), readout("uncertainty", 0.1)]
        first = evaluate_cognitive_envelope(policy(), base_readouts)
        changed_generation = evaluate_cognitive_envelope(
            policy(),
            [readout("latency_ms", 50.0, generation=4), readout("uncertainty", 0.1)],
        )
        changed_policy = EnvelopePolicy(
            policy_id="policy:grid10-envelope",
            generation=8,
            bands=policy().bands,
            evidence_refs=policy().evidence_refs,
            provenance_refs=policy().provenance_refs,
        )
        third = evaluate_cognitive_envelope(changed_policy, base_readouts)
        self.assertNotEqual(first.snapshot_digest, changed_generation.snapshot_digest)
        self.assertNotEqual(first.snapshot_digest, third.snapshot_digest)
        self.assertNotEqual(first.policy_digest, third.policy_digest)

    def test_optional_absent_signal_does_not_create_unknown(self) -> None:
        optional_policy = EnvelopePolicy(
            policy_id="p",
            generation=1,
            bands=(
                SignalBand("required", 0.0, 0.0, 1.0, 2.0),
                SignalBand("optional", 0.0, 0.0, 1.0, 2.0, required=False),
            ),
            evidence_refs=("e",),
            provenance_refs=("p",),
        )
        snapshot = evaluate_cognitive_envelope(optional_policy, [readout("required", 0.5)])
        self.assertEqual(snapshot.state, EnvelopeState.IN_ENVELOPE)
        absent = next(x for x in snapshot.assessments if x.signal_id == "optional")
        self.assertEqual(absent.reason, "OPTIONAL_READOUT_ABSENT")


if __name__ == "__main__":
    unittest.main()
