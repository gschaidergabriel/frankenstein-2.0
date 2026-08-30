#!/usr/bin/env python3
"""Repository-hosted regressions for F2-WP-901 generation 3 source binding."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import unittest

from frankenstein2.causal_authority_binding import UnifiedDBAuthorityRef
from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.persistent_agency_kernel import advance_checkpoint
from frankenstein2.restart_recovery_continuation import (
    CONTINUE_UNFINISHED,
    PersistedRestartEvidence,
)
from frankenstein2.restart_recovery_source_authentication import (
    RestartSourceAuthenticationError,
    bind_restart_sources,
    causal_identity_ref,
    plan_restart_continuation_from_sources,
)
from frankenstein2.whole_persistent_loop import (
    LoopOutcomeEvidence,
    NO_EFFECT,
    required_reentry_refs,
    seal_whole_persistent_loop,
)
from tests.test_whole_persistent_loop import fixture_components


def sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def authority() -> UnifiedDBAuthorityRef:
    return UnifiedDBAuthorityRef(
        receipt_ref="receipt:unifieddb:accepted-component",
        canonical_source="src/frankenstein2/unifieddb_authority.py",
        fingerprint_schema="FRANKENSTEIN2_UNIFIEDDB_FINGERPRINT/v2",
    )


def identity(causal_id: str, generation: int) -> CausalIdentity:
    return CausalIdentity(
        session_id="session-wp901-g3",
        agent_id="agent-wp901-g3",
        task_id="task-wp901-g3",
        turn_id="turn-wp901-g3",
        causal_id=causal_id,
        generation=generation,
        parent_causal_id="causal-wp901-g3-parent",
    )


class RestartRecoverySourceAuthenticationTests(unittest.TestCase):
    def sources(self, *, causal_id: str = "causal-wp901-g3"):
        (
            current_checkpoint,
            frame,
            contract,
            grid_plan,
            gwt_seal,
            gwt_evidence,
            decision,
            _fixture_outcome,
            _fixture_next_checkpoint,
        ) = fixture_components()

        causal = identity(causal_id, current_checkpoint.generation + 1)
        causal_ref = causal_identity_ref(causal)
        outcome = LoopOutcomeEvidence(
            outcome_id="outcome-wp901-g3",
            status=NO_EFFECT,
            provenance_refs=(causal_ref, "test:wp901:g3:outcome"),
        )
        reentry_refs = required_reentry_refs(
            current_checkpoint=current_checkpoint,
            frame=frame,
            contract=contract,
            plan=grid_plan,
            gwt_seal=gwt_seal,
            decision=decision,
            outcome=outcome,
        )
        next_checkpoint = advance_checkpoint(
            current_checkpoint,
            checkpoint_id="checkpoint-wp901-g3",
            pulse_id="pulse-wp901-g3",
            observation_id="observation-wp901-g3",
            provenance_refs=tuple(sorted(set(reentry_refs) | {causal_ref})),
        )
        whole_loop_seal = seal_whole_persistent_loop(
            seal_id="whole-loop-seal-wp901-g3",
            generation=current_checkpoint.generation,
            current_checkpoint=current_checkpoint,
            frame=frame,
            contract=contract,
            plan=grid_plan,
            gwt_seal=gwt_seal,
            gwt_evidence=gwt_evidence,
            decision=decision,
            outcome=outcome,
            next_checkpoint=next_checkpoint,
            provenance_refs=(causal_ref, "test:wp901:g3:whole-loop"),
        )
        evidence = PersistedRestartEvidence(
            evidence_id="restart-evidence-wp901-g3",
            source_checkpoint_id=next_checkpoint.checkpoint_id,
            source_checkpoint_generation=next_checkpoint.generation,
            source_checkpoint_sha256=next_checkpoint.sha256(),
            whole_loop_seal_id=whole_loop_seal.seal_id,
            whole_loop_seal_sha256=whole_loop_seal.sha256(),
            outcome_status=outcome.status,
            outcome_sha256=outcome.sha256(),
            unfinished_work_refs=("work:alpha", "work:beta"),
            completed_work_refs=("work:done",),
            effect_attempt_refs=(),
            provenance_refs=(causal_ref, "receipt:wp900", "receipt:wp206"),
        )
        return causal, next_checkpoint, whole_loop_seal, outcome, evidence

    def plan(self):
        causal, checkpoint, seal, outcome, evidence = self.sources()
        plan = plan_restart_continuation_from_sources(
            evidence,
            plan_id="restart-plan-wp901-g3",
            expected_evidence_sha256=evidence.sha256(),
            causal_identity=causal,
            unifieddb_authority=authority(),
            source_checkpoint=checkpoint,
            whole_loop_seal=seal,
            outcome=outcome,
        )
        return plan, causal, checkpoint, seal, outcome, evidence

    def test_bound_sources_preserve_accepted_g2_continue_semantics(self) -> None:
        plan, _, checkpoint, _, _, _ = self.plan()
        self.assertEqual(plan.disposition, CONTINUE_UNFINISHED)
        self.assertEqual(plan.reason_code, "EXPLICIT_UNFINISHED_EVIDENCE")
        self.assertEqual(plan.continuation_refs, ("work:alpha", "work:beta"))
        self.assertEqual(plan.held_refs, ())
        self.assertFalse(plan.requires_effect_verification)
        self.assertFalse(plan.requires_effect_reauthorization)
        self.assertEqual(plan.candidate_generation, checkpoint.generation + 1)

    def test_pr683_self_attested_fake_principal_strings_fail_against_concrete_sources(self) -> None:
        causal, checkpoint, seal, outcome, good = self.sources()
        forged = PersistedRestartEvidence(
            evidence_id="forged-self-attested-evidence",
            source_checkpoint_id="checkpoint-never-loaded-from-wp206",
            source_checkpoint_generation=checkpoint.generation,
            source_checkpoint_sha256=sha("checkpoint-never-loaded-from-wp206"),
            whole_loop_seal_id="seal-never-loaded-from-wp900",
            whole_loop_seal_sha256=sha("seal-never-loaded-from-wp900"),
            outcome_status=good.outcome_status,
            outcome_sha256=good.outcome_sha256,
            unfinished_work_refs=good.unfinished_work_refs,
            completed_work_refs=good.completed_work_refs,
            effect_attempt_refs=good.effect_attempt_refs,
            provenance_refs=good.provenance_refs,
        )
        with self.assertRaisesRegex(
            RestartSourceAuthenticationError,
            "SOURCE_AUTH_EVIDENCE_CHECKPOINT_ID_MISMATCH",
        ):
            plan_restart_continuation_from_sources(
                forged,
                plan_id="forged-self-attested-plan",
                expected_evidence_sha256=forged.sha256(),
                causal_identity=causal,
                unifieddb_authority=authority(),
                source_checkpoint=checkpoint,
                whole_loop_seal=seal,
                outcome=outcome,
            )

    def test_pr669_mixed_causal_lineage_fails_closed(self) -> None:
        causal, checkpoint, seal, outcome, evidence = self.sources()
        foreign = identity("causal-episode-B", checkpoint.generation)
        foreign_ref = causal_identity_ref(foreign)
        mixed_seal = replace(
            seal,
            provenance_refs=(foreign_ref, "test:wp901:g3:foreign-seal"),
        )
        mixed_evidence = replace(
            evidence,
            whole_loop_seal_sha256=mixed_seal.sha256(),
        )
        with self.assertRaisesRegex(
            RestartSourceAuthenticationError,
            "SOURCE_AUTH_CAUSAL_REF_MISSING:whole_loop_seal",
        ):
            bind_restart_sources(
                mixed_evidence,
                causal_identity=causal,
                unifieddb_authority=authority(),
                source_checkpoint=checkpoint,
                whole_loop_seal=mixed_seal,
                outcome=outcome,
            )

    def test_seal_must_name_exact_concrete_checkpoint(self) -> None:
        causal, checkpoint, seal, outcome, evidence = self.sources()
        forged_seal = replace(seal, next_checkpoint_id="checkpoint-other")
        forged_evidence = replace(
            evidence,
            whole_loop_seal_sha256=forged_seal.sha256(),
        )
        with self.assertRaisesRegex(
            RestartSourceAuthenticationError,
            "SOURCE_AUTH_SEAL_CHECKPOINT_ID_MISMATCH",
        ):
            bind_restart_sources(
                forged_evidence,
                causal_identity=causal,
                unifieddb_authority=authority(),
                source_checkpoint=checkpoint,
                whole_loop_seal=forged_seal,
                outcome=outcome,
            )

    def test_seal_must_name_exact_concrete_outcome(self) -> None:
        causal, checkpoint, seal, outcome, evidence = self.sources()
        foreign_outcome = replace(
            outcome,
            outcome_id="outcome-other",
        )
        with self.assertRaisesRegex(
            RestartSourceAuthenticationError,
            "SOURCE_AUTH_SEAL_OUTCOME_ID_MISMATCH",
        ):
            bind_restart_sources(
                evidence,
                causal_identity=causal,
                unifieddb_authority=authority(),
                source_checkpoint=checkpoint,
                whole_loop_seal=seal,
                outcome=foreign_outcome,
            )

    def test_causal_identity_generation_must_match_restart_checkpoint(self) -> None:
        _, checkpoint, seal, outcome, evidence = self.sources()
        wrong = identity("causal-wrong-generation", checkpoint.generation + 1)
        with self.assertRaisesRegex(
            RestartSourceAuthenticationError,
            "SOURCE_AUTH_CAUSAL_CHECKPOINT_GENERATION_MISMATCH",
        ):
            bind_restart_sources(
                evidence,
                causal_identity=wrong,
                unifieddb_authority=authority(),
                source_checkpoint=checkpoint,
                whole_loop_seal=seal,
                outcome=outcome,
            )

    def test_checkpoint_without_exact_causal_ref_fails_closed(self) -> None:
        causal, checkpoint, seal, outcome, evidence = self.sources()
        unbound_checkpoint = replace(
            checkpoint,
            provenance_refs=("checkpoint:missing-causal-ref",),
        )
        seal_for_unbound = replace(
            seal,
            next_checkpoint_sha256=unbound_checkpoint.sha256(),
        )
        evidence_for_unbound = replace(
            evidence,
            source_checkpoint_sha256=unbound_checkpoint.sha256(),
            whole_loop_seal_sha256=seal_for_unbound.sha256(),
        )
        with self.assertRaisesRegex(
            RestartSourceAuthenticationError,
            "SOURCE_AUTH_CAUSAL_REF_MISSING:checkpoint",
        ):
            bind_restart_sources(
                evidence_for_unbound,
                causal_identity=causal,
                unifieddb_authority=authority(),
                source_checkpoint=unbound_checkpoint,
                whole_loop_seal=seal_for_unbound,
                outcome=outcome,
            )

    def test_restart_evidence_without_exact_causal_ref_fails_closed(self) -> None:
        causal, checkpoint, seal, outcome, evidence = self.sources()
        unbound_evidence = replace(
            evidence,
            provenance_refs=("receipt:without-causal-ref",),
        )
        with self.assertRaisesRegex(
            RestartSourceAuthenticationError,
            "SOURCE_AUTH_CAUSAL_REF_MISSING:restart_evidence",
        ):
            bind_restart_sources(
                unbound_evidence,
                causal_identity=causal,
                unifieddb_authority=authority(),
                source_checkpoint=checkpoint,
                whole_loop_seal=seal,
                outcome=outcome,
            )

    def test_expected_evidence_digest_mismatch_fails_before_g2_planning(self) -> None:
        causal, checkpoint, seal, outcome, evidence = self.sources()
        with self.assertRaisesRegex(
            RestartSourceAuthenticationError,
            "SOURCE_AUTH_EXPECTED_EVIDENCE_DIGEST_MISMATCH",
        ):
            plan_restart_continuation_from_sources(
                evidence,
                plan_id="wrong-evidence-digest",
                expected_evidence_sha256=sha("wrong-evidence"),
                causal_identity=causal,
                unifieddb_authority=authority(),
                source_checkpoint=checkpoint,
                whole_loop_seal=seal,
                outcome=outcome,
            )

    def test_binding_explicitly_denies_persisted_row_and_effect_authority(self) -> None:
        causal, checkpoint, seal, outcome, evidence = self.sources()
        binding = bind_restart_sources(
            evidence,
            causal_identity=causal,
            unifieddb_authority=authority(),
            source_checkpoint=checkpoint,
            whole_loop_seal=seal,
            outcome=outcome,
        )
        raw = binding.as_dict()
        self.assertEqual(raw["persisted_row_attestation"], "NOT_OBSERVED")
        self.assertEqual(raw["truth_authority"], "NONE")
        self.assertEqual(raw["effect_authority"], "NONE")
        self.assertEqual(raw["completion_authority"], "NONE")
        self.assertEqual(raw["persistence_authority"], "NONE")

    def test_plan_contains_exact_causal_ref_via_evidence_provenance(self) -> None:
        plan, causal, _, _, _, _ = self.plan()
        self.assertIn(causal_identity_ref(causal), plan.provenance_refs)
        raw = plan.as_dict()
        self.assertEqual(raw["scheduler_authority"], "NONE")
        self.assertEqual(raw["effect_authority"], "NONE")
        self.assertEqual(raw["completion_authority"], "NONE")
        self.assertEqual(raw["persistence_authority"], "NONE")


if __name__ == "__main__":
    unittest.main(verbosity=2)
