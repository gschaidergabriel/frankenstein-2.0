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
from frankenstein2.familiarity_prediction_binding import FamiliarityPredictionBinding
from frankenstein2.memory_lifecycle import create_memory
from frankenstein2.prediction_contract import PredictionContract


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class WP302G2PrebindingPlanScoreFalsifier(unittest.TestCase):
    def test_prebinding_self_inconsistent_plan_can_mint_forged_familiarity(self) -> None:
        need = RetrievalNeed.create(
            need_id="need:review-falsifier",
            axis_weights_bp={AXIS_GOAL: 10_000, AXIS_SEMANTIC: 10_000, AXIS_CAUSAL: 10_000},
            min_overlap_axes=2,
            limit=1,
            evidence_refs=("need:evidence",),
        )
        memory = create_memory(
            memory_id="memory:low-score",
            payload_ref="payload:low-score",
            payload_sha256=_sha("payload:low-score"),
            provenance_refs=("memory:evidence",),
        )
        low_score = 1_000
        candidate = RetrievalCandidate.create(
            memory=memory,
            signals=(
                RetrievalSignal.create(axis=AXIS_GOAL, score_bp=low_score, evidence_refs=("goal:evidence",)),
                RetrievalSignal.create(axis=AXIS_SEMANTIC, score_bp=low_score, evidence_refs=("semantic:evidence",)),
                RetrievalSignal.create(axis=AXIS_CAUSAL, score_bp=low_score, evidence_refs=("causal:evidence",)),
            ),
            candidate_evidence_refs=("candidate:evidence",),
        )
        canonical_plan = build_retrieval_plan(need, (candidate,))
        original = canonical_plan.selected[0]
        self.assertEqual(original.weighted_score_bp, low_score)
        self.assertEqual(dict(original.signal_scores_bp)[AXIS_GOAL], low_score)

        forged_score = 10_000
        forged_result = replace(
            original,
            weighted_score_bp=forged_score,
            rank_score=forged_score * original.overlap_count,
        )
        # Keep the original low signal_scores_bp and candidate_sha256. Only the derived
        # weighted/rank score is inflated, creating an internally inconsistent result.
        self.assertEqual(dict(forged_result.signal_scores_bp)[AXIS_GOAL], low_score)
        self.assertEqual(forged_result.weighted_score_bp, forged_score)

        forged_plan = RetrievalPlan(
            schema=PLAN_SCHEMA,
            need_id=canonical_plan.need_id,
            need_sha256=canonical_plan.need_sha256,
            selected=(forged_result,),
            not_selected=canonical_plan.not_selected,
            candidate_count=canonical_plan.candidate_count,
            classification=PLAN_CLASSIFICATION,
        )

        contract = PredictionContract.create(
            prediction_id="prediction:review-falsifier",
            target_id="agency:state",
            generation=2,
            basis_fingerprint_sha256=_sha("basis"),
            expected_projection={"value": 1},
        )
        residual = contract.observe(
            observation_id="observation:review-falsifier",
            observation_fingerprint_sha256=_sha("observation"),
            observed_projection={"value": 1},
        )

        # The G2 binding fences the digest of the already-forged plan. If provenance
        # closure is complete, evaluation must not accept a score that contradicts the
        # plan's own signal_scores_bp. Current G2 is expected to accept it; that acceptance
        # is the falsifier.
        binding = FamiliarityPredictionBinding.create(
            prediction_id=residual.prediction_id,
            generation=residual.generation,
            retrieval_need=need,
            retrieval_plan=forged_plan,
            expected_residual_sha256=residual.sha256(),
            evidence_refs=("binding:evidence",),
        )
        signal = binding.evaluate(
            residual=residual,
            retrieval_need=need,
            retrieval_plan=forged_plan,
        )

        self.assertEqual(signal.familiarity_bp, forged_score)
        self.assertEqual(signal.retrieval_plan_sha256, forged_plan.sha256())
        self.assertNotEqual(signal.familiarity_bp, low_score)


if __name__ == "__main__":
    unittest.main(verbosity=2)
