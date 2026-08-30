#!/usr/bin/env python3
"""Executable falsifier/regression for F2-WP-901 generation 2.

Generation 2 requires the exported RestartContinuationPlan constructor to enforce one coherent
semantic tuple across disposition, reason_code, continuation/held references and effect flags.

Important anti-Goodhart rule: contradiction tests must use the *correct* reason_code for the
disposition they exercise. Otherwise reason-code validation could raise first and falsely make
reference/flag regressions look green without testing their intended invariant.
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


REASON_CONTINUE = "EXPLICIT_UNFINISHED_EVIDENCE"
REASON_VERIFY = "UNRESOLVED_EFFECT_OUTCOME_REQUIRES_VERIFICATION"
REASON_REAUTHORIZE = "VERIFIED_NOT_APPLIED_EFFECT_REQUIRES_EXPLICIT_REAUTHORIZATION"
REASON_NONE = "NO_EXPLICIT_UNFINISHED_WORK"


def sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def fields(*, reason_code: str) -> dict[str, object]:
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
        "reason_code": reason_code,
        "provenance_refs": ("receipt:wp900", "receipt:wp206"),
    }


class RestartPlanSemanticConsistencyTests(unittest.TestCase):
    def test_each_canonical_semantic_tuple_is_constructible(self) -> None:
        cases = (
            dict(
                disposition=NO_CONTINUATION,
                reason_code=REASON_NONE,
                continuation_refs=(),
                held_refs=(),
                requires_effect_verification=False,
                requires_effect_reauthorization=False,
            ),
            dict(
                disposition=CONTINUE_UNFINISHED,
                reason_code=REASON_CONTINUE,
                continuation_refs=("work:alpha",),
                held_refs=(),
                requires_effect_verification=False,
                requires_effect_reauthorization=False,
            ),
            dict(
                disposition=HOLD_EFFECT_VERIFICATION,
                reason_code=REASON_VERIFY,
                continuation_refs=(),
                held_refs=("effect:send-1",),
                requires_effect_verification=True,
                requires_effect_reauthorization=False,
            ),
            dict(
                disposition=CONTINUE_WITH_EFFECT_REAUTH_HOLD,
                reason_code=REASON_REAUTHORIZE,
                continuation_refs=("work:alpha",),
                held_refs=("effect:send-1",),
                requires_effect_verification=False,
                requires_effect_reauthorization=True,
            ),
        )
        for case in cases:
            with self.subTest(case["disposition"]):
                reason_code = case.pop("reason_code")
                try:
                    plan = RestartContinuationPlan(
                        **fields(reason_code=reason_code),
                        **case,
                    )
                finally:
                    case["reason_code"] = reason_code
                self.assertEqual(plan.disposition, case["disposition"])
                self.assertEqual(plan.reason_code, reason_code)

    def test_continue_unfinished_rejects_verification_hold_contradiction(self) -> None:
        with self.assertRaises(RestartRecoveryError):
            RestartContinuationPlan(
                **fields(reason_code=REASON_CONTINUE),
                disposition=CONTINUE_UNFINISHED,
                continuation_refs=("work:alpha",),
                held_refs=("effect:send-1",),
                requires_effect_verification=True,
                requires_effect_reauthorization=False,
            )

    def test_continue_unfinished_requires_actual_continuation(self) -> None:
        with self.assertRaises(RestartRecoveryError):
            RestartContinuationPlan(
                **fields(reason_code=REASON_CONTINUE),
                disposition=CONTINUE_UNFINISHED,
                continuation_refs=(),
                held_refs=(),
                requires_effect_verification=False,
                requires_effect_reauthorization=False,
            )

    def test_no_continuation_rejects_refs(self) -> None:
        with self.assertRaises(RestartRecoveryError):
            RestartContinuationPlan(
                **fields(reason_code=REASON_NONE),
                disposition=NO_CONTINUATION,
                continuation_refs=("work:alpha",),
                held_refs=(),
                requires_effect_verification=False,
                requires_effect_reauthorization=False,
            )

    def test_verification_hold_requires_held_refs_and_exclusive_flag(self) -> None:
        with self.assertRaises(RestartRecoveryError):
            RestartContinuationPlan(
                **fields(reason_code=REASON_VERIFY),
                disposition=HOLD_EFFECT_VERIFICATION,
                continuation_refs=(),
                held_refs=(),
                requires_effect_verification=True,
                requires_effect_reauthorization=False,
            )
        with self.assertRaises(RestartRecoveryError):
            RestartContinuationPlan(
                **fields(reason_code=REASON_VERIFY),
                disposition=HOLD_EFFECT_VERIFICATION,
                continuation_refs=(),
                held_refs=("effect:send-1",),
                requires_effect_verification=True,
                requires_effect_reauthorization=True,
            )

    def test_reauth_hold_requires_held_refs_and_reauth_only(self) -> None:
        with self.assertRaises(RestartRecoveryError):
            RestartContinuationPlan(
                **fields(reason_code=REASON_REAUTHORIZE),
                disposition=CONTINUE_WITH_EFFECT_REAUTH_HOLD,
                continuation_refs=(),
                held_refs=(),
                requires_effect_verification=False,
                requires_effect_reauthorization=True,
            )
        with self.assertRaises(RestartRecoveryError):
            RestartContinuationPlan(
                **fields(reason_code=REASON_REAUTHORIZE),
                disposition=CONTINUE_WITH_EFFECT_REAUTH_HOLD,
                continuation_refs=("work:alpha",),
                held_refs=("effect:send-1",),
                requires_effect_verification=True,
                requires_effect_reauthorization=True,
            )

    def test_each_disposition_rejects_cross_paired_reason_code(self) -> None:
        cases = (
            dict(
                disposition=NO_CONTINUATION,
                correct_reason=REASON_NONE,
                wrong_reason=REASON_CONTINUE,
                continuation_refs=(),
                held_refs=(),
                requires_effect_verification=False,
                requires_effect_reauthorization=False,
            ),
            dict(
                disposition=CONTINUE_UNFINISHED,
                correct_reason=REASON_CONTINUE,
                wrong_reason=REASON_NONE,
                continuation_refs=("work:alpha",),
                held_refs=(),
                requires_effect_verification=False,
                requires_effect_reauthorization=False,
            ),
            dict(
                disposition=HOLD_EFFECT_VERIFICATION,
                correct_reason=REASON_VERIFY,
                wrong_reason=REASON_REAUTHORIZE,
                continuation_refs=(),
                held_refs=("effect:send-1",),
                requires_effect_verification=True,
                requires_effect_reauthorization=False,
            ),
            dict(
                disposition=CONTINUE_WITH_EFFECT_REAUTH_HOLD,
                correct_reason=REASON_REAUTHORIZE,
                wrong_reason=REASON_VERIFY,
                continuation_refs=(),
                held_refs=("effect:send-1",),
                requires_effect_verification=False,
                requires_effect_reauthorization=True,
            ),
        )
        for case in cases:
            with self.subTest(case["disposition"]):
                with self.assertRaisesRegex(
                    RestartRecoveryError,
                    "reason_code must match the deterministic disposition semantics",
                ):
                    RestartContinuationPlan(
                        **fields(reason_code=case["wrong_reason"]),
                        disposition=case["disposition"],
                        continuation_refs=case["continuation_refs"],
                        held_refs=case["held_refs"],
                        requires_effect_verification=case["requires_effect_verification"],
                        requires_effect_reauthorization=case[
                            "requires_effect_reauthorization"
                        ],
                    )


if __name__ == "__main__":
    unittest.main(verbosity=2)
