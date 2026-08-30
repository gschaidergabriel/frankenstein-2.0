#!/usr/bin/env python3
"""Executable falsifier/regression for F2-WP-901 generation 2.

The generation-1 planner emitted coherent plans but the exported plan dataclass accepted
directly constructed semantic contradictions. Generation 2 requires those contradictions
to fail closed at the object boundary itself.
"""
from __future__ import annotations

import hashlib
import unittest

from frankenstein2.restart_recovery_continuation import (
    CONTINUE_UNFINISHED,
    CONTINUE_WITH_EFFECT_REAUTH_HOLD,
    HOLD_EFFECT_VERIFICATION,
    NO_CONTINUATION,
    RestartContinuationPlan,
    RestartRecoveryError,
)


def sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def fields() -> dict[str, object]:
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
        "reason_code": "G2_SEMANTIC_CONSISTENCY",
        "provenance_refs": ("receipt:wp900", "receipt:wp206"),
    }


class RestartPlanSemanticConsistencyTests(unittest.TestCase):
    def test_continue_unfinished_rejects_verification_hold_contradiction(self) -> None:
        with self.assertRaises(RestartRecoveryError):
            RestartContinuationPlan(
                **fields(),
                disposition=CONTINUE_UNFINISHED,
                continuation_refs=("work:alpha",),
                held_refs=("effect:send-1",),
                requires_effect_verification=True,
                requires_effect_reauthorization=False,
            )

    def test_continue_unfinished_requires_actual_continuation(self) -> None:
        with self.assertRaises(RestartRecoveryError):
            RestartContinuationPlan(
                **fields(),
                disposition=CONTINUE_UNFINISHED,
                continuation_refs=(),
                held_refs=(),
                requires_effect_verification=False,
                requires_effect_reauthorization=False,
            )

    def test_no_continuation_rejects_refs(self) -> None:
        with self.assertRaises(RestartRecoveryError):
            RestartContinuationPlan(
                **fields(),
                disposition=NO_CONTINUATION,
                continuation_refs=("work:alpha",),
                held_refs=(),
                requires_effect_verification=False,
                requires_effect_reauthorization=False,
            )

    def test_verification_hold_requires_held_refs_and_exclusive_flag(self) -> None:
        with self.assertRaises(RestartRecoveryError):
            RestartContinuationPlan(
                **fields(),
                disposition=HOLD_EFFECT_VERIFICATION,
                continuation_refs=(),
                held_refs=(),
                requires_effect_verification=True,
                requires_effect_reauthorization=False,
            )
        with self.assertRaises(RestartRecoveryError):
            RestartContinuationPlan(
                **fields(),
                disposition=HOLD_EFFECT_VERIFICATION,
                continuation_refs=(),
                held_refs=("effect:send-1",),
                requires_effect_verification=True,
                requires_effect_reauthorization=True,
            )

    def test_reauth_hold_requires_held_refs_and_reauth_only(self) -> None:
        with self.assertRaises(RestartRecoveryError):
            RestartContinuationPlan(
                **fields(),
                disposition=CONTINUE_WITH_EFFECT_REAUTH_HOLD,
                continuation_refs=(),
                held_refs=(),
                requires_effect_verification=False,
                requires_effect_reauthorization=True,
            )
        with self.assertRaises(RestartRecoveryError):
            RestartContinuationPlan(
                **fields(),
                disposition=CONTINUE_WITH_EFFECT_REAUTH_HOLD,
                continuation_refs=("work:alpha",),
                held_refs=("effect:send-1",),
                requires_effect_verification=True,
                requires_effect_reauthorization=True,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
