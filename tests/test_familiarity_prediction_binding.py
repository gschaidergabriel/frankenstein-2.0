from __future__ import annotations

from dataclasses import replace
import hashlib
import unittest

from frankenstein2.emergent_retrieval import (
    AXIS_CAUSAL,
    AXIS_GOAL,
    AXIS_SEMANTIC,
    PLAN_CLASSIFICATION,
    PLAN_SCHEMA,
    RetrievalCandidate,
    RetrievalNeed,
    RetrievalPlan,
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


def _candidate(memory_id: str, score: int, *, selected: bool = True) -> RetrievalCandidate:
    memory = create_memory(
        memory_id=memory_id,
        payload_ref=f"payload:{memory_id}",
        payload_sha256=_sha(f"payload:{memory_id}"),
        provenance_refs=(f"evidence:{memory_id}",),
    )
    signals = (
        RetrievalSignal.create(axis=AXIS_GOAL, score_bp=score, evidence_refs=(f"goal:{memory_id}",)),
        RetrievalSignal.create(
            axis=AXIS_SEMANTIC,
            score_bp=score if selected else 0,
            evidence_refs=(f"semantic:{memory_id}",),
        ),
        RetrievalSignal.create(
            axis=AXIS_CAUSAL,
            score_bp=score if selected else 0,
            evidence_refs=(f"causal:{memory_id}",),
        ),
    )
    return RetrievalCandidate.create(
        memory=memory,
        signals=signals,
        candidate_evidence_refs=(f"candidate:{memory_id}",),
    )


def _retrieval_context(*items: tuple[str, int, bool], limit: int = 4):
    need = RetrievalNeed.create(
        need_id="need:familiarity",
        axis_weights_bp={AXIS_GOAL: 10_000, AXIS_SEMANTIC: 10_000, AXIS_CAUSAL: 10_000},
        min_overlap_axes=2,
        limit=limit,
        evidence_refs=("need-evidence:familiarity",),
    )
    candidates = tuple(_candidate(memory_id, score, selected=selected) for memory_id, score, selected in items)
    return need, build_retrieval_plan(need, candidates)


def _binding(residual, need, plan, *, prediction_id=None, generation=None, expected_residual="auto"):
    expected = residual.sha256() if expected_residual == "auto" and residual is not None else expected_residual
    return FamiliarityPredictionBinding.create(
        prediction_id=prediction_id or (residual.prediction_id if residual is not None else "prediction:pending"),
        generation=generation or (residual.generation if residual is not None else 4),
        retrieval_need=need,
        retrieval_plan=plan,
        expected_residual_sha256=expected,
        evidence_refs=("binding:evidence",),
    )


class FamiliarityPredictionBindingTests(unittest.TestCase):
    def test_exact_residual_match_stays_match_and_preserves_full_provenance(self) -> None:
        residual = _residual(expected=7, observed=7)
        need, plan = _retrieval_context(("m:known", 8_000, True))
        binding = _binding(residual, need, plan)
        signal = binding.evaluate(residual=residual, retrieval_need=need, retrieval_plan=plan)
        self.assertEqual(signal.status, STATUS_MATCH)
        self.assertEqual(signal.residual_sha256, residual.sha256())
        self.assertEqual(signal.observation_id, residual.observation_id)
        self.assertEqual(signal.observation_fingerprint_sha256, residual.observation_fingerprint_sha256)
        self.assertEqual(signal.prediction_error_bp, 0)
        self.assertEqual(signal.familiarity_bp, 8_000)
        self.assertEqual(signal.attention_priority_bp, 8_000)
        self.assertEqual(signal.retrieval_need_id, need.need_id)
        self.assertEqual(signal.retrieval_need_sha256, need.sha256())
        self.assertEqual(signal.retrieval_plan_sha256, plan.sha256())
        self.assertEqual(signal.classification, CLASSIFICATION)

    def test_high_familiarity_cannot_suppress_current_mismatch(self) -> None:
        residual = _residual(expected=1, observed=2)
        need, plan = _retrieval_context(("m:familiar", 10_000, True))
        signal = _binding(residual, need, plan).evaluate(
            residual=residual, retrieval_need=need, retrieval_plan=plan
        )
        self.assertEqual(signal.status, STATUS_MISMATCH)
        self.assertEqual(signal.prediction_error_bp, 10_000)
        self.assertEqual(signal.familiarity_bp, 10_000)
        self.assertEqual(signal.attention_priority_bp, 10_000)

    def test_no_current_residual_is_unknown_even_with_strong_memory(self) -> None:
        need, plan = _retrieval_context(("m:prior", 9_000, True))
        binding = _binding(None, need, plan, expected_residual=None)
        signal = binding.evaluate(residual=None, retrieval_need=need, retrieval_plan=plan)
        self.assertEqual(signal.status, STATUS_UNKNOWN)
        self.assertIsNone(signal.residual_sha256)
        self.assertIsNone(signal.observation_id)
        self.assertIsNone(signal.prediction_error_bp)
        self.assertEqual(signal.familiarity_bp, 9_000)
        self.assertEqual(signal.attention_priority_bp, 9_000)

    def test_unselected_result_is_not_consumed_as_familiarity(self) -> None:
        need, plan = _retrieval_context(("m:strong", 8_000, True), ("m:weak", 8_000, False))
        residual = _residual()
        signal = _binding(residual, need, plan).evaluate(
            residual=residual, retrieval_need=need, retrieval_plan=plan
        )
        self.assertEqual(signal.retrieval_memory_ids, ("m:strong",))
        self.assertNotIn("m:weak", signal.retrieval_memory_ids)

    def test_direct_retrieval_result_injection_surface_is_removed(self) -> None:
        residual = _residual()
        need, plan = _retrieval_context(("m:known", 8_000, True))
        binding = _binding(residual, need, plan)
        with self.assertRaises(TypeError):
            binding.evaluate(  # type: ignore[call-arg]
                residual=residual,
                retrieval_need=need,
                retrieval_plan=plan,
                retrieval_results=plan.selected,
            )

    def test_postbinding_result_mutation_is_rejected_by_plan_digest(self) -> None:
        residual = _residual()
        need, canonical_plan = _retrieval_context(("m:known", 8_000, True))
        binding = _binding(residual, need, canonical_plan)
        original = canonical_plan.selected[0]
        forged = replace(original, candidate_sha256=_sha("forged-direct-constructor-result"))
        forged_plan = RetrievalPlan(
            schema=PLAN_SCHEMA,
            need_id=canonical_plan.need_id,
            need_sha256=canonical_plan.need_sha256,
            selected=(forged,),
            not_selected=canonical_plan.not_selected,
            candidate_count=canonical_plan.candidate_count,
            classification=PLAN_CLASSIFICATION,
        )
        with self.assertRaisesRegex(FamiliarityPredictionBindingError, "retrieval plan digest mismatch"):
            binding.evaluate(residual=residual, retrieval_need=need, retrieval_plan=forged_plan)

    def test_prebinding_derived_score_forgery_is_reconstructed_and_rejected(self) -> None:
        residual = _residual()
        need, canonical_plan = _retrieval_context(("m:known", 1_000, True))
        original = canonical_plan.selected[0]
        forged_score = 10_000
        forged = replace(
            original,
            weighted_score_bp=forged_score,
            rank_score=forged_score * original.overlap_count,
        )
        forged_plan = RetrievalPlan(
            schema=PLAN_SCHEMA,
            need_id=canonical_plan.need_id,
            need_sha256=canonical_plan.need_sha256,
            selected=(forged,),
            not_selected=canonical_plan.not_selected,
            candidate_count=canonical_plan.candidate_count,
            classification=PLAN_CLASSIFICATION,
        )
        with self.assertRaisesRegex(FamiliarityPredictionBindingError, "weighted_score_bp"):
            _binding(residual, need, forged_plan)

    def test_need_identity_and_digest_are_fenced(self) -> None:
        residual = _residual()
        need, plan = _retrieval_context(("m:known", 8_000, True))
        binding = _binding(residual, need, plan)
        other_need = RetrievalNeed.create(
            need_id="need:other",
            axis_weights_bp={AXIS_GOAL: 10_000, AXIS_SEMANTIC: 10_000, AXIS_CAUSAL: 10_000},
            min_overlap_axes=2,
            limit=4,
            evidence_refs=("need-evidence:other",),
        )
        with self.assertRaisesRegex(FamiliarityPredictionBindingError, "need_id mismatch"):
            binding.evaluate(residual=residual, retrieval_need=other_need, retrieval_plan=plan)

    def test_plan_need_binding_is_fenced(self) -> None:
        residual = _residual()
        need, plan = _retrieval_context(("m:known", 8_000, True))
        binding = _binding(residual, need, plan)
        forged_plan = replace(plan, need_sha256=_sha("wrong-need"))
        with self.assertRaisesRegex(FamiliarityPredictionBindingError, "not bound to supplied need"):
            binding.evaluate(residual=residual, retrieval_need=need, retrieval_plan=forged_plan)

    def test_plan_candidate_count_and_duplicate_memory_fail_closed(self) -> None:
        residual = _residual()
        need, plan = _retrieval_context(("m:a", 8_000, True), ("m:b", 7_000, True))
        binding = _binding(residual, need, plan)
        bad_count = replace(plan, candidate_count=99)
        with self.assertRaisesRegex(FamiliarityPredictionBindingError, "candidate_count"):
            binding.evaluate(residual=residual, retrieval_need=need, retrieval_plan=bad_count)
        duplicate = replace(plan, selected=(plan.selected[0], plan.selected[0]), candidate_count=2)
        with self.assertRaisesRegex(FamiliarityPredictionBindingError, "duplicate retrieval memory_id"):
            binding.evaluate(residual=residual, retrieval_need=need, retrieval_plan=duplicate)

    def test_missing_and_present_residual_digest_fences_fail_closed(self) -> None:
        residual = _residual()
        need, plan = _retrieval_context(("m:known", 8_000, True))
        expected = _binding(residual, need, plan)
        with self.assertRaisesRegex(FamiliarityPredictionBindingError, "residual is unavailable"):
            expected.evaluate(residual=None, retrieval_need=need, retrieval_plan=plan)
        no_expected = _binding(residual, need, plan, expected_residual=None)
        with self.assertRaisesRegex(FamiliarityPredictionBindingError, "requires expected_residual_sha256"):
            no_expected.evaluate(residual=residual, retrieval_need=need, retrieval_plan=plan)
        wrong = _binding(residual, need, plan, expected_residual=_sha("wrong"))
        with self.assertRaisesRegex(FamiliarityPredictionBindingError, "residual digest mismatch"):
            wrong.evaluate(residual=residual, retrieval_need=need, retrieval_plan=plan)

    def test_prediction_identity_and_generation_fail_closed(self) -> None:
        residual = _residual(prediction_id="prediction:source", generation=5)
        need, plan = _retrieval_context(("m:known", 8_000, True))
        wrong_id = _binding(residual, need, plan, prediction_id="prediction:other")
        with self.assertRaisesRegex(FamiliarityPredictionBindingError, "prediction_id mismatch"):
            wrong_id.evaluate(residual=residual, retrieval_need=need, retrieval_plan=plan)
        wrong_generation = _binding(residual, need, plan, generation=6)
        with self.assertRaisesRegex(FamiliarityPredictionBindingError, "generation mismatch"):
            wrong_generation.evaluate(residual=residual, retrieval_need=need, retrieval_plan=plan)

    def test_signal_digest_is_deterministic_for_exact_same_fenced_plan(self) -> None:
        residual = _residual(expected=3, observed=4)
        need, plan = _retrieval_context(("m:a", 6_000, True), ("m:b", 9_000, True))
        binding = _binding(residual, need, plan)
        first = binding.evaluate(residual=residual, retrieval_need=need, retrieval_plan=plan)
        second = binding.evaluate(residual=residual, retrieval_need=need, retrieval_plan=plan)
        self.assertEqual(first.as_dict(), second.as_dict())
        self.assertEqual(first.sha256(), second.sha256())
        self.assertEqual(first.retrieval_memory_ids, ("m:a", "m:b"))
        self.assertEqual(first.familiarity_bp, 9_000)


if __name__ == "__main__":
    unittest.main()
