from __future__ import annotations

import hashlib
import unittest

from frankenstein2.familiarity_prediction_binding import (
    CLASSIFICATION,
    STATUS_MATCH,
    STATUS_MISMATCH,
    STATUS_UNKNOWN,
    FamiliarityEvidence,
    FamiliarityPredictionBindingError,
    bind_familiarity_to_prediction,
)
from frankenstein2.prediction_contract import PredictionContract


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _residual(*, prediction_id="prediction:1", target_id="target:1", generation=3,
              expected=1, observed=1):
    contract = PredictionContract.create(
        prediction_id=prediction_id,
        target_id=target_id,
        generation=generation,
        basis_fingerprint_sha256=_sha("basis"),
        expected_projection={"value": expected},
    )
    return contract.observe(
        observation_id="observation:1",
        observation_fingerprint_sha256=_sha("observation"),
        observed_projection={"value": observed},
    )


def _known(score=8000, *, target_id="target:1", generation=3):
    return FamiliarityEvidence.known(
        evidence_id="familiarity:1",
        target_id=target_id,
        generation=generation,
        score_bp=score,
        evidence_refs=("retrieval:goal", "retrieval:causal"),
    )


def _bind(residual, familiarity=None, *, expected_digest="auto"):
    if familiarity is None:
        familiarity = _known(target_id=residual.target_id, generation=residual.generation)
    digest = residual.sha256() if expected_digest == "auto" else expected_digest
    return bind_familiarity_to_prediction(
        prediction_id=residual.prediction_id,
        target_id=residual.target_id,
        generation=residual.generation,
        familiarity=familiarity,
        residual=residual,
        expected_residual_sha256=digest,
        evidence_refs=("prediction:receipt", "observation:receipt"),
    )


class FamiliarityPredictionBindingTests(unittest.TestCase):
    def test_exact_match_is_candidate_not_truth(self) -> None:
        residual = _residual(expected=7, observed=7)
        signal = _bind(residual)
        self.assertEqual(signal.status, STATUS_MATCH)
        self.assertEqual(signal.prediction_error_bp, 0)
        self.assertFalse(signal.contradiction_preserved)
        self.assertEqual(signal.classification, CLASSIFICATION)
        self.assertEqual(signal.residual_sha256, residual.sha256())
        self.assertEqual(signal.observation_fingerprint_sha256,
                         residual.observation_fingerprint_sha256)

    def test_high_familiarity_never_suppresses_current_mismatch(self) -> None:
        residual = _residual(expected=1, observed=2)
        signal = _bind(residual, _known(10_000))
        self.assertEqual(signal.status, STATUS_MISMATCH)
        self.assertEqual(signal.prediction_error_bp, 10_000)
        self.assertTrue(signal.contradiction_preserved)
        self.assertEqual(signal.attention_priority_bp, 10_000)

    def test_unknown_familiarity_has_no_fake_score(self) -> None:
        residual = _residual()
        familiarity = FamiliarityEvidence.unknown(
            evidence_id="familiarity:unknown",
            target_id=residual.target_id,
            generation=residual.generation,
            evidence_refs=("retrieval:insufficient",),
        )
        signal = _bind(residual, familiarity)
        self.assertIsNone(signal.familiarity_bp)
        self.assertEqual(signal.status, STATUS_MATCH)

    def test_missing_current_residual_stays_unknown_even_with_strong_familiarity(self) -> None:
        familiarity = _known(9_000, target_id="target:pending", generation=4)
        signal = bind_familiarity_to_prediction(
            prediction_id="prediction:pending",
            target_id="target:pending",
            generation=4,
            familiarity=familiarity,
            residual=None,
            expected_residual_sha256=None,
            evidence_refs=("binding:pending",),
        )
        self.assertEqual(signal.status, STATUS_UNKNOWN)
        self.assertIsNone(signal.residual_sha256)
        self.assertIsNone(signal.prediction_error_bp)
        self.assertEqual(signal.attention_priority_bp, 9_000)

    def test_expected_but_missing_residual_fails_closed(self) -> None:
        familiarity = _known(target_id="target:pending", generation=4)
        with self.assertRaisesRegex(FamiliarityPredictionBindingError, "unavailable"):
            bind_familiarity_to_prediction(
                prediction_id="prediction:pending",
                target_id="target:pending",
                generation=4,
                familiarity=familiarity,
                residual=None,
                expected_residual_sha256=_sha("expected"),
                evidence_refs=("binding:pending",),
            )

    def test_present_residual_requires_digest_fence(self) -> None:
        residual = _residual()
        with self.assertRaisesRegex(FamiliarityPredictionBindingError, "requires"):
            _bind(residual, expected_digest=None)

    def test_wrong_residual_digest_fails_closed(self) -> None:
        residual = _residual()
        with self.assertRaisesRegex(FamiliarityPredictionBindingError, "digest mismatch"):
            _bind(residual, expected_digest=_sha("wrong"))

    def test_target_and_generation_mismatches_fail_closed(self) -> None:
        residual = _residual()
        with self.assertRaisesRegex(FamiliarityPredictionBindingError, "target/generation"):
            _bind(residual, _known(target_id="target:other"))
        with self.assertRaisesRegex(FamiliarityPredictionBindingError, "target/generation"):
            _bind(residual, _known(generation=4))

    def test_familiarity_evidence_is_canonical_and_deterministic(self) -> None:
        left = FamiliarityEvidence.known(
            evidence_id="familiarity:stable", target_id="target:1", generation=3,
            score_bp=5_000, evidence_refs=("z", "a"),
        )
        right = FamiliarityEvidence.known(
            evidence_id="familiarity:stable", target_id="target:1", generation=3,
            score_bp=5_000, evidence_refs=("a", "z"),
        )
        self.assertEqual(left.evidence_refs, ("a", "z"))
        self.assertEqual(left.sha256(), right.sha256())

    def test_unknown_familiarity_rejects_numeric_score(self) -> None:
        with self.assertRaisesRegex(FamiliarityPredictionBindingError, "must not carry"):
            FamiliarityEvidence(
                schema="FRANKENSTEIN2_FAMILIARITY_EVIDENCE/v1",
                evidence_id="familiarity:bad", target_id="target:1", generation=3,
                state="UNKNOWN", score_bp=1, evidence_refs=("e",),
            )

    def test_result_digest_is_deterministic(self) -> None:
        residual = _residual(expected=3, observed=4)
        first = _bind(residual)
        second = _bind(residual)
        self.assertEqual(first.as_dict(), second.as_dict())
        self.assertEqual(first.sha256(), second.sha256())


if __name__ == "__main__":
    unittest.main()
