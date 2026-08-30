#!/usr/bin/env python3
from __future__ import annotations

import unittest

from frankenstein2.target_chaos_coverage import (
    COVERAGE_CLASSIFICATION,
    TargetChaosCoverageError,
    compile_chaos_coverage_plan,
)
from frankenstein2.target_fault_scenarios import (
    DEVICE_EBUSY,
    DEVICE_REMOVE,
    LOW_SPACE,
    NETWORK_LOSS,
    NETWORK_RESET,
    PERMISSION_DENY,
    PERMISSION_REVOKE,
    PROCESS_KILL,
    READ_ONLY,
    REBOOT,
    FaultSpec,
)
from frankenstein2.target_hostile_chaos_matrix import (
    compile_hostile_chaos_case,
    compile_hostile_chaos_matrix,
)

PROFILE = "a" * 64

LEVELS = (
    (DEVICE_REMOVE, DEVICE_EBUSY),
    (PERMISSION_DENY, PERMISSION_REVOKE),
    (PROCESS_KILL, REBOOT),
    (NETWORK_LOSS, NETWORK_RESET),
    (LOW_SPACE, READ_ONLY),
)


def _params(action: str) -> dict:
    if action == NETWORK_LOSS:
        return {"loss_percent": 25}
    if action == LOW_SPACE:
        return {"remaining_bytes": 4096}
    return {}


def _case(name: str, bits: tuple[int, int, int, int, int], *, reverse_order: bool = False):
    chosen = [LEVELS[index][bit] for index, bit in enumerate(bits)]
    offsets = [0, 0, 10, 20, 30]
    indexed = list(enumerate(chosen))
    if reverse_order:
        indexed = list(reversed(indexed))
    specs = []
    for position, (family_index, action) in enumerate(indexed):
        specs.append(
            FaultSpec.create(
                action=action,
                target=f"fixture:{family_index}:{name}",
                offset_ms=offsets[position],
                parameters=_params(action),
            )
        )
    return compile_hostile_chaos_case(
        case_name=name,
        seed=100 + sum(bits) + (10 if reverse_order else 0),
        target_profile_digest=PROFILE,
        start_generation=7,
        specs=specs,
    )


def _matrix():
    patterns = (
        ((0, 0, 0, 0, 0), False),
        ((0, 0, 0, 0, 1), False),
        ((0, 0, 0, 1, 0), False),
        ((0, 0, 0, 1, 1), False),
        ((1, 1, 1, 0, 0), True),
        ((1, 0, 1, 1, 0), True),
        ((0, 1, 1, 0, 1), True),
        ((1, 1, 0, 1, 1), True),
    )
    cases = tuple(_case(f"case-{index}", bits, reverse_order=reverse) for index, (bits, reverse) in enumerate(patterns))
    return compile_hostile_chaos_matrix(matrix_name="coverage-fixture", cases=cases)


class TargetChaosCoverageTests(unittest.TestCase):
    def test_equal_budget_selection_improves_pairwise_and_sequence_coverage(self) -> None:
        plan = compile_chaos_coverage_plan(_matrix(), case_budget=4)
        self.assertEqual(plan.baseline.case_count, 4)
        self.assertEqual(plan.selected.case_count, 4)
        self.assertGreater(plan.pairwise_gain, 0)
        self.assertGreater(plan.ordered_gain, 0)
        self.assertGreater(plan.selected.pairwise_covered, plan.baseline.pairwise_covered)
        self.assertGreater(plan.selected.ordered_covered, plan.baseline.ordered_covered)

    def test_plan_is_deterministic_and_identity_bound(self) -> None:
        matrix = _matrix()
        first = compile_chaos_coverage_plan(matrix, case_budget=4)
        second = compile_chaos_coverage_plan(matrix, case_budget=4)
        self.assertEqual(first.as_dict(), second.as_dict())
        self.assertEqual(first.sha256(), second.sha256())
        self.assertTrue(first.plan_id.startswith("hostile-chaos-coverage:"))
        self.assertEqual(first.source_matrix_sha256, matrix.sha256())

    def test_mandatory_sentinel_is_never_optimized_away(self) -> None:
        matrix = _matrix()
        sentinel = matrix.cases[1].case_id
        plan = compile_chaos_coverage_plan(matrix, case_budget=3, mandatory_case_ids=(sentinel,))
        self.assertIn(sentinel, plan.selected_case_ids)
        self.assertEqual(len(plan.selected_case_ids), 3)

    def test_unknown_or_duplicate_mandatory_case_fails_closed(self) -> None:
        matrix = _matrix()
        with self.assertRaisesRegex(TargetChaosCoverageError, "unknown mandatory"):
            compile_chaos_coverage_plan(matrix, case_budget=3, mandatory_case_ids=("missing",))
        case_id = matrix.cases[0].case_id
        with self.assertRaisesRegex(TargetChaosCoverageError, "duplicates"):
            compile_chaos_coverage_plan(matrix, case_budget=3, mandatory_case_ids=(case_id, case_id))
        with self.assertRaisesRegex(TargetChaosCoverageError, "non-empty strings"):
            compile_chaos_coverage_plan(matrix, case_budget=3, mandatory_case_ids=(1,))

    def test_case_budget_is_exact_and_bounded(self) -> None:
        matrix = _matrix()
        with self.assertRaisesRegex(TargetChaosCoverageError, "case_budget"):
            compile_chaos_coverage_plan(matrix, case_budget=0)
        with self.assertRaisesRegex(TargetChaosCoverageError, "case_budget"):
            compile_chaos_coverage_plan(matrix, case_budget=len(matrix.cases) + 1)
        with self.assertRaisesRegex(TargetChaosCoverageError, "mandatory cases exceed"):
            compile_chaos_coverage_plan(matrix, case_budget=1, mandatory_case_ids=(matrix.cases[0].case_id, matrix.cases[1].case_id))

    def test_coverage_universe_is_candidate_pool_derived_not_a_safety_claim(self) -> None:
        plan = compile_chaos_coverage_plan(_matrix(), case_budget=4)
        self.assertGreater(plan.selected.pairwise_universe, 0)
        self.assertGreater(plan.selected.ordered_universe, 0)
        self.assertLessEqual(plan.selected.pairwise_covered, plan.selected.pairwise_universe)
        self.assertLessEqual(plan.selected.ordered_covered, plan.selected.ordered_universe)
        self.assertEqual(plan.classification, COVERAGE_CLASSIFICATION)

    def test_repository_coverage_plan_mints_no_runtime_or_completion_credit(self) -> None:
        plan = compile_chaos_coverage_plan(_matrix(), case_budget=4)
        self.assertFalse(plan.runtime_execution_observed)
        self.assertEqual(plan.target_runtime_credit, 0)
        self.assertEqual(plan.physical_host_credit, 0)
        self.assertEqual(plan.completion_credit, 0)
        self.assertFalse(plan.whole_system_acceptance)


if __name__ == "__main__":
    unittest.main()
