#!/usr/bin/env python3
"""Review-only regressions for the WP901 source-bound restart candidate."""
from __future__ import annotations

import hashlib
import unittest
from unittest.mock import patch

from frankenstein2.persistent_agency_kernel import PersistentAgencyCheckpoint
from frankenstein2.restart_recovery_continuation import (
    CONTINUE_UNFINISHED,
    PersistedRestartEvidence,
    RestartRecoveryError,
)
from frankenstein2.restart_recovery_source_binding import (
    RestartSourceBinding,
    bind_restart_sources,
    plan_source_bound_restart_continuation,
)
from frankenstein2.whole_persistent_loop import (
    NO_EFFECT,
    LoopOutcomeEvidence,
    WholePersistentLoopSeal,
)


def sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def bare_checkpoint(
    *,
    checkpoint_id: str = "checkpoint-10",
    generation: int = 10,
    previous_checkpoint_id: str = "checkpoint-9",
) -> PersistentAgencyCheckpoint:
    obj = object.__new__(PersistentAgencyCheckpoint)
    object.__setattr__(obj, "checkpoint_id", checkpoint_id)
    object.__setattr__(obj, "generation", generation)
    object.__setattr__(obj, "previous_checkpoint_id", previous_checkpoint_id)
    return obj


def bare_seal(
    *,
    seal_id: str = "whole-loop-seal-9",
    generation: int = 9,
    current_checkpoint_id: str = "checkpoint-9",
    current_checkpoint_sha256: str = sha("checkpoint-9"),
    next_checkpoint_id: str = "checkpoint-10",
    next_checkpoint_sha256: str = sha("checkpoint-10"),
    outcome_id: str = "outcome-9",
    outcome_sha256: str = sha("outcome-9"),
) -> WholePersistentLoopSeal:
    obj = object.__new__(WholePersistentLoopSeal)
    for name, value in {
        "seal_id": seal_id,
        "generation": generation,
        "current_checkpoint_id": current_checkpoint_id,
        "current_checkpoint_sha256": current_checkpoint_sha256,
        "next_checkpoint_id": next_checkpoint_id,
        "next_checkpoint_sha256": next_checkpoint_sha256,
        "outcome_id": outcome_id,
        "outcome_sha256": outcome_sha256,
    }.items():
        object.__setattr__(obj, name, value)
    return obj


def bare_outcome(
    *,
    outcome_id: str = "outcome-9",
    status: str = NO_EFFECT,
) -> LoopOutcomeEvidence:
    obj = object.__new__(LoopOutcomeEvidence)
    object.__setattr__(obj, "outcome_id", outcome_id)
    object.__setattr__(obj, "status", status)
    return obj


