from __future__ import annotations

import hashlib
import unittest

from frankenstein2.familiarity_prediction import (
    MAX_BASIS_POINTS,
    RELATION_MATCH,
    RELATION_MISMATCH,
    RELATION_UNKNOWN,
    SIGNAL_CLASSIFICATION,
    FamiliarityEvidence,
    FamiliarityPredictionError,
    bind_familiarity_to_prediction_residual,
)
from frankenstein2.prediction_contract import PredictionContract


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _residual(*, mismatch: bool):
    prediction = PredictionContract.create(
        prediction_id="prediction:1",
        target_id="target:cup",
        generation=1,
        basis_fingerprint_sha256=_sha("basis"),
        expected_projection={"present": True, "count": 1},
    )
    observed = {"present": True, "count": 2 if mismatch else 1}
    return prediction.observe(
        observation_id="observation:1",
        observation_fingerprint_sha256=_sha("observation"),
        observed_projection=observed,
    )


def _familiarity(score: int = 7000) -> FamiliarityEvidence:
    return FamiliarityEvidence.create(
        familiarity_score_bp=score,
        evidence_refs=("retrieval:memory-7", "familiarity:explicit-score"),
    )


def _bind(residual, familiarity=None, *, contradiction=("observation:contradiction",)):
    familiarity = familiarity or _familiarity()
    return bind_familiarity_to_prediction_residual(
        residual=residual,
        expected_prediction_id=residual.prediction_id,
        expected_generation=residual.generation,
        expected_residual_sha256=residual.sha256(),
        familiarity=familiarity,
        contradiction_evidence_refs=contradiction,
    )


class FamiliarityPredictionTests(unittest.TestCase):
    def test_exact_residual_with_positive_familiarity_emits_match_candidate(self) -> None:
        residual = _residual(mismatch=False)
        signal = _bind(residual)

        self.assertEqual(signal.relation, RELATION_MATCH)
        self.assertTrue(signal.residual_exact_match)
        self.assertEqual(signal.residual_mismatch_count, 0)
        self.assertEqual(signal.attention_priority_bp, 7000)
        self.assertEqual(signal.classification, SIGNAL_CLASSIFICATION)

    def test_exact_residual_without_familiarity_support_is_unknown_not_invented_match(self) -> None:
        residual = _residual(mismatch=False)
        signal = _bind(residual, _familiarity(0), contradiction=())

        self.assertEqual(signal.relation, RELATION_UNKNOWN)
        self.assertTrue(signal.residual_exact_match)
        self.assertEqual(signal.attention_priority_bp, 0)

    def test_mismatch_cannot_be_suppressed_by_high_familiarity(self) -> None:
        residual = _residual(mismatch=True)
        signal = _bind(residual, _familiarity(MAX_BASIS_POINTS))

        self.assertEqual(signal.relation, RELATION_MISMATCH)
        self.assertFalse(signal.residual_exact_match)
        self.assertGreater(signal.residual_mismatch_count, 0)
        self.assertEqual(signal.attention_priority_bp, MAX_BASIS_POINTS)
        self.assertEqual(
            signal.contradiction_evidence_refs,
            ("observation:contradiction",),
        )

    def test_mismatch_requires_explicit_contradiction_evidence(self) -> None:
        residual = _residual(mismatch=True)

        with self.assertRaisesRegex(
            FamiliarityPredictionError, "requires explicit contradiction evidence"
        ):
            _bind(residual, contradiction=())

    def test_prediction_identity_fence_fails_closed(self) -> None:
        residual = _residual(mismatch=False)

        with self.assertRaisesRegex(FamiliarityPredictionError, "prediction_id fence mismatch"):
            bind_familiarity_to_prediction_residual(
                residual=residual,
                expected_prediction_id="prediction:other",
                expected_generation=residual.generation,
                expected_residual_sha256=residual.sha256(),
                familiarity=_familiarity(),
            )

    def test_generation_fence_fails_closed(self) -> None:
        residual = _residual(mismatch=False)

        with self.assertRaisesRegex(FamiliarityPredictionError, "generation fence mismatch"):
            bind_familiarity_to_prediction_residual(
                residual=residual,
                expected_prediction_id=residual.prediction_id,
                expected_generation=residual.generation + 1,
                expected_residual_sha256=residual.sha256(),
                familiarity=_familiarity(),
            )

    def test_residual_digest_fence_fails_closed(self) -> None:
        residual = _residual(mismatch=False)

        with self.assertRaisesRegex(FamiliarityPredictionError, "residual digest fence mismatch"):
            bind_familiarity_to_prediction_residual(
                residual=residual,
                expected_prediction_id=residual.prediction_id,
                expected_generation=residual.generation,
                expected_residual_sha256="0" * 64,
                familiarity=_familiarity(),
            )

    def test_familiarity_score_is_bounded_integer_evidence(self) -> None:
        with self.assertRaisesRegex(FamiliarityPredictionError, "integer basis-point"):
            FamiliarityEvidence.create(
                familiarity_score_bp=0.5,
                evidence_refs=("evidence:float",),
            )
        with self.assertRaisesRegex(FamiliarityPredictionError, "between"):
            FamiliarityEvidence.create(
                familiarity_score_bp=10_001,
                evidence_refs=("evidence:overflow",),
            )

    def test_duplicate_evidence_refs_fail_closed(self) -> None:
        with self.assertRaisesRegex(FamiliarityPredictionError, "duplicate references"):
            FamiliarityEvidence.create(
                familiarity_score_bp=5000,
                evidence_refs=("same", "same"),
            )

    def test_signal_preserves_exact_residual_and_familiarity_provenance(self) -> None:
        residual = _residual(mismatch=True)
        familiarity = _familiarity(4200)
        signal = _bind(
            residual,
            familiarity,
            contradiction=("observation:z", "observation:a"),
        )

        self.assertEqual(signal.prediction_id, residual.prediction_id)
        self.assertEqual(signal.target_id, residual.target_id)
        self.assertEqual(signal.observation_id, residual.observation_id)
        self.assertEqual(signal.generation, residual.generation)
        self.assertEqual(signal.residual_sha256, residual.sha256())
        self.assertEqual(signal.familiarity_evidence_sha256, familiarity.sha256())
        self.assertEqual(signal.familiarity_evidence_refs, familiarity.evidence_refs)
        self.assertEqual(
            signal.contradiction_evidence_refs,
            ("observation:a", "observation:z"),
        )

    def test_binding_is_deterministic_and_input_order_independent_for_refs(self) -> None:
        residual = _residual(mismatch=True)
        familiarity_a = FamiliarityEvidence.create(
            familiarity_score_bp=6100,
            evidence_refs=("evidence:b", "evidence:a"),
        )
        familiarity_b = FamiliarityEvidence.create(
            familiarity_score_bp=6100,
            evidence_refs=("evidence:a", "evidence:b"),
        )

        first = _bind(
            residual,
            familiarity_a,
            contradiction=("contradiction:b", "contradiction:a"),
        )
        second = _bind(
            residual,
            familiarity_b,
            contradiction=("contradiction:a", "contradiction:b"),
        )

        self.assertEqual(first.as_dict(), second.as_dict())
        self.assertEqual(first.sha256(), second.sha256())


if __name__ == "__main__":
    unittest.main()
