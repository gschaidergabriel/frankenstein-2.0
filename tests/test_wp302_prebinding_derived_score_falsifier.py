from __future__ import annotations

from dataclasses import replace
import hashlib
import unittest

from frankenstein2.emergent_retrieval import (
    AXIS_CAUSAL,
    AXIS_GOAL,
    AXIS_SEMANTIC,
    RetrievalCandidate,
    RetrievalNeed,
    RetrievalPlan,
    RetrievalSignal,
    build_retrieval_plan,
)
from frankenstein2.familiarity_prediction_binding import (
    FamiliarityPredictionBinding,
    FamiliarityPredictionBindingError,
)
from frankenstein2.memory_lifecycle import create_memory


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_context() -> tuple[RetrievalNeed, RetrievalPlan]:
    need = RetrievalNeed.create(
        need_id="need:wp302-prebinding-falsifier",
        axis_weights_bp={
            AXIS_GOAL: 10_000,
            AXIS_SEMANTIC: 10_000,
            AXIS_CAUSAL: 10_000,
        },
        min_overlap_axes=2,
        limit=4,
        evidence_refs=("need-evidence:wp302-prebinding-falsifier",),
    )
    memory = create_memory(
        memory_id="memory:low-signal",
        payload_ref="payload:memory:low-signal",
        payload_sha256=_sha("payload:memory:low-signal"),
        provenance_refs=("evidence:memory:low-signal",),
    )
    candidate = RetrievalCandidate.create(
        memory=memory,
        signals=(
            RetrievalSignal.create(
                axis=AXIS_GOAL,
                score_bp=1_000,
                evidence_refs=("signal:goal",),
            ),
            RetrievalSignal.create(
                axis=AXIS_SEMANTIC,
                score_bp=1_000,
                evidence_refs=("signal:semantic",),
            ),
            RetrievalSignal.create(
                axis=AXIS_CAUSAL,
                score_bp=1_000,
                evidence_refs=("signal:causal",),
            ),
        ),
        candidate_evidence_refs=("candidate:evidence",),
    )
    return need, build_retrieval_plan(need, (candidate,))


def _create_binding(need: RetrievalNeed, plan: RetrievalPlan) -> FamiliarityPredictionBinding:
    return FamiliarityPredictionBinding.create(
        prediction_id="prediction:wp302-prebinding-falsifier",
        generation=2,
        retrieval_need=need,
        retrieval_plan=plan,
        expected_residual_sha256=None,
        evidence_refs=("binding:evidence",),
    )


class WP302PrebindingDerivedScoreFalsifierTests(unittest.TestCase):
    def test_canonical_wp301_plan_remains_accepted(self) -> None:
        need, plan = _canonical_context()
        binding = _create_binding(need, plan)
        signal = binding.evaluate(
            residual=None,
            retrieval_need=need,
            retrieval_plan=plan,
        )
        self.assertEqual(signal.familiarity_bp, 1_000)

    def test_prebinding_weighted_score_forgery_is_rejected(self) -> None:
        need, plan = _canonical_context()
        original = plan.selected[0]
        forged = replace(
            original,
            weighted_score_bp=10_000,
            rank_score=10_000 * original.overlap_count,
        )
        forged_plan = replace(plan, selected=(forged,))

        with self.assertRaisesRegex(
            FamiliarityPredictionBindingError,
            "weighted_score_bp is not derived",
        ):
            _create_binding(need, forged_plan)

    def test_prebinding_bottleneck_score_forgery_is_rejected(self) -> None:
        need, plan = _canonical_context()
        original = plan.selected[0]
        forged = replace(original, bottleneck_score_bp=9_000)
        forged_plan = replace(plan, selected=(forged,))

        with self.assertRaisesRegex(
            FamiliarityPredictionBindingError,
            "bottleneck_score_bp is not derived",
        ):
            _create_binding(need, forged_plan)

    def test_prebinding_overlap_forgery_is_rejected(self) -> None:
        need, plan = _canonical_context()
        original = plan.selected[0]
        forged = replace(
            original,
            overlap_axes=(AXIS_CAUSAL, AXIS_GOAL),
            overlap_count=2,
            rank_score=original.weighted_score_bp * 2,
        )
        forged_plan = replace(plan, selected=(forged,))

        with self.assertRaisesRegex(
            FamiliarityPredictionBindingError,
            "overlap_axes is not derived",
        ):
            _create_binding(need, forged_plan)

    def test_signal_axis_reordering_is_rejected(self) -> None:
        need, plan = _canonical_context()
        original = plan.selected[0]
        forged = replace(
            original,
            signal_scores_bp=tuple(reversed(original.signal_scores_bp)),
        )
        forged_plan = replace(plan, selected=(forged,))

        with self.assertRaisesRegex(
            FamiliarityPredictionBindingError,
            "axes/order do not match",
        ):
            _create_binding(need, forged_plan)


if __name__ == "__main__":
    unittest.main()
