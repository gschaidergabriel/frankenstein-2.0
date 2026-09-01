from __future__ import annotations

import hashlib
import unittest

from frankenstein2.cognitive_transfer_recovery_benchmark import (
    COLD_RESTART,
    EvaluatorRunMeasurement,
    TransferCase,
)


def h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def case() -> TransferCase:
    return TransferCase.create(
        source_fixture_id="train.source.001",
        source_fixture_generation=1,
        source_holdout_set_id="source-family-v1",
        source_public_fixture_sha256=h("source-public-fixture"),
        target_fixture_id="heldout.target.001",
        target_fixture_generation=3,
        target_holdout_set_id="target-family-v1",
        target_public_fixture_sha256=h("target-public-fixture"),
        episode_family_id="transfer-family-1",
        action_budget=8,
    )


class WP805MeasurementProvenanceFalsifier(unittest.TestCase):
    def test_same_declared_run_identity_accepts_conflicting_caller_supplied_measurements(self):
        """Reproduce that WP805 measurement values are not bound to an evaluator execution trace."""
        c = case()
        fixed = dict(
            run_id="same-declared-run",
            mode=COLD_RESTART,
            case=c,
            target_fixture_sha256=h("same-target-hidden-fixture"),
            checkpoint=None,
        )

        first = EvaluatorRunMeasurement.measure_run(
            **fixed,
            actions_executed=7,
            replayed_steps=2,
            repeated_work_steps=3,
            final_evaluator_score=9,
            terminal=True,
        )
        contradictory = EvaluatorRunMeasurement.measure_run(
            **fixed,
            actions_executed=1,
            replayed_steps=0,
            repeated_work_steps=0,
            final_evaluator_score=999,
            terminal=False,
        )

        # The exact declared run/case/target identity is unchanged, yet mutually
        # incompatible measurement claims are both accepted. This is expected to
        # PASS while the provenance gap exists; it is a reproducer, not a repair.
        self.assertEqual(first.run_id, contradictory.run_id)
        self.assertEqual(first.transfer_case_sha256, contradictory.transfer_case_sha256)
        self.assertEqual(first.target_fixture_sha256, contradictory.target_fixture_sha256)
        self.assertNotEqual(first.actions_executed, contradictory.actions_executed)
        self.assertNotEqual(first.final_evaluator_score, contradictory.final_evaluator_score)
        self.assertNotEqual(first.terminal, contradictory.terminal)
        self.assertNotEqual(first.sha256(), contradictory.sha256())


if __name__ == "__main__":
    unittest.main()
