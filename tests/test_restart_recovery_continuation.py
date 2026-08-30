#!/usr/bin/env python3
"""Repository-hosted acceptance tests for F2-WP-901 generation 2."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.effect_invocation_correlation import (
    EffectCallBinding,
    EffectCorrelationStage,
)
from frankenstein2.persistent_agency_kernel import advance_checkpoint
from frankenstein2.restart_recovery_continuation import (
    CONTINUE_UNFINISHED,
    HOLD_EFFECT_VERIFICATION,
    NO_CONTINUATION,
    PersistedRestartEvidence,
    RestartRecoveryError,
    bind_persisted_restart_evidence,
    causal_identity_ref,
    plan_restart_continuation,
)
from frankenstein2.whole_persistent_loop import (
    EFFECT_OUTCOME_UNKNOWN,
    EFFECT_RESULT_OBSERVED,
    EFFECT_VERIFIED_APPLIED,
    NO_EFFECT,
    LoopOutcomeEvidence,
    required_reentry_refs,
    seal_whole_persistent_loop,
)
from tests.test_whole_persistent_loop import fixture_components


def sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def identity(causal_id: str = "causal-wp901-g2", *, generation: int = 1) -> CausalIdentity:
    return CausalIdentity(
        session_id="session-wp901",
        agent_id="agent-wp901",
        task_id="task-wp901",
        turn_id="turn-wp901",
        causal_id=causal_id,
        generation=generation,
        parent_causal_id="causal-wp901-parent",
    )


class RestartRecoveryContinuationTests(unittest.TestCase):
    def bound_sources(self, *, unknown_effect: bool = False):
        (
            current_checkpoint,
            frame,
            contract,
            plan,
            gwt,
            gwt_evidence,
            decision,
            _,
            _,
        ) = fixture_components()
        causal = identity(generation=current_checkpoint.generation + 1)
        causal_ref = causal_identity_ref(causal)

        if unknown_effect:
            prepared = EffectCallBinding(
                effect_id="effect-wp901",
                return_id=None,
                binding_id="binding-wp901",
                invocation_id="invocation-wp901",
                tool_use_id="tool-use-wp901",
                delegation_id="delegation-wp901",
                child_identity_sha256=sha("child-wp901"),
                stage=EffectCorrelationStage.PREPARED,
            )
            outcome = LoopOutcomeEvidence(
                outcome_id="outcome-wp901-unknown",
                status=EFFECT_OUTCOME_UNKNOWN,
                effect_call=prepared,
                unknown_reason_ref="unknown:transport-after-dispatch",
                provenance_refs=(causal_ref, "outcome:wp901:unknown"),
            )
        else:
            outcome = LoopOutcomeEvidence(
                outcome_id="outcome-wp901-no-effect",
                status=NO_EFFECT,
                provenance_refs=(causal_ref, "outcome:wp901:no-effect"),
            )

        refs = required_reentry_refs(
            current_checkpoint=current_checkpoint,
            frame=frame,
            contract=contract,
            plan=plan,
            gwt_seal=gwt,
            decision=decision,
            outcome=outcome,
        )
        next_checkpoint = advance_checkpoint(
            current_checkpoint,
            checkpoint_id="checkpoint-wp901-g2-1",
            pulse_id="pulse-wp901-g2-1",
            observation_id="observation-wp901-g2-1",
            provenance_refs=tuple(sorted(set(refs) | {causal_ref})),
        )
        whole_loop_seal = seal_whole_persistent_loop(
            seal_id="whole-loop-seal-wp901-g2",
            generation=current_checkpoint.generation,
            current_checkpoint=current_checkpoint,
            frame=frame,
            contract=contract,
            plan=plan,
            gwt_seal=gwt,
            gwt_evidence=gwt_evidence,
            decision=decision,
            outcome=outcome,
            next_checkpoint=next_checkpoint,
            provenance_refs=(causal_ref, "test:wp901:g2:whole-loop"),
        )
        return causal, next_checkpoint, whole_loop_seal, outcome

    def evidence(self, *, unknown_effect: bool = False, provenance_refs=("receipt:wp901:g2",)):
        causal, checkpoint, seal, outcome = self.bound_sources(unknown_effect=unknown_effect)
        if unknown_effect:
            unfinished = ("effect:send-1", "work:independent")
            effect_refs = ("effect:send-1",)
        else:
            unfinished = ("work:alpha", "work:beta")
            effect_refs = ()
        evidence = bind_persisted_restart_evidence(
            evidence_id="recovery-evidence-wp901-g2",
            causal_identity=causal,
            source_checkpoint=checkpoint,
            whole_loop_seal=seal,
            outcome=outcome,
            unfinished_work_refs=unfinished,
            completed_work_refs=("work:done",),
            effect_attempt_refs=effect_refs,
            provenance_refs=provenance_refs,
        )
        return evidence, causal, checkpoint, seal, outcome

    def plan(self, *, unknown_effect: bool = False):
        evidence, causal, checkpoint, seal, outcome = self.evidence(
            unknown_effect=unknown_effect
        )
        plan = plan_restart_continuation(
            evidence,
            plan_id="recovery-plan-wp901-g2",
            expected_evidence_sha256=evidence.sha256(),
            causal_identity=causal,
            source_checkpoint=checkpoint,
            whole_loop_seal=seal,
            outcome=outcome,
        )
        return plan, evidence, causal, checkpoint, seal, outcome

    def raw_evidence(self, **overrides) -> PersistedRestartEvidence:
        causal = overrides.pop("causal_identity", identity())
        values = {
            "evidence_id": "raw-evidence-wp901-g2",
            "causal_identity": causal,
            "source_checkpoint_id": "checkpoint-1",
            "source_checkpoint_generation": causal.generation,
            "source_checkpoint_sha256": sha("checkpoint-1"),
            "whole_loop_seal_id": "seal-0",
            "whole_loop_seal_sha256": sha("seal-0"),
            "outcome_status": NO_EFFECT,
            "outcome_id": "outcome-0",
            "outcome_sha256": sha("outcome-0"),
            "unfinished_work_refs": ("work:alpha",),
            "completed_work_refs": ("work:done",),
            "effect_attempt_refs": (),
            "provenance_refs": (causal_identity_ref(causal), "receipt:raw"),
        }
        values.update(overrides)
        return PersistedRestartEvidence(**values)

    def test_no_effect_continues_only_explicit_unfinished_refs(self) -> None:
        plan, _, _, _, _, _ = self.plan()
        self.assertEqual(plan.disposition, CONTINUE_UNFINISHED)
        self.assertEqual(plan.continuation_refs, ("work:alpha", "work:beta"))
        self.assertEqual(plan.held_refs, ())
        self.assertNotIn("work:done", plan.continuation_refs)
        self.assertFalse(plan.requires_effect_verification)
        self.assertFalse(plan.requires_effect_reauthorization)

    def test_unknown_effect_holds_entire_unfinished_set_and_never_replays(self) -> None:
        plan, _, _, _, _, _ = self.plan(unknown_effect=True)
        self.assertEqual(plan.disposition, HOLD_EFFECT_VERIFICATION)
        self.assertEqual(plan.continuation_refs, ())
        self.assertEqual(plan.held_refs, ("effect:send-1", "work:independent"))
        self.assertTrue(plan.requires_effect_verification)
        self.assertFalse(plan.requires_effect_reauthorization)

    def test_mixed_causal_identity_is_rejected_before_continuation(self) -> None:
        evidence, _, checkpoint, seal, outcome = self.evidence()
        other = identity("causal-episode-B")
        with self.assertRaisesRegex(RestartRecoveryError, "RECOVERY_CAUSAL_IDENTITY_MISMATCH"):
            plan_restart_continuation(
                evidence,
                plan_id="mixed-lineage",
                expected_evidence_sha256=evidence.sha256(),
                causal_identity=other,
                source_checkpoint=checkpoint,
                whole_loop_seal=seal,
                outcome=outcome,
            )

    def test_whole_loop_from_other_lineage_is_rejected(self) -> None:
        _, causal, checkpoint, seal, outcome = self.evidence()
        other_ref = causal_identity_ref(identity("causal-episode-B"))
        foreign_seal = replace(
            seal,
            provenance_refs=(other_ref, "test:foreign-lineage"),
        )
        with self.assertRaisesRegex(
            RestartRecoveryError, "RECOVERY_CAUSAL_LINEAGE_REF_MISSING:whole-loop seal"
        ):
            bind_persisted_restart_evidence(
                evidence_id="foreign-seal",
                causal_identity=causal,
                source_checkpoint=checkpoint,
                whole_loop_seal=foreign_seal,
                outcome=outcome,
                unfinished_work_refs=("work:alpha",),
                provenance_refs=("receipt:test",),
            )

    def test_generation1_self_attestation_shape_no_longer_authenticates_fake_principals(self) -> None:
        good, causal, checkpoint, seal, outcome = self.evidence()
        forged = PersistedRestartEvidence(
            evidence_id=good.evidence_id,
            causal_identity=causal,
            source_checkpoint_id="checkpoint-forged-but-self-consistent",
            source_checkpoint_generation=checkpoint.generation,
            source_checkpoint_sha256=sha("forged-checkpoint"),
            whole_loop_seal_id="seal-forged-but-self-consistent",
            whole_loop_seal_sha256=sha("forged-seal"),
            outcome_status=outcome.status,
            outcome_id=outcome.outcome_id,
            outcome_sha256=outcome.sha256(),
            unfinished_work_refs=good.unfinished_work_refs,
            completed_work_refs=good.completed_work_refs,
            effect_attempt_refs=good.effect_attempt_refs,
            provenance_refs=good.provenance_refs,
        )
        with self.assertRaisesRegex(
            RestartRecoveryError, "RECOVERY_BOUND_SOURCE_OBJECT_MISMATCH"
        ):
            plan_restart_continuation(
                forged,
                plan_id="self-attested-forgery",
                expected_evidence_sha256=forged.sha256(),
                causal_identity=causal,
                source_checkpoint=checkpoint,
                whole_loop_seal=seal,
                outcome=outcome,
            )

    def test_seal_must_name_exact_restart_checkpoint_id(self) -> None:
        _, causal, checkpoint, seal, outcome = self.evidence()
        forged = replace(seal, next_checkpoint_id="checkpoint-other")
        with self.assertRaisesRegex(RestartRecoveryError, "RECOVERY_SEAL_CHECKPOINT_ID_MISMATCH"):
            bind_persisted_restart_evidence(
                evidence_id="wrong-checkpoint-id",
                causal_identity=causal,
                source_checkpoint=checkpoint,
                whole_loop_seal=forged,
                outcome=outcome,
                unfinished_work_refs=("work:alpha",),
            )

    def test_seal_must_name_exact_restart_checkpoint_digest(self) -> None:
        _, causal, checkpoint, seal, outcome = self.evidence()
        forged = replace(seal, next_checkpoint_sha256="f" * 64)
        with self.assertRaisesRegex(
            RestartRecoveryError, "RECOVERY_SEAL_CHECKPOINT_DIGEST_MISMATCH"
        ):
            bind_persisted_restart_evidence(
                evidence_id="wrong-checkpoint-digest",
                causal_identity=causal,
                source_checkpoint=checkpoint,
                whole_loop_seal=forged,
                outcome=outcome,
                unfinished_work_refs=("work:alpha",),
            )

    def test_seal_must_name_exact_outcome_digest(self) -> None:
        _, causal, checkpoint, seal, outcome = self.evidence()
        forged = replace(seal, outcome_sha256="f" * 64)
        with self.assertRaisesRegex(RestartRecoveryError, "RECOVERY_SEAL_OUTCOME_DIGEST_MISMATCH"):
            bind_persisted_restart_evidence(
                evidence_id="wrong-outcome-digest",
                causal_identity=causal,
                source_checkpoint=checkpoint,
                whole_loop_seal=forged,
                outcome=outcome,
                unfinished_work_refs=("work:alpha",),
            )

    def test_checkpoint_missing_lineage_ref_is_rejected(self) -> None:
        _, causal, checkpoint, seal, outcome = self.evidence()
        unbound_checkpoint = replace(
            checkpoint,
            provenance_refs=("checkpoint:without-causal-lineage",),
        )
        seal_for_unbound = replace(
            seal,
            next_checkpoint_sha256=unbound_checkpoint.sha256(),
        )
        with self.assertRaisesRegex(
            RestartRecoveryError, "RECOVERY_CAUSAL_LINEAGE_REF_MISSING:checkpoint"
        ):
            bind_persisted_restart_evidence(
                evidence_id="unbound-checkpoint",
                causal_identity=causal,
                source_checkpoint=unbound_checkpoint,
                whole_loop_seal=seal_for_unbound,
                outcome=outcome,
                unfinished_work_refs=("work:alpha",),
            )

    def test_causal_generation_must_match_restart_checkpoint(self) -> None:
        _, _, checkpoint, seal, outcome = self.evidence()
        wrong_generation = identity("causal-wrong-generation", generation=checkpoint.generation + 1)
        with self.assertRaisesRegex(RestartRecoveryError, "RECOVERY_CAUSAL_GENERATION_MISMATCH"):
            bind_persisted_restart_evidence(
                evidence_id="wrong-causal-generation",
                causal_identity=wrong_generation,
                source_checkpoint=checkpoint,
                whole_loop_seal=seal,
                outcome=outcome,
                unfinished_work_refs=("work:alpha",),
            )

    def test_evidence_digest_mismatch_fails_closed(self) -> None:
        evidence, causal, checkpoint, seal, outcome = self.evidence()
        with self.assertRaisesRegex(RestartRecoveryError, "RECOVERY_EVIDENCE_DIGEST_MISMATCH"):
            plan_restart_continuation(
                evidence,
                plan_id="bad-evidence-digest",
                expected_evidence_sha256=sha("wrong-evidence"),
                causal_identity=causal,
                source_checkpoint=checkpoint,
                whole_loop_seal=seal,
                outcome=outcome,
            )

    def test_completed_and_unfinished_sets_must_be_disjoint(self) -> None:
        with self.assertRaisesRegex(RestartRecoveryError, "must be disjoint"):
            self.raw_evidence(
                unfinished_work_refs=("work:same",),
                completed_work_refs=("work:same",),
            )

    def test_no_effect_cannot_smuggle_effect_attempt_ref(self) -> None:
        with self.assertRaisesRegex(RestartRecoveryError, "NO_EFFECT"):
            self.raw_evidence(effect_attempt_refs=("effect:send-1",))

    def test_effect_status_requires_explicit_effect_ref(self) -> None:
        with self.assertRaisesRegex(RestartRecoveryError, "requires explicit effect_attempt_refs"):
            self.raw_evidence(outcome_status=EFFECT_OUTCOME_UNKNOWN)

    def test_verified_applied_effect_must_be_explicit_completed_work(self) -> None:
        with self.assertRaisesRegex(
            RestartRecoveryError, "VERIFIED_APPLIED effect_attempt_refs must be completed"
        ):
            self.raw_evidence(
                outcome_status=EFFECT_VERIFIED_APPLIED,
                unfinished_work_refs=("work:independent",),
                completed_work_refs=("work:done",),
                effect_attempt_refs=("effect:send-1",),
            )

    def test_result_observed_effect_ref_must_remain_unfinished(self) -> None:
        with self.assertRaisesRegex(
            RestartRecoveryError, "must remain explicit unfinished work"
        ):
            self.raw_evidence(
                outcome_status=EFFECT_RESULT_OBSERVED,
                unfinished_work_refs=("work:independent",),
                effect_attempt_refs=("effect:send-1",),
            )

    def test_empty_unfinished_set_yields_no_continuation_candidate(self) -> None:
        evidence, causal, checkpoint, seal, outcome = self.evidence()
        empty = bind_persisted_restart_evidence(
            evidence_id="empty-recovery-evidence",
            causal_identity=causal,
            source_checkpoint=checkpoint,
            whole_loop_seal=seal,
            outcome=outcome,
            unfinished_work_refs=(),
            completed_work_refs=("work:done",),
            provenance_refs=("receipt:empty",),
        )
        plan = plan_restart_continuation(
            empty,
            plan_id="empty-plan",
            expected_evidence_sha256=empty.sha256(),
            causal_identity=causal,
            source_checkpoint=checkpoint,
            whole_loop_seal=seal,
            outcome=outcome,
        )
        self.assertEqual(plan.disposition, NO_CONTINUATION)
        self.assertEqual(plan.continuation_refs, ())
        self.assertEqual(plan.held_refs, ())

    def test_reference_order_canonicalizes_to_same_bound_evidence_digest(self) -> None:
        left, _, _, _, _ = self.evidence(
            provenance_refs=("receipt:z", "receipt:a")
        )
        right, _, _, _, _ = self.evidence(
            provenance_refs=("receipt:a", "receipt:z")
        )
        self.assertEqual(left.sha256(), right.sha256())

    def test_plan_carries_exact_causal_identity_and_zero_authority(self) -> None:
        plan, _, causal, checkpoint, _, _ = self.plan()
        raw = plan.as_dict()
        self.assertEqual(raw["causal_identity"], causal.as_dict())
        self.assertEqual(raw["causal_identity_sha256"], causal.sha256())
        self.assertEqual(plan.candidate_generation, checkpoint.generation + 1)
        self.assertEqual(raw["scheduler_authority"], "NONE")
        self.assertEqual(raw["truth_authority"], "NONE")
        self.assertEqual(raw["effect_authority"], "NONE")
        self.assertEqual(raw["completion_authority"], "NONE")
        self.assertEqual(raw["persistence_authority"], "NONE")

    def test_raw_evidence_without_causal_ref_fails_closed(self) -> None:
        causal = identity()
        with self.assertRaisesRegex(
            RestartRecoveryError, "lacks exact causal identity provenance ref"
        ):
            self.raw_evidence(
                causal_identity=causal,
                provenance_refs=("receipt:without-causal-ref",),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
