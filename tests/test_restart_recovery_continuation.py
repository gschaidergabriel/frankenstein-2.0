#!/usr/bin/env python3
"""Repository-hosted acceptance tests for F2-WP-901 generation 2."""
from __future__ import annotations

import hashlib
import unittest

from frankenstein2.restart_recovery_continuation import (
    CONTINUE_UNFINISHED,
    CONTINUE_WITH_EFFECT_REAUTH_HOLD,
    HOLD_EFFECT_VERIFICATION,
    NO_CONTINUATION,
    PersistedRestartEvidence,
    RestartContinuationPlan,
    RestartRecoveryError,
    plan_restart_continuation,
)
from frankenstein2.whole_persistent_loop import (
    EFFECT_OUTCOME_UNKNOWN,
    EFFECT_RESULT_OBSERVED,
    EFFECT_VERIFIED_APPLIED,
    EFFECT_VERIFIED_NOT_APPLIED,
    NO_EFFECT,
)


def sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


class RestartRecoveryContinuationTests(unittest.TestCase):
    lineage = "causal-lineage-episode-9"

    def evidence(self, **overrides) -> PersistedRestartEvidence:
        values = {
            "evidence_id": "recovery-evidence-1",
            "causal_lineage_id": self.lineage,
            "source_checkpoint_id": "checkpoint-9",
            "source_checkpoint_generation": 9,
            "source_checkpoint_sha256": sha("checkpoint-9"),
            "source_checkpoint_causal_lineage_id": self.lineage,
            "whole_loop_seal_id": "whole-loop-seal-9",
            "whole_loop_seal_sha256": sha("whole-loop-seal-9"),
            "whole_loop_causal_lineage_id": self.lineage,
            "outcome_status": NO_EFFECT,
            "outcome_sha256": sha("outcome-9"),
            "unfinished_work_refs": ("work:alpha", "work:beta"),
            "completed_work_refs": ("work:done",),
            "effect_attempt_refs": (),
            "provenance_refs": ("receipt:wp900", "receipt:wp206"),
        }
        values.update(overrides)
        return PersistedRestartEvidence(**values)

    def plan(self, evidence: PersistedRestartEvidence):
        return plan_restart_continuation(
            evidence,
            plan_id="recovery-plan-10",
            expected_evidence_sha256=evidence.sha256(),
            expected_causal_lineage_id=evidence.causal_lineage_id,
            expected_checkpoint_id=evidence.source_checkpoint_id,
            expected_checkpoint_generation=evidence.source_checkpoint_generation,
            expected_checkpoint_sha256=evidence.source_checkpoint_sha256,
            expected_whole_loop_seal_id=evidence.whole_loop_seal_id,
            expected_whole_loop_seal_sha256=evidence.whole_loop_seal_sha256,
        )

    def direct_plan_fields(self) -> dict[str, object]:
        evidence = self.evidence()
        return {
            "plan_id": "direct-plan-10",
            "source_evidence_id": evidence.evidence_id,
            "source_evidence_sha256": evidence.sha256(),
            "causal_lineage_id": evidence.causal_lineage_id,
            "source_checkpoint_id": evidence.source_checkpoint_id,
            "source_checkpoint_generation": evidence.source_checkpoint_generation,
            "source_checkpoint_sha256": evidence.source_checkpoint_sha256,
            "whole_loop_seal_id": evidence.whole_loop_seal_id,
            "whole_loop_seal_sha256": evidence.whole_loop_seal_sha256,
            "candidate_generation": 10,
            "provenance_refs": ("receipt:wp900", "receipt:wp206"),
        }

    def test_no_effect_continues_only_explicit_unfinished_refs(self) -> None:
        plan = self.plan(self.evidence())
        self.assertEqual(plan.disposition, CONTINUE_UNFINISHED)
        self.assertEqual(plan.continuation_refs, ("work:alpha", "work:beta"))
        self.assertEqual(plan.held_refs, ())
        self.assertNotIn("work:done", plan.continuation_refs)
        self.assertEqual(plan.candidate_generation, 10)
        self.assertFalse(plan.requires_effect_verification)
        self.assertFalse(plan.requires_effect_reauthorization)

    def test_unknown_effect_holds_entire_unfinished_set_and_never_replays(self) -> None:
        evidence = self.evidence(
            outcome_status=EFFECT_OUTCOME_UNKNOWN,
            unfinished_work_refs=("effect:send-1", "work:independent"),
            effect_attempt_refs=("effect:send-1",),
        )
        plan = self.plan(evidence)
        self.assertEqual(plan.disposition, HOLD_EFFECT_VERIFICATION)
        self.assertEqual(plan.continuation_refs, ())
        self.assertEqual(plan.held_refs, ("effect:send-1", "work:independent"))
        self.assertTrue(plan.requires_effect_verification)
        self.assertFalse(plan.requires_effect_reauthorization)

    def test_result_observed_without_verified_outcome_still_holds(self) -> None:
        evidence = self.evidence(
            outcome_status=EFFECT_RESULT_OBSERVED,
            unfinished_work_refs=("effect:send-1", "work:independent"),
            effect_attempt_refs=("effect:send-1",),
        )
        plan = self.plan(evidence)
        self.assertEqual(plan.disposition, HOLD_EFFECT_VERIFICATION)
        self.assertEqual(plan.continuation_refs, ())
        self.assertTrue(plan.requires_effect_verification)

    def test_verified_not_applied_requires_effect_reauthorization(self) -> None:
        evidence = self.evidence(
            outcome_status=EFFECT_VERIFIED_NOT_APPLIED,
            unfinished_work_refs=("effect:send-1", "work:independent"),
            effect_attempt_refs=("effect:send-1",),
        )
        plan = self.plan(evidence)
        self.assertEqual(plan.disposition, CONTINUE_WITH_EFFECT_REAUTH_HOLD)
        self.assertEqual(plan.continuation_refs, ("work:independent",))
        self.assertEqual(plan.held_refs, ("effect:send-1",))
        self.assertFalse(plan.requires_effect_verification)
        self.assertTrue(plan.requires_effect_reauthorization)

    def test_verified_not_applied_effect_only_may_hold_without_safe_continuation(self) -> None:
        evidence = self.evidence(
            outcome_status=EFFECT_VERIFIED_NOT_APPLIED,
            unfinished_work_refs=("effect:send-1",),
            effect_attempt_refs=("effect:send-1",),
        )
        plan = self.plan(evidence)
        self.assertEqual(plan.disposition, CONTINUE_WITH_EFFECT_REAUTH_HOLD)
        self.assertEqual(plan.continuation_refs, ())
        self.assertEqual(plan.held_refs, ("effect:send-1",))

    def test_verified_applied_effect_must_be_completed_and_is_not_reintroduced(self) -> None:
        evidence = self.evidence(
            outcome_status=EFFECT_VERIFIED_APPLIED,
            unfinished_work_refs=("work:independent",),
            completed_work_refs=("effect:send-1", "work:done"),
            effect_attempt_refs=("effect:send-1",),
        )
        plan = self.plan(evidence)
        self.assertEqual(plan.disposition, CONTINUE_UNFINISHED)
        self.assertEqual(plan.continuation_refs, ("work:independent",))
        self.assertNotIn("effect:send-1", plan.continuation_refs)

    def test_verified_applied_effect_cannot_remain_unfinished(self) -> None:
        with self.assertRaisesRegex(
            RestartRecoveryError, "VERIFIED_APPLIED effect_attempt_refs must be completed"
        ):
            self.evidence(
                outcome_status=EFFECT_VERIFIED_APPLIED,
                unfinished_work_refs=("effect:send-1",),
                completed_work_refs=("work:done",),
                effect_attempt_refs=("effect:send-1",),
            )

    def test_no_effect_cannot_smuggle_effect_attempt_ref(self) -> None:
        with self.assertRaisesRegex(RestartRecoveryError, "NO_EFFECT"):
            self.evidence(effect_attempt_refs=("effect:send-1",))

    def test_effect_status_requires_explicit_effect_ref(self) -> None:
        with self.assertRaisesRegex(RestartRecoveryError, "requires explicit effect_attempt_refs"):
            self.evidence(outcome_status=EFFECT_OUTCOME_UNKNOWN)

    def test_completed_and_unfinished_sets_must_be_disjoint(self) -> None:
        with self.assertRaisesRegex(RestartRecoveryError, "must be disjoint"):
            self.evidence(
                unfinished_work_refs=("work:same",),
                completed_work_refs=("work:same",),
            )

    def test_empty_unfinished_set_yields_no_continuation_candidate(self) -> None:
        plan = self.plan(self.evidence(unfinished_work_refs=()))
        self.assertEqual(plan.disposition, NO_CONTINUATION)
        self.assertEqual(plan.continuation_refs, ())
        self.assertEqual(plan.held_refs, ())

    def test_checkpoint_lineage_mismatch_fails_closed_at_evidence_boundary(self) -> None:
        with self.assertRaisesRegex(RestartRecoveryError, "RECOVERY_CAUSAL_LINEAGE_MISMATCH"):
            self.evidence(source_checkpoint_causal_lineage_id="episode-A")

    def test_whole_loop_lineage_mismatch_fails_closed_at_evidence_boundary(self) -> None:
        with self.assertRaisesRegex(RestartRecoveryError, "RECOVERY_CAUSAL_LINEAGE_MISMATCH"):
            self.evidence(whole_loop_causal_lineage_id="episode-B")

    def test_mixed_checkpoint_and_whole_loop_lineage_falsifier_is_closed(self) -> None:
        with self.assertRaisesRegex(RestartRecoveryError, "RECOVERY_CAUSAL_LINEAGE_MISMATCH"):
            self.evidence(
                causal_lineage_id="episode-A",
                source_checkpoint_causal_lineage_id="episode-A",
                whole_loop_causal_lineage_id="episode-B",
            )

    def test_expected_lineage_mismatch_fails_closed(self) -> None:
        evidence = self.evidence()
        with self.assertRaisesRegex(
            RestartRecoveryError, "RECOVERY_EXPECTED_CAUSAL_LINEAGE_MISMATCH"
        ):
            plan_restart_continuation(
                evidence,
                plan_id="recovery-plan-bad",
                expected_evidence_sha256=evidence.sha256(),
                expected_causal_lineage_id="different-lineage",
                expected_checkpoint_id=evidence.source_checkpoint_id,
                expected_checkpoint_generation=evidence.source_checkpoint_generation,
                expected_checkpoint_sha256=evidence.source_checkpoint_sha256,
                expected_whole_loop_seal_id=evidence.whole_loop_seal_id,
                expected_whole_loop_seal_sha256=evidence.whole_loop_seal_sha256,
            )

    def test_stale_checkpoint_identity_fails_closed(self) -> None:
        evidence = self.evidence()
        with self.assertRaisesRegex(RestartRecoveryError, "RECOVERY_CHECKPOINT_ID_MISMATCH"):
            plan_restart_continuation(
                evidence,
                plan_id="recovery-plan-bad",
                expected_evidence_sha256=evidence.sha256(),
                expected_causal_lineage_id=evidence.causal_lineage_id,
                expected_checkpoint_id="checkpoint-stale",
                expected_checkpoint_generation=evidence.source_checkpoint_generation,
                expected_checkpoint_sha256=evidence.source_checkpoint_sha256,
                expected_whole_loop_seal_id=evidence.whole_loop_seal_id,
                expected_whole_loop_seal_sha256=evidence.whole_loop_seal_sha256,
            )

    def test_generation_mismatch_fails_closed(self) -> None:
        evidence = self.evidence()
        with self.assertRaisesRegex(RestartRecoveryError, "RECOVERY_CHECKPOINT_GENERATION_MISMATCH"):
            plan_restart_continuation(
                evidence,
                plan_id="recovery-plan-bad",
                expected_evidence_sha256=evidence.sha256(),
                expected_causal_lineage_id=evidence.causal_lineage_id,
                expected_checkpoint_id=evidence.source_checkpoint_id,
                expected_checkpoint_generation=evidence.source_checkpoint_generation + 1,
                expected_checkpoint_sha256=evidence.source_checkpoint_sha256,
                expected_whole_loop_seal_id=evidence.whole_loop_seal_id,
                expected_whole_loop_seal_sha256=evidence.whole_loop_seal_sha256,
            )

    def test_evidence_digest_mismatch_fails_closed(self) -> None:
        evidence = self.evidence()
        with self.assertRaisesRegex(RestartRecoveryError, "RECOVERY_EVIDENCE_DIGEST_MISMATCH"):
            plan_restart_continuation(
                evidence,
                plan_id="recovery-plan-bad",
                expected_evidence_sha256=sha("wrong-evidence"),
                expected_causal_lineage_id=evidence.causal_lineage_id,
                expected_checkpoint_id=evidence.source_checkpoint_id,
                expected_checkpoint_generation=evidence.source_checkpoint_generation,
                expected_checkpoint_sha256=evidence.source_checkpoint_sha256,
                expected_whole_loop_seal_id=evidence.whole_loop_seal_id,
                expected_whole_loop_seal_sha256=evidence.whole_loop_seal_sha256,
            )

    def test_checkpoint_digest_mismatch_fails_closed(self) -> None:
        evidence = self.evidence()
        with self.assertRaisesRegex(RestartRecoveryError, "RECOVERY_CHECKPOINT_DIGEST_MISMATCH"):
            plan_restart_continuation(
                evidence,
                plan_id="recovery-plan-bad",
                expected_evidence_sha256=evidence.sha256(),
                expected_causal_lineage_id=evidence.causal_lineage_id,
                expected_checkpoint_id=evidence.source_checkpoint_id,
                expected_checkpoint_generation=evidence.source_checkpoint_generation,
                expected_checkpoint_sha256=sha("wrong-checkpoint"),
                expected_whole_loop_seal_id=evidence.whole_loop_seal_id,
                expected_whole_loop_seal_sha256=evidence.whole_loop_seal_sha256,
            )

    def test_whole_loop_seal_identity_mismatch_fails_closed(self) -> None:
        evidence = self.evidence()
        with self.assertRaisesRegex(RestartRecoveryError, "RECOVERY_WHOLE_LOOP_SEAL_ID_MISMATCH"):
            plan_restart_continuation(
                evidence,
                plan_id="recovery-plan-bad",
                expected_evidence_sha256=evidence.sha256(),
                expected_causal_lineage_id=evidence.causal_lineage_id,
                expected_checkpoint_id=evidence.source_checkpoint_id,
                expected_checkpoint_generation=evidence.source_checkpoint_generation,
                expected_checkpoint_sha256=evidence.source_checkpoint_sha256,
                expected_whole_loop_seal_id="whole-loop-seal-stale",
                expected_whole_loop_seal_sha256=evidence.whole_loop_seal_sha256,
            )

    def test_whole_loop_seal_digest_mismatch_fails_closed(self) -> None:
        evidence = self.evidence()
        with self.assertRaisesRegex(RestartRecoveryError, "RECOVERY_WHOLE_LOOP_SEAL_DIGEST_MISMATCH"):
            plan_restart_continuation(
                evidence,
                plan_id="recovery-plan-bad",
                expected_evidence_sha256=evidence.sha256(),
                expected_causal_lineage_id=evidence.causal_lineage_id,
                expected_checkpoint_id=evidence.source_checkpoint_id,
                expected_checkpoint_generation=evidence.source_checkpoint_generation,
                expected_checkpoint_sha256=evidence.source_checkpoint_sha256,
                expected_whole_loop_seal_id=evidence.whole_loop_seal_id,
                expected_whole_loop_seal_sha256=sha("wrong-loop-seal"),
            )

    def test_reference_order_canonicalizes_to_same_evidence_and_plan_digest(self) -> None:
        left = self.evidence(
            unfinished_work_refs=("work:beta", "work:alpha"),
            provenance_refs=("receipt:wp206", "receipt:wp900"),
        )
        right = self.evidence(
            unfinished_work_refs=("work:alpha", "work:beta"),
            provenance_refs=("receipt:wp900", "receipt:wp206"),
        )
        self.assertEqual(left.sha256(), right.sha256())
        self.assertEqual(self.plan(left).sha256(), self.plan(right).sha256())

    def test_plan_carries_explicit_lineage_and_zero_authority(self) -> None:
        plan = self.plan(self.evidence())
        raw = plan.as_dict()
        self.assertEqual(raw["causal_lineage_id"], self.lineage)
        self.assertEqual(raw["scheduler_authority"], "NONE")
        self.assertEqual(raw["truth_authority"], "NONE")
        self.assertEqual(raw["effect_authority"], "NONE")
        self.assertEqual(raw["completion_authority"], "NONE")
        self.assertEqual(raw["persistence_authority"], "NONE")

    def test_direct_continue_plan_cannot_claim_effect_verification_hold(self) -> None:
        fields = self.direct_plan_fields()
        with self.assertRaises(RestartRecoveryError):
            RestartContinuationPlan(
                **fields,
                disposition=CONTINUE_UNFINISHED,
                reason_code="EXPLICIT_UNFINISHED_EVIDENCE",
                continuation_refs=("work:alpha",),
                held_refs=("effect:send-1",),
                requires_effect_verification=True,
                requires_effect_reauthorization=False,
            )

    def test_direct_no_continuation_plan_cannot_carry_continuation_refs(self) -> None:
        fields = self.direct_plan_fields()
        with self.assertRaises(RestartRecoveryError):
            RestartContinuationPlan(
                **fields,
                disposition=NO_CONTINUATION,
                reason_code="NO_EXPLICIT_UNFINISHED_WORK",
                continuation_refs=("work:alpha",),
                held_refs=(),
                requires_effect_verification=False,
                requires_effect_reauthorization=False,
            )

    def test_direct_verification_hold_requires_held_refs(self) -> None:
        fields = self.direct_plan_fields()
        with self.assertRaises(RestartRecoveryError):
            RestartContinuationPlan(
                **fields,
                disposition=HOLD_EFFECT_VERIFICATION,
                reason_code="UNRESOLVED_EFFECT_OUTCOME_REQUIRES_VERIFICATION",
                continuation_refs=(),
                held_refs=(),
                requires_effect_verification=True,
                requires_effect_reauthorization=False,
            )

    def test_direct_reauthorization_hold_requires_held_refs(self) -> None:
        fields = self.direct_plan_fields()
        with self.assertRaises(RestartRecoveryError):
            RestartContinuationPlan(
                **fields,
                disposition=CONTINUE_WITH_EFFECT_REAUTH_HOLD,
                reason_code="VERIFIED_NOT_APPLIED_EFFECT_REQUIRES_EXPLICIT_REAUTHORIZATION",
                continuation_refs=("work:independent",),
                held_refs=(),
                requires_effect_verification=False,
                requires_effect_reauthorization=True,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