class RestartRecoverySourceBindingTests(unittest.TestCase):
    def evidence(self, **overrides) -> PersistedRestartEvidence:
        values = {
            "evidence_id": "recovery-evidence-10",
            "source_checkpoint_id": "checkpoint-10",
            "source_checkpoint_generation": 10,
            "source_checkpoint_sha256": sha("checkpoint-10"),
            "whole_loop_seal_id": "whole-loop-seal-9",
            "whole_loop_seal_sha256": sha("whole-loop-seal-9"),
            "outcome_status": NO_EFFECT,
            "outcome_sha256": sha("outcome-9"),
            "unfinished_work_refs": ("work:alpha",),
            "completed_work_refs": (),
            "effect_attempt_refs": (),
            "provenance_refs": ("receipt:wp206", "receipt:wp900"),
        }
        values.update(overrides)
        return PersistedRestartEvidence(**values)

    def source_patches(self):
        return (
            patch.object(
                PersistentAgencyCheckpoint,
                "sha256",
                autospec=True,
                return_value=sha("checkpoint-10"),
            ),
            patch.object(
                WholePersistentLoopSeal,
                "sha256",
                autospec=True,
                return_value=sha("whole-loop-seal-9"),
            ),
            patch.object(
                LoopOutcomeEvidence,
                "sha256",
                autospec=True,
                return_value=sha("outcome-9"),
            ),
        )

    def bind(self, *, evidence=None, checkpoint=None, seal=None, outcome=None):
        evidence = self.evidence() if evidence is None else evidence
        checkpoint = bare_checkpoint() if checkpoint is None else checkpoint
        seal = bare_seal() if seal is None else seal
        outcome = bare_outcome() if outcome is None else outcome
        p1, p2, p3 = self.source_patches()
        with p1, p2, p3:
            return bind_restart_sources(
                evidence=evidence,
                checkpoint=checkpoint,
                whole_loop_seal=seal,
                outcome=outcome,
            )

    def test_concrete_typed_source_chain_binds_and_plans(self) -> None:
        checkpoint = bare_checkpoint()
        seal = bare_seal()
        outcome = bare_outcome()
        evidence = self.evidence()
        p1, p2, p3 = self.source_patches()
        with p1, p2, p3:
            binding = bind_restart_sources(
                evidence=evidence,
                checkpoint=checkpoint,
                whole_loop_seal=seal,
                outcome=outcome,
            )
            plan = plan_source_bound_restart_continuation(
                binding,
                plan_id="source-bound-plan-11",
            )
        self.assertEqual(plan.base_plan.disposition, CONTINUE_UNFINISHED)
        self.assertEqual(plan.base_plan.candidate_generation, 11)
        self.assertEqual(plan.base_plan.continuation_refs, ("work:alpha",))
        self.assertEqual(len(plan.causal_lineage_sha256), 64)
        self.assertEqual(len(plan.source_binding_sha256), 64)

    def test_self_attested_fake_checkpoint_identity_is_rejected(self) -> None:
        evidence = self.evidence(
            source_checkpoint_id="fabricated-checkpoint",
            source_checkpoint_sha256=sha("fabricated-checkpoint"),
        )
        with self.assertRaisesRegex(
            RestartRecoveryError, "RECOVERY_SOURCE_CHECKPOINT_ID_MISMATCH"
        ):
            self.bind(evidence=evidence)

    def test_mixed_checkpoint_and_whole_loop_lineage_is_rejected(self) -> None:
        checkpoint = bare_checkpoint(previous_checkpoint_id="checkpoint-from-episode-B")
        with self.assertRaisesRegex(
            RestartRecoveryError, "RECOVERY_SOURCE_CAUSAL_LINEAGE_MISMATCH"
        ):
            self.bind(checkpoint=checkpoint)

    def test_whole_loop_must_seal_the_exact_loaded_checkpoint(self) -> None:
        seal = bare_seal(next_checkpoint_sha256=sha("other-checkpoint"))
        with self.assertRaisesRegex(
            RestartRecoveryError, "RECOVERY_SOURCE_SEAL_NEXT_CHECKPOINT_DIGEST_MISMATCH"
        ):
            self.bind(seal=seal)

    def test_direct_successor_generation_is_not_inferred_from_names(self) -> None:
        seal = bare_seal(generation=7)
        with self.assertRaisesRegex(
            RestartRecoveryError, "RECOVERY_SOURCE_DIRECT_SUCCESSOR_GENERATION_MISMATCH"
        ):
            self.bind(seal=seal)

    def test_outcome_status_is_bound_to_concrete_wp900_outcome(self) -> None:
        evidence = self.evidence(outcome_status="EFFECT_OUTCOME_UNKNOWN", effect_attempt_refs=("effect:1",), unfinished_work_refs=("effect:1",))
        with self.assertRaisesRegex(
            RestartRecoveryError, "RECOVERY_SOURCE_OUTCOME_STATUS_MISMATCH"
        ):
            self.bind(evidence=evidence, outcome=bare_outcome(status=NO_EFFECT))

    def test_outcome_digest_must_match_both_seal_and_evidence(self) -> None:
        evidence = self.evidence(outcome_sha256=sha("other-outcome"))
        with self.assertRaisesRegex(
            RestartRecoveryError, "RECOVERY_SOURCE_EVIDENCE_OUTCOME_DIGEST_MISMATCH"
        ):
            self.bind(evidence=evidence)

    def test_emitted_plan_carries_source_binding_and_zero_authority(self) -> None:
        checkpoint = bare_checkpoint()
        seal = bare_seal()
        outcome = bare_outcome()
        p1, p2, p3 = self.source_patches()
        with p1, p2, p3:
            binding = RestartSourceBinding(
                evidence=self.evidence(),
                checkpoint=checkpoint,
                whole_loop_seal=seal,
                outcome=outcome,
            )
            plan = plan_source_bound_restart_continuation(
                binding,
                plan_id="source-bound-plan-11",
            )
            raw = plan.as_dict()
        self.assertEqual(raw["causal_lineage_sha256"], binding.causal_lineage_sha256)
        self.assertEqual(raw["source_binding_sha256"], binding.sha256())
        self.assertEqual(raw["scheduler_authority"], "NONE")
        self.assertEqual(raw["persistence_authority"], "NONE")
        self.assertEqual(raw["truth_authority"], "NONE")
        self.assertEqual(raw["effect_authority"], "NONE")
        self.assertEqual(raw["completion_authority"], "NONE")
        self.assertEqual(raw["runtime_credit"], 0)
        self.assertFalse(raw["whole_system_acceptance"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
