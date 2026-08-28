from __future__ import annotations

import hashlib
import unittest

from frankenstein2.emergent_retrieval import (
    AXIS_CAUSAL,
    AXIS_GOAL,
    AXIS_SEMANTIC,
    CLASSIFICATION_SELECTED,
    PLAN_CLASSIFICATION,
    PLAN_SCHEMA,
    RESULT_SCHEMA,
    RetrievalCandidate,
    RetrievalNeed,
    RetrievalPlan,
    RetrievalResult,
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
from frankenstein2.memory_lifecycle import STATUS_ACTIVE, create_memory
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


def _candidate(memory_id: str, score: int, *, weak: bool = False) -> RetrievalCandidate:
    memory = create_memory(
        memory_id=memory_id,
        payload_ref=f"payload:{memory_id}",
        payload_sha256=_sha(f"payload:{memory_id}"),
        provenance_refs=(f"evidence:{memory_id}",),
    )
    signals = (
        RetrievalSignal.create(
            axis=AXIS_GOAL,
            score_bp=score,
            evidence_refs=(f"goal:{memory_id}",),
        ),
        RetrievalSignal.create(
            axis=AXIS_SEMANTIC,
            score_bp=0 if weak else score,
            evidence_refs=(f"semantic:{memory_id}",),
        ),
        RetrievalSignal.create(
            axis=AXIS_CAUSAL,
            score_bp=0 if weak else score,
            evidence_refs=(f"causal:{memory_id}",),
        ),
    )
    return RetrievalCandidate.create(
        memory=memory,
        signals=signals,
        candidate_evidence_refs=(f"candidate:{memory_id}",),
    )


def _need() -> RetrievalNeed:
    return RetrievalNeed.create(
        need_id="need:familiarity",
        axis_weights_bp={
            AXIS_GOAL: 10_000,
            AXIS_SEMANTIC: 10_000,
            AXIS_CAUSAL: 10_000,
        },
        min_overlap_axes=2,
        limit=4,
        evidence_refs=("need-evidence:familiarity",),
    )


def _plan(*entries: tuple[str, int, bool]) -> RetrievalPlan:
    need = _need()
    candidates = tuple(
        _candidate(memory_id, score, weak=weak)
        for memory_id, score, weak in entries
    )
    return build_retrieval_plan(need, candidates)


def _binding(residual, plan: RetrievalPlan | None, *, residual_fence: bool = True):
    return FamiliarityPredictionBinding.create(
        prediction_id=residual.prediction_id if residual is not None else "prediction:pending",
        generation=residual.generation if residual is not None else 4,
        expected_residual_sha256=(residual.sha256() if residual is not None and residual_fence else None),
        expected_retrieval_plan_sha256=plan.sha256() if plan is not None else None,
        expected_retrieval_need_id=plan.need_id if plan is not None else None,
        expected_retrieval_need_sha256=plan.need_sha256 if plan is not None else None,
        evidence_refs=("binding:evidence",),
    )


class FamiliarityPredictionBindingTests(unittest.TestCase):
    def test_exact_residual_match_stays_match_and_binds_plan_identity(self) -> None:
        residual = _residual(expected=7, observed=7)
        plan = _plan(("m:known", 8_000, False))
        signal = _binding(residual, plan).evaluate(residual=residual, retrieval_plan=plan)

        self.assertEqual(signal.status, STATUS_MATCH)
        self.assertEqual(signal.residual_sha256, residual.sha256())
        self.assertEqual(signal.observation_id, residual.observation_id)
        self.assertEqual(signal.observation_fingerprint_sha256, residual.observation_fingerprint_sha256)
        self.assertEqual(signal.prediction_error_bp, 0)
        self.assertEqual(signal.familiarity_bp, 8_000)
        self.assertEqual(signal.attention_priority_bp, 8_000)
        self.assertEqual(signal.retrieval_plan_sha256, plan.sha256())
        self.assertEqual(signal.retrieval_need_id, plan.need_id)
        self.assertEqual(signal.retrieval_need_sha256, plan.need_sha256)
        self.assertEqual(signal.classification, CLASSIFICATION)

    def test_high_familiarity_cannot_suppress_current_mismatch(self) -> None:
        residual = _residual(expected=1, observed=2)
        plan = _plan(("m:familiar", 10_000, False))
        signal = _binding(residual, plan).evaluate(residual=residual, retrieval_plan=plan)

        self.assertEqual(signal.status, STATUS_MISMATCH)
        self.assertEqual(signal.prediction_error_bp, 10_000)
        self.assertEqual(signal.familiarity_bp, 10_000)
        self.assertEqual(signal.attention_priority_bp, 10_000)

    def test_no_current_residual_is_unknown_even_with_strong_bound_plan(self) -> None:
        plan = _plan(("m:prior", 9_000, False))
        binding = _binding(None, plan)
        signal = binding.evaluate(residual=None, retrieval_plan=plan)

        self.assertEqual(signal.status, STATUS_UNKNOWN)
        self.assertIsNone(signal.residual_sha256)
        self.assertIsNone(signal.observation_id)
        self.assertIsNone(signal.prediction_error_bp)
        self.assertEqual(signal.familiarity_bp, 9_000)
        self.assertEqual(signal.attention_priority_bp, 9_000)
        self.assertEqual(signal.retrieval_plan_sha256, plan.sha256())

    def test_missing_residual_fails_closed_when_digest_was_expected(self) -> None:
        residual = _residual()
        binding = _binding(residual, None)
        with self.assertRaisesRegex(FamiliarityPredictionBindingError, "residual is unavailable"):
            binding.evaluate(residual=None)

    def test_present_residual_requires_explicit_digest_fence(self) -> None:
        residual = _residual()
        binding = _binding(residual, None, residual_fence=False)
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

    def test_present_plan_requires_explicit_plan_and_need_fences(self) -> None:
        plan = _plan(("m:known", 7_000, False))
        binding = _binding(None, None)
        with self.assertRaisesRegex(FamiliarityPredictionBindingError, "requires explicit plan and need identity fences"):
            binding.evaluate(residual=None, retrieval_plan=plan)

    def test_missing_plan_fails_closed_when_plan_was_expected(self) -> None:
        plan = _plan(("m:known", 7_000, False))
        binding = _binding(None, plan)
        with self.assertRaisesRegex(FamiliarityPredictionBindingError, "retrieval_plan is unavailable"):
            binding.evaluate(residual=None, retrieval_plan=None)

    def test_plan_digest_and_need_identity_mismatch_fail_closed(self) -> None:
        plan = _plan(("m:known", 7_000, False))
        wrong_digest = FamiliarityPredictionBinding.create(
            prediction_id="prediction:pending",
            generation=4,
            expected_residual_sha256=None,
            expected_retrieval_plan_sha256=_sha("wrong-plan"),
            expected_retrieval_need_id=plan.need_id,
            expected_retrieval_need_sha256=plan.need_sha256,
            evidence_refs=("binding:plan-digest",),
        )
        with self.assertRaisesRegex(FamiliarityPredictionBindingError, "plan digest fence mismatch"):
            wrong_digest.evaluate(residual=None, retrieval_plan=plan)

        wrong_need = FamiliarityPredictionBinding.create(
            prediction_id="prediction:pending",
            generation=4,
            expected_residual_sha256=None,
            expected_retrieval_plan_sha256=plan.sha256(),
            expected_retrieval_need_id="need:other",
            expected_retrieval_need_sha256=plan.need_sha256,
            evidence_refs=("binding:need-id",),
        )
        with self.assertRaisesRegex(FamiliarityPredictionBindingError, "need_id fence mismatch"):
            wrong_need.evaluate(residual=None, retrieval_plan=plan)

    def test_direct_forged_selected_result_inside_self_hashed_plan_fails_closed(self) -> None:
        forged = RetrievalResult(
            schema=RESULT_SCHEMA,
            memory_id="m:forged",
            memory_generation=0,
            memory_state_sha256=_sha("memory"),
            lifecycle_status=STATUS_ACTIVE,
            selected=True,
            classification=CLASSIFICATION_SELECTED,
            payload_ref="payload:forged",
            payload_sha256=_sha("payload"),
            provenance_refs=("provenance:forged",),
            successor_ref=None,
            overlap_axes=(),
            overlap_count=0,
            weighted_score_bp=10_000,
            bottleneck_score_bp=10_000,
            rank_score=10_000,
            signal_scores_bp=(),
            signal_evidence_refs=(),
            candidate_sha256=_sha("candidate"),
        )
        fake_plan = RetrievalPlan(
            schema=PLAN_SCHEMA,
            need_id="need:forged",
            need_sha256=_sha("need:forged"),
            selected=(forged,),
            not_selected=(),
            candidate_count=1,
            classification=PLAN_CLASSIFICATION,
        )
        binding = FamiliarityPredictionBinding.create(
            prediction_id="prediction:pending",
            generation=4,
            expected_residual_sha256=None,
            expected_retrieval_plan_sha256=fake_plan.sha256(),
            expected_retrieval_need_id=fake_plan.need_id,
            expected_retrieval_need_sha256=fake_plan.need_sha256,
            evidence_refs=("binding:forged-plan",),
        )
        with self.assertRaisesRegex(FamiliarityPredictionBindingError, "requires positive overlap"):
            binding.evaluate(residual=None, retrieval_plan=fake_plan)

    def test_free_floating_retrieval_result_api_is_not_supported(self) -> None:
        plan = _plan(("m:known", 7_000, False))
        result = plan.selected[0]
        binding = _binding(None, plan)
        with self.assertRaises(TypeError):
            binding.evaluate(residual=None, retrieval_results=(result,))  # type: ignore[call-arg]

    def test_weak_unselected_memory_does_not_contribute_familiarity(self) -> None:
        plan = _plan(("m:weak", 9_000, True))
        self.assertEqual(plan.selected, ())
        signal = _binding(None, plan).evaluate(residual=None, retrieval_plan=plan)
        self.assertEqual(signal.familiarity_bp, 0)
        self.assertEqual(signal.retrieval_memory_ids, ())

    def test_result_is_deterministic_across_candidate_input_order(self) -> None:
        need_a = _need()
        need_b = _need()
        a = _candidate("m:a", 6_000)
        b = _candidate("m:b", 9_000)
        forward_plan = build_retrieval_plan(need_a, (a, b))
        reverse_plan = build_retrieval_plan(need_b, (b, a))
        self.assertEqual(forward_plan.sha256(), reverse_plan.sha256())

        residual = _residual(expected=3, observed=4)
        forward = _binding(residual, forward_plan).evaluate(
            residual=residual,
            retrieval_plan=forward_plan,
        )
        reverse = _binding(residual, reverse_plan).evaluate(
            residual=residual,
            retrieval_plan=reverse_plan,
        )
        self.assertEqual(forward.as_dict(), reverse.as_dict())
        self.assertEqual(forward.sha256(), reverse.sha256())
        self.assertEqual(forward.retrieval_memory_ids, ("m:a", "m:b"))
        self.assertEqual(forward.familiarity_bp, 9_000)


if __name__ == "__main__":
    unittest.main()
