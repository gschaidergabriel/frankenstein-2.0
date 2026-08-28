from __future__ import annotations

import hashlib
import unittest

from frankenstein2.emergent_retrieval import (
    AXIS_CAUSAL,
    AXIS_GOAL,
    AXIS_SEMANTIC,
    RetrievalCandidate,
    RetrievalNeed,
    RetrievalSignal,
    build_retrieval_plan,
)
from frankenstein2.familiarity_prediction_binding import (
    CLASSIFICATION,
    STATUS_MATCH,
    STATUS_MISMATCH,
    STATUS_UNKNOWN,
    FamiliarityPredictionBinding,
    FamiliarityPredictionBindingError,
)
from frankenstein2.memory_lifecycle import create_memory
from frankenstein2.prediction_contract import PredictionContract


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _residual(*, prediction_id: str = "prediction:1", generation: int = 3, expected=1, observed=1):
    contract = PredictionContract.create(
        prediction_id=prediction_id,
        target_id="agency:state",
        generation=generation,
        basis_fingerprint_sha256=_sha("basis"),
        expected_projection={"value": expected},
    )
    return contract.observe(
        observation_id="observation:1",
        observation_fingerprint_sha256=_sha("observation"),
        observed_projection={"value": observed},
    )


def _result(memory_id: str, score: int, *, selected: bool = True):
    memory = create_memory(
        memory_id=memory_id,
        payload_ref=f"payload:{memory_id}",
        payload_sha256=_sha(f"payload:{memory_id}"),
        provenance_refs=(f"evidence:{memory_id}",),
    )
    signals = (
        RetrievalSignal.create(axis=AXIS_GOAL, score_bp=score, evidence_refs=(f"goal:{memory_id}",)),
        RetrievalSignal.create(axis=AXIS_SEMANTIC, score_bp=score if selected else 0, evidence_refs=(f"semantic:{memory_id}",)),
        RetrievalSignal.create(axis=AXIS_CAUSAL, score_bp=score if selected else 0, evidence_refs=(f"causal:{memory_id}",)),
    )
    candidate = RetrievalCandidate.create(
        memory=memory,
        signals=signals,
        candidate_evidence_refs=(f"candidate:{memory_id}",),
    )
    need = RetrievalNeed.create(
        need_id=f"need:{memory_id}",
        axis_weights_bp={AXIS_GOAL: 10_000, AXIS_SEMANTIC: 10_000, AXIS_CAUSAL: 10_000},
        min_overlap_axes=2,
        limit=4,
        evidence_refs=(f"need-evidence:{memory_id}",),
    )
    plan = build_retrieval_plan(need, (candidate,))
    return plan.selected[0] if selected else plan.not_selected[0]


