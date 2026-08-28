from __future__ import annotations

import unittest

from frankenstein2.wake_hold import (
    HOLD_CHECKPOINT_SCHEMA,
    OP_PRESENT,
    WAKE_ANY,
    WAKE_CONDITION_MATCH,
    WAKE_EVALUATION_SCHEMA,
    HoldCheckpoint,
    WakeCondition,
    WakeEvaluation,
    WakeHoldError,
)

DIGEST = "a" * 64


def forged_evaluation_kwargs(*, contradictory: bool = False) -> dict[str, object]:
    """Stay ABI-compatible with both the G2 and active G3 receipt shape."""
    kwargs: dict[str, object] = {
        "schema": WAKE_EVALUATION_SCHEMA,
        "evaluation_id": "contradictory-eval" if contradictory else "forged-eval",
        "hold_id": "hold-1",
        "checkpoint_sha256": DIGEST,
        "observed_state_id": "agency-1",
        "observed_generation": 7,
        "observed_state_sha256": DIGEST,
        "observation_ids": ("o1",),
        "matched_condition_ids": ("c1",),
        "unmatched_condition_ids": (),
        "unknown_condition_ids": ("c1",) if contradictory else (),
        "conflicting_condition_ids": (),
        "classification": WAKE_CONDITION_MATCH,
        "wake": True,
    }
    if "observations_sha256" in WakeEvaluation.__dataclass_fields__:
        kwargs["observations_sha256"] = DIGEST
    return kwargs


class WakeEvaluationReceiptConstructorFalsifier(unittest.TestCase):
    """REVIEW_ONLY falsifiers for the active F2-WP-205 generation-3 receipt boundary."""

    def test_direct_positive_wake_receipt_construction_must_fail_closed(self):
        """A caller must not mint a positive wake receipt without evaluate_wake fences."""
        with self.assertRaises(WakeHoldError):
            WakeEvaluation(**forged_evaluation_kwargs())

    def test_internally_contradictory_receipt_must_fail_closed(self):
        """The same condition cannot be simultaneously matched and unknown in one receipt."""
        with self.assertRaises(WakeHoldError):
            WakeEvaluation(**forged_evaluation_kwargs(contradictory=True))

    def test_hold_checkpoint_cannot_be_reclassified_as_scheduler_authority(self):
        condition = WakeCondition(
            condition_id="c1",
            observation_key="job.status",
            operator=OP_PRESENT,
            provenance_refs=("condition:explicit",),
            expected_value=None,
        )
        with self.assertRaises(WakeHoldError):
            HoldCheckpoint(
                schema=HOLD_CHECKPOINT_SCHEMA,
                hold_id="hold-1",
                state_id="agency-1",
                generation=7,
                state_sha256=DIGEST,
                wake_policy=WAKE_ANY,
                wake_conditions=(condition,),
                provenance_refs=("state:agency-1",),
                classification="SCHEDULER_AUTHORITY",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
