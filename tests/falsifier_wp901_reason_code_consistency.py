#!/usr/bin/env python3
"""Regression closure for the executable WP901 G2 reason-code falsifier.

The review witness proved that the generation-1 constructor accepted cross-paired
``disposition`` / ``reason_code`` values. Generation 2 must reject the same four
counterexamples while retaining its explicit causal-lineage field.
"""
from __future__ import annotations

import unittest

from frankenstein2.restart_recovery_continuation import (
    CONTINUE_UNFINISHED,
    CONTINUE_WITH_EFFECT_REAUTH_HOLD,
    HOLD_EFFECT_VERIFICATION,
    NO_CONTINUATION,
    RestartContinuationPlan,
    RestartRecoveryError,
)


SHA = "a" * 64
REASON_CONTINUE = "EXPLICIT_UNFINISHED_EVIDENCE"
REASON_NONE = "NO_EXPLICIT_UNFINISHED_WORK"


class ReasonCodeConsistencyRegression(unittest.TestCase):
    def _base(self) -> dict[str, object]:
        return {
            "plan_id": "reason-regression-plan",
            "source_evidence_id": "evidence-1",
            "source_evidence_sha256": SHA,
            "causal_lineage_id": "episode-1",
            "source_checkpoint_id": "checkpoint-1",
            "source_checkpoint_generation": 1,
            "source_checkpoint_sha256": SHA,
            "whole_loop_seal_id": "loop-1",
            "whole_loop_seal_sha256": SHA,
            "candidate_generation": 2,
            "provenance_refs": ("review:reason-code-falsifier",),
        }

    def _must_reject(self, **fields: object) -> None:
        values = self._base()
        values.update(fields)
        with self.assertRaises(RestartRecoveryError):
            RestartContinuationPlan(**values)

    def test_no_continuation_rejects_continue_reason(self) -> None:
        self._must_reject(
            disposition=NO_CONTINUATION,
            reason_code=REASON_CONTINUE,
            continuation_refs=(),
            held_refs=(),
            requires_effect_verification=False,
            requires_effect_reauthorization=False,
        )

    def test_continue_rejects_no_work_reason(self) -> None:
        self._must_reject(
            disposition=CONTINUE_UNFINISHED,
            reason_code=REASON_NONE,
            continuation_refs=("work:1",),
            held_refs=(),
            requires_effect_verification=False,
            requires_effect_reauthorization=False,
        )

    def test_verification_hold_rejects_no_work_reason(self) -> None:
        self._must_reject(
            disposition=HOLD_EFFECT_VERIFICATION,
            reason_code=REASON_NONE,
            continuation_refs=(),
            held_refs=("effect:1",),
            requires_effect_verification=True,
            requires_effect_reauthorization=False,
        )

    def test_reauth_hold_rejects_no_work_reason(self) -> None:
        self._must_reject(
            disposition=CONTINUE_WITH_EFFECT_REAUTH_HOLD,
            reason_code=REASON_NONE,
            continuation_refs=(),
            held_refs=("effect:1",),
            requires_effect_verification=False,
            requires_effect_reauthorization=True,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