class FamiliarityPredictionBindingTests(unittest.TestCase):
    def test_exact_residual_match_stays_match_and_preserves_identity(self) -> None:
        residual = _residual(expected=7, observed=7)
        binding = FamiliarityPredictionBinding.create(
            prediction_id=residual.prediction_id,
            generation=residual.generation,
            expected_residual_sha256=residual.sha256(),
            evidence_refs=("binding:evidence",),
        )

        signal = binding.evaluate(residual=residual, retrieval_results=(_result("m:known", 8_000),))

        self.assertEqual(signal.status, STATUS_MATCH)
        self.assertEqual(signal.residual_sha256, residual.sha256())
        self.assertEqual(signal.observation_id, residual.observation_id)
        self.assertEqual(signal.observation_fingerprint_sha256, residual.observation_fingerprint_sha256)
        self.assertEqual(signal.prediction_error_bp, 0)
        self.assertEqual(signal.familiarity_bp, 8_000)
        self.assertEqual(signal.attention_priority_bp, 8_000)
        self.assertEqual(signal.classification, CLASSIFICATION)

    def test_high_familiarity_cannot_suppress_current_mismatch(self) -> None:
        residual = _residual(expected=1, observed=2)
        binding = FamiliarityPredictionBinding.create(
            prediction_id=residual.prediction_id,
            generation=residual.generation,
            expected_residual_sha256=residual.sha256(),
            evidence_refs=("binding:mismatch",),
        )

        signal = binding.evaluate(residual=residual, retrieval_results=(_result("m:familiar", 10_000),))

        self.assertEqual(signal.status, STATUS_MISMATCH)
        self.assertEqual(signal.prediction_error_bp, 10_000)
        self.assertEqual(signal.familiarity_bp, 10_000)
        self.assertEqual(signal.attention_priority_bp, 10_000)

    def test_no_current_residual_is_unknown_even_with_strong_memory(self) -> None:
        binding = FamiliarityPredictionBinding.create(
            prediction_id="prediction:pending",
            generation=4,
            expected_residual_sha256=None,
            evidence_refs=("binding:unknown",),
        )

        signal = binding.evaluate(residual=None, retrieval_results=(_result("m:prior", 9_000),))

        self.assertEqual(signal.status, STATUS_UNKNOWN)
        self.assertIsNone(signal.residual_sha256)
        self.assertIsNone(signal.observation_id)
        self.assertIsNone(signal.prediction_error_bp)
        self.assertEqual(signal.familiarity_bp, 9_000)
        self.assertEqual(signal.attention_priority_bp, 9_000)

    def test_missing_residual_fails_closed_when_digest_was_expected(self) -> None:
        residual = _residual()
        binding = FamiliarityPredictionBinding.create(
            prediction_id=residual.prediction_id,
            generation=residual.generation,
            expected_residual_sha256=residual.sha256(),
            evidence_refs=("binding:fence",),
        )
        with self.assertRaisesRegex(FamiliarityPredictionBindingError, "residual is unavailable"):
            binding.evaluate(residual=None)

    def test_present_residual_requires_explicit_digest_fence(self) -> None:
        residual = _residual()
        binding = FamiliarityPredictionBinding.create(
            prediction_id=residual.prediction_id,
            generation=residual.generation,
            expected_residual_sha256=None,
            evidence_refs=("binding:no-fence",),
        )
        with self.assertRaisesRegex(FamiliarityPredictionBindingError, "requires expected_residual_sha256"):
            binding.evaluate(residual=residual)

    def test_prediction_identity_generation_and_digest_mismatch_fail_closed(self) -> None:
        residual = _residual(prediction_id="prediction:source", generation=5)
        wrong_id = FamiliarityPredictionBinding.create(
            prediction_id="prediction:other",
            generation=5,
            expected_residual_sha256=residual.sha256(),
            evidence_refs=("binding:id",),
        )
        with self.assertRaisesRegex(FamiliarityPredictionBindingError, "prediction_id mismatch"):
            wrong_id.evaluate(residual=residual)

        wrong_generation = FamiliarityPredictionBinding.create(
            prediction_id=residual.prediction_id,
            generation=6,
            expected_residual_sha256=residual.sha256(),
            evidence_refs=("binding:generation",),
        )
        with self.assertRaisesRegex(FamiliarityPredictionBindingError, "generation mismatch"):
            wrong_generation.evaluate(residual=residual)

        wrong_digest = FamiliarityPredictionBinding.create(
            prediction_id=residual.prediction_id,
            generation=residual.generation,
            expected_residual_sha256=_sha("wrong"),
            evidence_refs=("binding:digest",),
        )
        with self.assertRaisesRegex(FamiliarityPredictionBindingError, "residual digest mismatch"):
            wrong_digest.evaluate(residual=residual)

    def test_unselected_retrieval_cannot_be_promoted_to_familiarity_evidence(self) -> None:
        binding = FamiliarityPredictionBinding.create(
            prediction_id="prediction:pending",
            generation=1,
            expected_residual_sha256=None,
            evidence_refs=("binding:reject",),
        )
        with self.assertRaisesRegex(FamiliarityPredictionBindingError, "only selected retrieval"):
            binding.evaluate(residual=None, retrieval_results=(_result("m:weak", 9_000, selected=False),))

    def test_duplicate_memory_identity_fails_closed(self) -> None:
        residual = _residual()
        binding = FamiliarityPredictionBinding.create(
            prediction_id=residual.prediction_id,
            generation=residual.generation,
            expected_residual_sha256=residual.sha256(),
            evidence_refs=("binding:duplicate",),
        )
        first = _result("m:duplicate", 7_000)
        second = _result("m:duplicate", 8_000)
        with self.assertRaisesRegex(FamiliarityPredictionBindingError, "duplicate retrieval memory_id"):
            binding.evaluate(residual=residual, retrieval_results=(first, second))

    def test_result_is_deterministic_across_retrieval_input_order(self) -> None:
        residual = _residual(expected=3, observed=4)
        binding = FamiliarityPredictionBinding.create(
            prediction_id=residual.prediction_id,
            generation=residual.generation,
            expected_residual_sha256=residual.sha256(),
            evidence_refs=("binding:deterministic",),
        )
        a = _result("m:a", 6_000)
        b = _result("m:b", 9_000)

        forward = binding.evaluate(residual=residual, retrieval_results=(a, b))
        reverse = binding.evaluate(residual=residual, retrieval_results=(b, a))

        self.assertEqual(forward.as_dict(), reverse.as_dict())
        self.assertEqual(forward.sha256(), reverse.sha256())
        self.assertEqual(forward.retrieval_memory_ids, ("m:a", "m:b"))
        self.assertEqual(forward.familiarity_bp, 9_000)


if __name__ == "__main__":
    unittest.main()
