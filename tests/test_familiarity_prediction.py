from __future__ import annotations

import hashlib
import unittest

from frankenstein2.emergent_retrieval import (
    AXIS_CAUSAL,
    AXIS_GOAL,
    AXIS_SEMANTIC,
    CLASSIFICATION_SELECTED,
    PLAN_SCHEMA,
    RESULT_SCHEMA,
    RetrievalCandidate,
    RetrievalNeed,
    RetrievalPlan,
    RetrievalResult,
    RetrievalSignal,
    build_retrieval_plan,
)
from frankenstein2.familiarity_prediction import (
    FAMILIARITY_CLASSIFICATION,
    FAMILIARITY_EVIDENCE_SCHEMA,
    MAX_BASIS_POINTS,
    RELATION_MATCH,
    RELATION_MISMATCH,
    RELATION_UNKNOWN,
    SIGNAL_CLASSIFICATION,
    FamiliarityEvidence,
    FamiliarityPredictionError,
    bind_familiarity_to_prediction_residual,
)
from frankenstein2.memory_lifecycle import STATUS_ACTIVE, create_memory
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


def _need(*, need_id: str = "need:familiarity") -> RetrievalNeed:
    return RetrievalNeed.create(
        need_id=need_id,
        axis_weights_bp={
            AXIS_GOAL: 10_000,
            AXIS_SEMANTIC: 10_000,
            AXIS_CAUSAL: 10_000,
        },
        min_overlap_axes=2,
        limit=4,
        evidence_refs=(f"need-evidence:{need_id}",),
    )


def _plan(score: int = 7000, *, need: RetrievalNeed | None = None) -> tuple[RetrievalNeed, RetrievalPlan]:
    need = need or _need()
    memory = create_memory(
        memory_id="memory:7",
        payload_ref="payload:memory:7",
        payload_sha256=_sha("payload:memory:7"),
        provenance_refs=("memory:7:provenance",),
    )
    candidate = RetrievalCandidate.create(
        memory=memory,
        signals=(
            RetrievalSignal.create(
                axis=AXIS_GOAL,
                score_bp=score,
                evidence_refs=("retrieval:goal",),
            ),
            RetrievalSignal.create(
                axis=AXIS_SEMANTIC,
                score_bp=score,
                evidence_refs=("retrieval:semantic",),
            ),
            RetrievalSignal.create(
                axis=AXIS_CAUSAL,
                score_bp=score,
                evidence_refs=("retrieval:causal",),
            ),
        ),
        candidate_evidence_refs=("candidate:memory:7",),
    )
    return need, build_retrieval_plan(need, (candidate,))


