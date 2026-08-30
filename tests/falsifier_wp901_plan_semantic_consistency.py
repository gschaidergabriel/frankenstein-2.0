#!/usr/bin/env python3
"""Candidate falsifier for F2-WP-901 restart-plan semantic consistency.

REVIEW_ONLY / CANDIDATE_FALSIFIER.

The canonical planner currently emits internally coherent RestartContinuationPlan objects,
but the public dataclass constructor is also exported.  These tests require the constructor
to fail closed when disposition, reference sets and effect flags contradict each other.
No runtime/effect/completion authority is asserted by this file.
"""
from __future__ import annotations

import hashlib
import unittest

from frankenstein2.restart_recovery_continuation import (
    CONTINUE_UNFINISHED,
    NO_CONTINUATION,
    RestartContinuationPlan,
    RestartRecoveryError,
)


def sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def base_plan_fields() -> dict[str, object]:
    return {
        "plan_id": "falsifier-plan-10",
        "source_evidence_id": "recovery-evidence-9",
        "source_evidence_sha256": sha("recovery-evidence-9"),
        "source_checkpoint_id": "checkpoint-9",
        "source_checkpoint_generation": 9,
        "source_checkpoint_sha256": sha("checkpoint-9"),
        "whole_loop_seal_id": "whole-loop-seal-9",
        "whole_loop_seal_sha256": sha("whole-loop-seal-9"),
        "candidate_generation": 10,
        "reason_code": "CANDIDATE_FALSIFIER",
        "provenance_refs": ("receipt:wp900", "receipt:wp206"),
    }


class RestartPlanSemanticConsistencyFalsifier(unittest.TestCase):
    def test_continue_unfinished_cannot_claim_effect_verification_hold(self) -> None:
        fields = base_plan_fields()
        with self.assertRaises(RestartRecoveryError):
            RestartContinuationPlan(
                **fields,
                disposition=CONTINUE_UNFINISHED,
                continuation_refs=("work:alpha",),
                held_refs=("effect:send-1",),
                requires_effect_verification=True,
                requires_effect_reauthorization=False,
            )

    def test_no_continuation_cannot_carry_continuation_refs(self) -> None:
        fields = base_plan_fields()
        with self.assertRaises(RestartRecoveryError):
            RestartContinuationPlan(
                **fields,
                disposition=NO_CONTINUATION,
                continuation_refs=("work:alpha",),
                held_refs=(),
                requires_effect_verification=False,
                requires_effect_reauthorization=False,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
