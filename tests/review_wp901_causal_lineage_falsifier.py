#!/usr/bin/env python3
"""REVIEW_ONLY executable falsifier for F2-WP-901 causal-lineage preservation.

No WP901 mutation authority is claimed. The test demonstrates that the current
repository contract can accept a checkpoint from one declared causal lineage and a
whole-loop seal from another because neither PersistedRestartEvidence nor
RestartContinuationPlan carries an explicit causal-lineage identity and the planner
has no independent lineage-binding witness.

A green review test means the counterexample was reproduced. It is bounded
repository-hosted negative evidence only, not target/runtime/whole-system credit.
"""
from __future__ import annotations

from dataclasses import fields
import hashlib
import unittest

from frankenstein2.restart_recovery_continuation import (
    CONTINUE_UNFINISHED,
    PersistedRestartEvidence,
    RestartContinuationPlan,
    plan_restart_continuation,
)
from frankenstein2.whole_persistent_loop import NO_EFFECT


def sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def build_evidence(checkpoint_lineage: str, loop_lineage: str) -> PersistedRestartEvidence:
    return PersistedRestartEvidence(
        evidence_id=f"recovery:{checkpoint_lineage}:{loop_lineage}",
        source_checkpoint_id=f"checkpoint:{checkpoint_lineage}:9",
        source_checkpoint_generation=9,
        source_checkpoint_sha256=sha(f"checkpoint:{checkpoint_lineage}:9"),
        whole_loop_seal_id=f"whole-loop:{loop_lineage}:9",
        whole_loop_seal_sha256=sha(f"whole-loop:{loop_lineage}:9"),
        outcome_status=NO_EFFECT,
        outcome_sha256=sha(f"outcome:{loop_lineage}:9"),
        unfinished_work_refs=(f"work:{checkpoint_lineage}:alpha",),
        completed_work_refs=(),
        effect_attempt_refs=(),
        provenance_refs=(
            f"causal-lineage:{checkpoint_lineage}:checkpoint",
            f"causal-lineage:{loop_lineage}:whole-loop",
            "receipt:wp900",
            "receipt:wp206",
        ),
    )


class WP901CausalLineageFalsifier(unittest.TestCase):
    def test_contract_has_no_explicit_causal_lineage_field(self) -> None:
        evidence_fields = {f.name for f in fields(PersistedRestartEvidence)}
        plan_fields = {f.name for f in fields(RestartContinuationPlan)}
        forbidden_gap_names = {"causal_id", "causal_lineage_id", "episode_id"}
        self.assertTrue(evidence_fields.isdisjoint(forbidden_gap_names))
        self.assertTrue(plan_fields.isdisjoint(forbidden_gap_names))

    def test_cross_lineage_checkpoint_and_whole_loop_are_accepted(self) -> None:
        mixed = build_evidence("episode-A", "episode-B")
        plan = plan_restart_continuation(
            mixed,
            plan_id="review-cross-lineage-plan",
            expected_evidence_sha256=mixed.sha256(),
            expected_checkpoint_id=mixed.source_checkpoint_id,
            expected_checkpoint_generation=mixed.source_checkpoint_generation,
            expected_checkpoint_sha256=mixed.source_checkpoint_sha256,
            expected_whole_loop_seal_id=mixed.whole_loop_seal_id,
            expected_whole_loop_seal_sha256=mixed.whole_loop_seal_sha256,
        )

        # The counterexample is reproduced when the mixed lineage is accepted as a
        # normal continuation candidate rather than failing closed on lineage mismatch.
        self.assertEqual(plan.disposition, CONTINUE_UNFINISHED)
        self.assertEqual(plan.source_checkpoint_id, "checkpoint:episode-A:9")
        self.assertEqual(plan.whole_loop_seal_id, "whole-loop:episode-B:9")
        self.assertEqual(plan.continuation_refs, ("work:episode-A:alpha",))


if __name__ == "__main__":
    unittest.main(verbosity=2)