def _familiarity(score: int = 7000) -> FamiliarityEvidence:
    need, plan = _plan(score)
    return FamiliarityEvidence.from_retrieval_plan(
        need=need,
        plan=plan,
        expected_plan_sha256=plan.sha256(),
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
    def test_exact_residual_with_plan_bound_familiarity_emits_match_candidate(self) -> None:
        residual = _residual(mismatch=False)
        familiarity = _familiarity(7000)
        signal = _bind(residual, familiarity)

        self.assertEqual(signal.relation, RELATION_MATCH)
        self.assertTrue(signal.residual_exact_match)
        self.assertEqual(signal.residual_mismatch_count, 0)
        self.assertEqual(signal.attention_priority_bp, 7000)
        self.assertEqual(signal.classification, SIGNAL_CLASSIFICATION)
        self.assertEqual(signal.retrieval_plan_sha256, familiarity.retrieval_plan_sha256)
        self.assertEqual(signal.retrieval_need_sha256, familiarity.retrieval_need_sha256)
        self.assertEqual(signal.retrieval_memory_ids, ("memory:7",))

    def test_exact_residual_without_selected_retrieval_support_is_unknown(self) -> None:
        residual = _residual(mismatch=False)
        familiarity = _familiarity(0)
        signal = _bind(residual, familiarity, contradiction=())

        self.assertEqual(signal.relation, RELATION_UNKNOWN)
        self.assertTrue(signal.residual_exact_match)
        self.assertEqual(signal.attention_priority_bp, 0)
        self.assertEqual(signal.retrieval_memory_ids, ())
        self.assertEqual(signal.retrieval_result_sha256s, ())

    def test_mismatch_cannot_be_suppressed_by_high_familiarity(self) -> None:
        residual = _residual(mismatch=True)
        signal = _bind(residual, _familiarity(MAX_BASIS_POINTS))

        self.assertEqual(signal.relation, RELATION_MISMATCH)
        self.assertFalse(signal.residual_exact_match)
        self.assertGreater(signal.residual_mismatch_count, 0)
        self.assertEqual(signal.attention_priority_bp, MAX_BASIS_POINTS)
        self.assertEqual(signal.contradiction_evidence_refs, ("observation:contradiction",))

    def test_mismatch_requires_explicit_contradiction_evidence(self) -> None:
        residual = _residual(mismatch=True)
        with self.assertRaisesRegex(
            FamiliarityPredictionError, "requires explicit contradiction evidence"
        ):
            _bind(residual, contradiction=())

    def test_prediction_identity_generation_and_residual_digest_fences_fail_closed(self) -> None:
        residual = _residual(mismatch=False)
        familiarity = _familiarity()
        with self.assertRaisesRegex(FamiliarityPredictionError, "prediction_id fence mismatch"):
            bind_familiarity_to_prediction_residual(
                residual=residual,
                expected_prediction_id="prediction:other",
                expected_generation=residual.generation,
                expected_residual_sha256=residual.sha256(),
                familiarity=familiarity,
            )
        with self.assertRaisesRegex(FamiliarityPredictionError, "generation fence mismatch"):
            bind_familiarity_to_prediction_residual(
                residual=residual,
                expected_prediction_id=residual.prediction_id,
                expected_generation=residual.generation + 1,
                expected_residual_sha256=residual.sha256(),
                familiarity=familiarity,
            )
        with self.assertRaisesRegex(FamiliarityPredictionError, "residual digest fence mismatch"):
            bind_familiarity_to_prediction_residual(
                residual=residual,
                expected_prediction_id=residual.prediction_id,
                expected_generation=residual.generation,
                expected_residual_sha256="0" * 64,
                familiarity=familiarity,
            )

    def test_familiarity_cannot_be_created_from_free_score(self) -> None:
        with self.assertRaisesRegex(
            FamiliarityPredictionError, "must be derived through from_retrieval_plan"
        ):
            FamiliarityEvidence(
                schema=FAMILIARITY_EVIDENCE_SCHEMA,
                retrieval_need_id="need:forged",
                retrieval_need_sha256=_sha("need"),
                retrieval_plan_sha256=_sha("plan"),
                familiarity_score_bp=MAX_BASIS_POINTS,
                retrieval_memory_ids=("memory:forged",),
                retrieval_result_sha256s=(_sha("result"),),
                evidence_refs=("forged:evidence",),
                classification=FAMILIARITY_CLASSIFICATION,
            )

    def test_retrieval_plan_digest_fence_fails_closed(self) -> None:
        need, plan = _plan(8000)
        with self.assertRaisesRegex(FamiliarityPredictionError, "plan digest fence mismatch"):
            FamiliarityEvidence.from_retrieval_plan(
                need=need,
                plan=plan,
                expected_plan_sha256="0" * 64,
            )

    def test_retrieval_need_identity_and_digest_are_bound(self) -> None:
        need, plan = _plan(8000)
        other_need = _need(need_id="need:other")
        with self.assertRaisesRegex(FamiliarityPredictionError, "need_id fence mismatch"):
            FamiliarityEvidence.from_retrieval_plan(
                need=other_need,
                plan=plan,
                expected_plan_sha256=plan.sha256(),
            )
        self.assertNotEqual(need.sha256(), other_need.sha256())

    def test_forged_selected_retrieval_result_from_recorded_falsifier_fails_closed(self) -> None:
        """Reproduce the mainline WP302 unbound RetrievalResult counterexample."""
        need = _need()
        forged = RetrievalResult(
            schema=RESULT_SCHEMA,
            memory_id="memory:forged",
            memory_generation=0,
            memory_state_sha256=_sha("state:forged"),
            lifecycle_status=STATUS_ACTIVE,
            selected=True,
            classification=CLASSIFICATION_SELECTED,
            payload_ref="payload:forged",
            payload_sha256=_sha("payload:forged"),
            provenance_refs=("provenance:forged",),
            successor_ref=None,
            overlap_axes=(),
            overlap_count=0,
            weighted_score_bp=MAX_BASIS_POINTS,
            bottleneck_score_bp=MAX_BASIS_POINTS,
            rank_score=0,
            signal_scores_bp=(
                (AXIS_CAUSAL, MAX_BASIS_POINTS),
                (AXIS_GOAL, MAX_BASIS_POINTS),
                (AXIS_SEMANTIC, MAX_BASIS_POINTS),
            ),
            signal_evidence_refs=(
                (AXIS_CAUSAL, ("forged:causal",)),
                (AXIS_GOAL, ("forged:goal",)),
                (AXIS_SEMANTIC, ("forged:semantic",)),
            ),
            candidate_sha256=_sha("candidate:forged"),
        )
        forged_plan = RetrievalPlan(
            schema=PLAN_SCHEMA,
            need_id=need.need_id,
            need_sha256=need.sha256(),
            selected=(forged,),
            not_selected=(),
            candidate_count=1,
        )

        with self.assertRaisesRegex(FamiliarityPredictionError, "overlap"):
            FamiliarityEvidence.from_retrieval_plan(
                need=need,
                plan=forged_plan,
                expected_plan_sha256=forged_plan.sha256(),
            )

    def test_forged_weighted_score_inside_plan_fails_closed(self) -> None:
        need, plan = _plan(6000)
        legitimate = plan.selected[0]
        forged = RetrievalResult(
            **{
                **legitimate.as_dict(),
                "weighted_score_bp": 9999,
                "rank_score": 9999 * legitimate.overlap_count,
            }
        )
        forged_plan = RetrievalPlan(
            schema=PLAN_SCHEMA,
            need_id=plan.need_id,
            need_sha256=plan.need_sha256,
            selected=(forged,),
            not_selected=plan.not_selected,
            candidate_count=plan.candidate_count,
        )
        with self.assertRaisesRegex(FamiliarityPredictionError, "weighted_score_bp"):
            FamiliarityEvidence.from_retrieval_plan(
                need=need,
                plan=forged_plan,
                expected_plan_sha256=forged_plan.sha256(),
            )

    def test_signal_preserves_exact_residual_and_retrieval_provenance(self) -> None:
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
        self.assertEqual(signal.retrieval_need_id, familiarity.retrieval_need_id)
        self.assertEqual(signal.retrieval_need_sha256, familiarity.retrieval_need_sha256)
        self.assertEqual(signal.retrieval_plan_sha256, familiarity.retrieval_plan_sha256)
        self.assertEqual(signal.familiarity_evidence_refs, familiarity.evidence_refs)
        self.assertEqual(
            signal.contradiction_evidence_refs,
            ("observation:a", "observation:z"),
        )

    def test_retrieval_bound_familiarity_is_deterministic(self) -> None:
        need = _need()
        memory_a = create_memory(
            memory_id="memory:a",
            payload_ref="payload:a",
            payload_sha256=_sha("payload:a"),
            provenance_refs=("provenance:a",),
        )
        memory_b = create_memory(
            memory_id="memory:b",
            payload_ref="payload:b",
            payload_sha256=_sha("payload:b"),
            provenance_refs=("provenance:b",),
        )

        def candidate(memory, score):
            return RetrievalCandidate.create(
                memory=memory,
                signals=(
                    RetrievalSignal.create(axis=AXIS_GOAL, score_bp=score, evidence_refs=(f"goal:{memory.memory_id}",)),
                    RetrievalSignal.create(axis=AXIS_SEMANTIC, score_bp=score, evidence_refs=(f"semantic:{memory.memory_id}",)),
                    RetrievalSignal.create(axis=AXIS_CAUSAL, score_bp=score, evidence_refs=(f"causal:{memory.memory_id}",)),
                ),
                candidate_evidence_refs=(f"candidate:{memory.memory_id}",),
            )

        a = candidate(memory_a, 6100)
        b = candidate(memory_b, 8100)
        forward_plan = build_retrieval_plan(need, (a, b))
        reverse_plan = build_retrieval_plan(need, (b, a))
        self.assertEqual(forward_plan.sha256(), reverse_plan.sha256())

        first = FamiliarityEvidence.from_retrieval_plan(
            need=need,
            plan=forward_plan,
            expected_plan_sha256=forward_plan.sha256(),
        )
        second = FamiliarityEvidence.from_retrieval_plan(
            need=need,
            plan=reverse_plan,
            expected_plan_sha256=reverse_plan.sha256(),
        )
        self.assertEqual(first.as_dict(), second.as_dict())
        self.assertEqual(first.sha256(), second.sha256())
        self.assertEqual(first.familiarity_score_bp, 8100)


if __name__ == "__main__":
    unittest.main()
