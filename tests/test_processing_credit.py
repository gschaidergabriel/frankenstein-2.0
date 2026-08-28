#!/usr/bin/env python3
"""Deterministic falsification suite for F2-WP-305 processing credit."""
from __future__ import annotations

import unittest

from frankenstein2.memory_lifecycle import create_memory
from frankenstein2.typed_memory import KIND_FACT, KIND_METHOD, KIND_PROCESS, create_typed_memory
from frankenstein2.processing_credit import (
    CLASS_IMPROVEMENT,
    CLASS_INSUFFICIENT,
    CLASS_REGRESSION,
    CLASS_TIE,
    DIRECTION_HIGHER_IS_BETTER,
    DIRECTION_LOWER_IS_BETTER,
    ROLE_BASELINE,
    ROLE_INTERVENTION,
    ProcessingCreditError,
    create_processing_outcome,
    evaluate_processing_credit,
)

PAYLOAD_SHA = "1" * 64


def typed_memory(kind: str, suffix: str):
    state = create_memory(
        memory_id=f"memory-{suffix}",
        payload_ref=f"payload/{suffix}.json",
        payload_sha256=PAYLOAD_SHA,
        provenance_refs=(f"source:{suffix}",),
    )
    if kind == KIND_METHOD:
        refs = {"method": (f"method:{suffix}",), "falsifier": (f"falsifier:{suffix}",)}
    elif kind == KIND_PROCESS:
        refs = {"process": (f"process:{suffix}",), "checkpoint": (f"checkpoint:{suffix}",)}
    else:
        refs = {"evidence": (f"evidence:{suffix}",)}
    return create_typed_memory(state=state, memory_kind=kind, refs=refs)


def outcome(
    role: str,
    value: int,
    *,
    pair_id: str = "pair-001",
    generation: int = 1,
    direction: str = DIRECTION_HIGHER_IS_BETTER,
    count: int = 3,
    kind: str = KIND_METHOD,
    metric_id: str = "quality-bp",
    metric_unit: str = "basis_points",
):
    suffix = "baseline" if role == ROLE_BASELINE else "intervention"
    return create_processing_outcome(
        typed_memory=typed_memory(kind, suffix),
        outcome_id=f"outcome-{suffix}",
        pair_id=pair_id,
        experiment_generation=generation,
        role=role,
        metric_id=metric_id,
        metric_unit=metric_unit,
        metric_direction=direction,
        metric_value=value,
        measurement_count=count,
        evidence_refs=(f"measurement:{suffix}",),
        provenance_refs=("suite:wp305", f"run:{suffix}"),
    )


class ProcessingCreditTests(unittest.TestCase):
    def test_higher_is_better_improvement_is_candidate_not_causal_proof(self):
        candidate = evaluate_processing_credit(outcome(ROLE_BASELINE, 7000), outcome(ROLE_INTERVENTION, 7600))
        self.assertEqual(candidate.oriented_delta, 600)
        self.assertEqual(candidate.classification, CLASS_IMPROVEMENT)
        self.assertTrue(candidate.credit_allowed)
        self.assertIn("NOT_WORLD_TRUTH", candidate.authority_boundary)
        self.assertNotIn("VERIFIED_COMPLETION", candidate.authority_boundary)

    def test_lower_is_better_direction_is_not_accidentally_reversed(self):
        candidate = evaluate_processing_credit(
            outcome(ROLE_BASELINE, 120, direction=DIRECTION_LOWER_IS_BETTER),
            outcome(ROLE_INTERVENTION, 90, direction=DIRECTION_LOWER_IS_BETTER),
        )
        self.assertEqual(candidate.oriented_delta, 30)
        self.assertEqual(candidate.classification, CLASS_IMPROVEMENT)
        self.assertTrue(candidate.credit_allowed)

    def test_regression_and_tie_do_not_receive_credit(self):
        regression = evaluate_processing_credit(outcome(ROLE_BASELINE, 100), outcome(ROLE_INTERVENTION, 90))
        self.assertEqual(regression.classification, CLASS_REGRESSION)
        self.assertFalse(regression.credit_allowed)
        tie = evaluate_processing_credit(outcome(ROLE_BASELINE, 100), outcome(ROLE_INTERVENTION, 100))
        self.assertEqual(tie.classification, CLASS_TIE)
        self.assertFalse(tie.credit_allowed)

    def test_explicit_minimum_measurements_yields_insufficient_not_credit(self):
        candidate = evaluate_processing_credit(
            outcome(ROLE_BASELINE, 100, count=1),
            outcome(ROLE_INTERVENTION, 150, count=2),
            min_measurements=3,
        )
        self.assertEqual(candidate.oriented_delta, 50)
        self.assertEqual(candidate.classification, CLASS_INSUFFICIENT)
        self.assertFalse(candidate.credit_allowed)
        self.assertEqual(candidate.required_min_measurements, 3)

    def test_pair_generation_and_metric_schema_are_exact_fences(self):
        cases = [
            (outcome(ROLE_BASELINE, 100, pair_id="pair-a"), outcome(ROLE_INTERVENTION, 110, pair_id="pair-b"), "pair_id"),
            (outcome(ROLE_BASELINE, 100, generation=1), outcome(ROLE_INTERVENTION, 110, generation=2), "experiment_generation"),
            (outcome(ROLE_BASELINE, 100, metric_id="latency"), outcome(ROLE_INTERVENTION, 110, metric_id="quality"), "metric_id"),
            (outcome(ROLE_BASELINE, 100, metric_unit="ms"), outcome(ROLE_INTERVENTION, 110, metric_unit="tokens"), "metric_unit"),
            (
                outcome(ROLE_BASELINE, 100, direction=DIRECTION_HIGHER_IS_BETTER),
                outcome(ROLE_INTERVENTION, 110, direction=DIRECTION_LOWER_IS_BETTER),
                "metric_direction",
            ),
        ]
        for baseline, intervention, expected in cases:
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(ProcessingCreditError, expected):
                    evaluate_processing_credit(baseline, intervention)

    def test_roles_are_not_inferred_or_swapped(self):
        with self.assertRaisesRegex(ProcessingCreditError, "BASELINE then INTERVENTION"):
            evaluate_processing_credit(outcome(ROLE_INTERVENTION, 100), outcome(ROLE_BASELINE, 110))

    def test_only_method_or_process_memory_can_back_processing_measurement(self):
        fact = typed_memory(KIND_FACT, "fact")
        with self.assertRaisesRegex(ProcessingCreditError, "METHOD or PROCESS"):
            create_processing_outcome(
                typed_memory=fact,
                outcome_id="outcome-fact",
                pair_id="pair-fact",
                experiment_generation=1,
                role=ROLE_BASELINE,
                metric_id="quality",
                metric_unit="points",
                metric_direction=DIRECTION_HIGHER_IS_BETTER,
                metric_value=1,
                measurement_count=1,
                evidence_refs=("measurement:fact",),
                provenance_refs=("suite:wp305",),
            )
        process = outcome(ROLE_BASELINE, 100, kind=KIND_PROCESS)
        self.assertEqual(process.memory_kind, KIND_PROCESS)

    def test_measurement_is_bound_to_exact_typed_memory_digest(self):
        memory = typed_memory(KIND_METHOD, "digest")
        result = create_processing_outcome(
            typed_memory=memory,
            outcome_id="outcome-digest",
            pair_id="pair-digest",
            experiment_generation=1,
            role=ROLE_BASELINE,
            metric_id="quality",
            metric_unit="points",
            metric_direction=DIRECTION_HIGHER_IS_BETTER,
            metric_value=5,
            measurement_count=1,
            evidence_refs=("measurement:digest",),
            provenance_refs=("suite:wp305",),
        )
        self.assertEqual(result.typed_memory_sha256, memory.sha256())
        self.assertEqual(result.memory_id, memory.memory_id)
        self.assertEqual(result.lifecycle_generation, memory.lifecycle_generation)

    def test_reference_order_is_canonical_but_duplicates_fail_closed(self):
        memory = typed_memory(KIND_METHOD, "refs")
        common = dict(
            typed_memory=memory,
            outcome_id="outcome-refs",
            pair_id="pair-refs",
            experiment_generation=1,
            role=ROLE_BASELINE,
            metric_id="quality",
            metric_unit="points",
            metric_direction=DIRECTION_HIGHER_IS_BETTER,
            metric_value=1,
            measurement_count=1,
        )
        left = create_processing_outcome(**common, evidence_refs=("e:z", "e:a"), provenance_refs=("p:z", "p:a"))
        right = create_processing_outcome(**common, evidence_refs=("e:a", "e:z"), provenance_refs=("p:a", "p:z"))
        self.assertEqual(left.canonical_json(), right.canonical_json())
        self.assertEqual(left.sha256(), right.sha256())
        with self.assertRaisesRegex(ProcessingCreditError, "duplicate references"):
            create_processing_outcome(**common, evidence_refs=("e:a", "e:a"), provenance_refs=("p:a",))

    def test_boolean_or_float_metrics_and_counts_are_rejected(self):
        memory = typed_memory(KIND_METHOD, "numeric")
        common = dict(
            typed_memory=memory,
            outcome_id="outcome-numeric",
            pair_id="pair-numeric",
            experiment_generation=1,
            role=ROLE_BASELINE,
            metric_id="quality",
            metric_unit="points",
            metric_direction=DIRECTION_HIGHER_IS_BETTER,
            evidence_refs=("e:numeric",),
            provenance_refs=("p:numeric",),
        )
        for value in (True, 1.5):
            with self.subTest(metric_value=value):
                with self.assertRaisesRegex(ProcessingCreditError, "metric_value"):
                    create_processing_outcome(**common, metric_value=value, measurement_count=1)
        with self.assertRaisesRegex(ProcessingCreditError, "measurement_count"):
            create_processing_outcome(**common, metric_value=1, measurement_count=True)


if __name__ == "__main__":
    unittest.main()
