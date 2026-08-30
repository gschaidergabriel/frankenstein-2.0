#!/usr/bin/env python3
"""Deterministic hostile regressions for F2-WP-300 generation 2 salience projection."""
from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.emergent_retrieval import (
    AXIS_GOAL,
    AXIS_SEMANTIC,
    AXIS_STATE,
    AXIS_TEMPORAL,
    CLASSIFICATION_SUPERSEDED,
    RetrievalCandidate,
    RetrievalNeed,
    RetrievalSignal,
    build_retrieval_plan,
)
from frankenstein2.memory_lifecycle import (
    STATUS_DEGRADED,
    STATUS_SUPERSEDED,
    TRANSITION_DEGRADE,
    TRANSITION_SUPERSEDE,
    MemoryTransition,
    apply_memory_transition,
    create_memory,
)
from frankenstein2.memory_salience_projection import (
    ANCHOR_CREATION,
    ANCHOR_VERIFIED_USE,
    EVIDENCE_SCHEMA,
    MAX_TICK,
    MemorySalienceEvidence,
    MemorySaliencePolicy,
    MemorySalienceProjectionError,
    build_memory_salience_projection,
)


class MemorySalienceProjectionTests(unittest.TestCase):
    @staticmethod
    def memory(memory_id: str = "memory-alpha"):
        return create_memory(
            memory_id=memory_id,
            payload_ref=f"payload:{memory_id}",
            payload_sha256="a" * 64,
            provenance_refs=("source:canonical-memory", "receipt:ingress"),
        )

    @staticmethod
    def policy(*, decay: int = 1000, degraded: int = 4000, floor: int = 0):
        return MemorySaliencePolicy.create(
            policy_id="salience-policy:test-v1",
            min_temporal_bp=floor,
            decay_bp_per_tick=decay,
            degraded_state_bp=degraded,
        )

    @staticmethod
    def evidence(memory, *, reference: int = 10, anchor: int = 8, kind: str = ANCHOR_CREATION):
        return MemorySalienceEvidence.create(
            memory=memory,
            reference_tick=reference,
            anchor_tick=anchor,
            anchor_kind=kind,
            anchor_evidence_refs=("evidence:anchor:typed",),
        )

    @staticmethod
    def degrade(memory):
        transition = MemoryTransition.create(
            transition_id=f"transition:degrade:{memory.memory_id}",
            memory_id=memory.memory_id,
            expected_generation=memory.generation,
            expected_state_sha256=memory.sha256(),
            kind=TRANSITION_DEGRADE,
            evidence_refs=("evidence:degrade",),
        )
        degraded, _ = apply_memory_transition(memory, transition)
        return degraded

    @staticmethod
    def supersede(memory):
        transition = MemoryTransition.create(
            transition_id=f"transition:supersede:{memory.memory_id}",
            memory_id=memory.memory_id,
            expected_generation=memory.generation,
            expected_state_sha256=memory.sha256(),
            kind=TRANSITION_SUPERSEDE,
            successor_ref=f"memory:{memory.memory_id}:successor",
            evidence_refs=("evidence:supersede",),
        )
        superseded, _ = apply_memory_transition(memory, transition)
        return superseded

    def test_identical_inputs_are_bit_deterministic(self) -> None:
        memory = self.memory()
        policy = self.policy()
        evidence = self.evidence(memory)
        first = build_memory_salience_projection(memory, policy=policy, evidence=evidence)
        second = build_memory_salience_projection(memory, policy=policy, evidence=evidence)
        self.assertEqual(first.as_dict(), second.as_dict())
        self.assertEqual(first.sha256(), second.sha256())
        self.assertEqual(first.temporal_signal.score_bp, 8000)
        self.assertEqual(first.state_signal.score_bp, 10000)

    def test_projection_preserves_payload_digest_and_provenance(self) -> None:
        memory = self.memory()
        projection = build_memory_salience_projection(
            memory,
            policy=self.policy(),
            evidence=self.evidence(memory),
        )
        self.assertEqual(projection.payload_ref, memory.payload_ref)
        self.assertEqual(projection.payload_sha256, memory.payload_sha256)
        self.assertEqual(projection.provenance_refs, memory.provenance_refs)
        self.assertEqual(projection.memory_state_sha256, memory.sha256())

    def test_stale_generation_and_state_digest_fail_closed(self) -> None:
        memory = self.memory()
        policy = self.policy()
        evidence = self.evidence(memory)
        with self.assertRaisesRegex(MemorySalienceProjectionError, "generation fence mismatch"):
            build_memory_salience_projection(
                memory,
                policy=policy,
                evidence=replace(evidence, expected_generation=memory.generation + 1),
            )
        with self.assertRaisesRegex(MemorySalienceProjectionError, "state digest fence mismatch"):
            build_memory_salience_projection(
                memory,
                policy=policy,
                evidence=replace(evidence, expected_state_sha256="0" * 64),
            )

    def test_wrong_memory_identity_fails_closed(self) -> None:
        memory = self.memory()
        evidence = self.evidence(memory)
        with self.assertRaisesRegex(MemorySalienceProjectionError, "memory_id fence mismatch"):
            build_memory_salience_projection(
                memory,
                policy=self.policy(),
                evidence=replace(evidence, expected_memory_id="memory-other"),
            )

    def test_ticks_are_explicit_nonnegative_bounded_integers(self) -> None:
        memory = self.memory()
        for invalid in (-1, 1.0, True, MAX_TICK + 1):
            with self.subTest(invalid=invalid):
                with self.assertRaises(MemorySalienceProjectionError):
                    MemorySalienceEvidence.create(
                        memory=memory,
                        reference_tick=invalid,
                        anchor_tick=0,
                        anchor_kind=ANCHOR_CREATION,
                        anchor_evidence_refs=("evidence:creation",),
                    )
        with self.assertRaisesRegex(MemorySalienceProjectionError, "reference_tick must be >= anchor_tick"):
            MemorySalienceEvidence.create(
                memory=memory,
                reference_tick=4,
                anchor_tick=5,
                anchor_kind=ANCHOR_CREATION,
                anchor_evidence_refs=("evidence:creation",),
            )

    def test_missing_anchor_evidence_and_unknown_anchor_kind_fail_closed(self) -> None:
        memory = self.memory()
        with self.assertRaisesRegex(MemorySalienceProjectionError, "at least one"):
            MemorySalienceEvidence.create(
                memory=memory,
                reference_tick=10,
                anchor_tick=0,
                anchor_kind=ANCHOR_CREATION,
                anchor_evidence_refs=(),
            )
        with self.assertRaisesRegex(MemorySalienceProjectionError, "unsupported anchor_kind"):
            MemorySalienceEvidence.create(
                memory=memory,
                reference_tick=10,
                anchor_tick=0,
                anchor_kind="RETRIEVAL_COUNT",
                anchor_evidence_refs=("evidence:retrieval-count",),
            )

    def test_large_tick_delta_clamps_to_explicit_floor_without_overflow(self) -> None:
        memory = self.memory()
        projection = build_memory_salience_projection(
            memory,
            policy=self.policy(decay=10_000, floor=125),
            evidence=self.evidence(memory, reference=MAX_TICK, anchor=0),
        )
        self.assertEqual(projection.temporal_signal.score_bp, 125)

    def test_active_and_degraded_scores_follow_policy(self) -> None:
        active = self.memory()
        degraded = self.degrade(active)
        self.assertEqual(degraded.status, STATUS_DEGRADED)
        policy = self.policy(decay=500, degraded=3250, floor=100)
        active_projection = build_memory_salience_projection(
            active,
            policy=policy,
            evidence=self.evidence(active, reference=10, anchor=8),
        )
        degraded_projection = build_memory_salience_projection(
            degraded,
            policy=policy,
            evidence=self.evidence(degraded, reference=10, anchor=8),
        )
        self.assertEqual(active_projection.temporal_signal.score_bp, 9000)
        self.assertEqual(active_projection.state_signal.score_bp, 10000)
        self.assertEqual(degraded_projection.temporal_signal.score_bp, 9000)
        self.assertEqual(degraded_projection.state_signal.score_bp, 3250)

    def test_superseded_memory_remains_wp301_redirect_only(self) -> None:
        superseded = self.supersede(self.memory("memory-superseded"))
        self.assertEqual(superseded.status, STATUS_SUPERSEDED)
        projection = build_memory_salience_projection(
            superseded,
            policy=self.policy(),
            evidence=self.evidence(superseded),
        )
        candidate = RetrievalCandidate.create(
            memory=superseded,
            signals=(
                RetrievalSignal.create(axis=AXIS_GOAL, score_bp=10000, evidence_refs=("goal:evidence",)),
                RetrievalSignal.create(axis=AXIS_SEMANTIC, score_bp=10000, evidence_refs=("semantic:evidence",)),
                *projection.signals,
            ),
            candidate_evidence_refs=("candidate:evidence",),
        )
        need = RetrievalNeed.create(
            need_id="need:superseded",
            axis_weights_bp={AXIS_GOAL: 10000, AXIS_SEMANTIC: 10000, AXIS_TEMPORAL: 10000, AXIS_STATE: 10000},
            min_overlap_axes=2,
            limit=4,
            evidence_refs=("need:evidence",),
        )
        plan = build_retrieval_plan(need, (candidate,))
        self.assertEqual(plan.selected, ())
        self.assertEqual(len(plan.not_selected), 1)
        result = plan.not_selected[0]
        self.assertEqual(result.classification, CLASSIFICATION_SUPERSEDED)
        self.assertIsNone(result.payload_ref)
        self.assertEqual(result.successor_ref, superseded.successor_ref)

    def test_projection_enters_normal_wp301_ranking_without_score_mutation(self) -> None:
        old = self.degrade(self.memory("memory-old-degraded"))
        recent = self.memory("memory-recent-active")
        policy = self.policy(decay=1000, degraded=4000, floor=0)
        old_projection = build_memory_salience_projection(
            old,
            policy=policy,
            evidence=self.evidence(old, reference=10, anchor=0),
        )
        recent_projection = build_memory_salience_projection(
            recent,
            policy=policy,
            evidence=self.evidence(recent, reference=10, anchor=9),
        )
        old_candidate = RetrievalCandidate.create(
            memory=old,
            signals=(
                RetrievalSignal.create(axis=AXIS_GOAL, score_bp=10000, evidence_refs=("goal:old",)),
                RetrievalSignal.create(axis=AXIS_SEMANTIC, score_bp=10000, evidence_refs=("semantic:old",)),
                *old_projection.signals,
            ),
            candidate_evidence_refs=("candidate:old",),
        )
        recent_candidate = RetrievalCandidate.create(
            memory=recent,
            signals=(
                RetrievalSignal.create(axis=AXIS_GOAL, score_bp=7000, evidence_refs=("goal:recent",)),
                RetrievalSignal.create(axis=AXIS_SEMANTIC, score_bp=7000, evidence_refs=("semantic:recent",)),
                *recent_projection.signals,
            ),
            candidate_evidence_refs=("candidate:recent",),
        )
        need = RetrievalNeed.create(
            need_id="need:salience-ablation",
            axis_weights_bp={AXIS_GOAL: 10000, AXIS_SEMANTIC: 10000, AXIS_TEMPORAL: 10000, AXIS_STATE: 10000},
            min_overlap_axes=2,
            limit=2,
            evidence_refs=("need:salience",),
        )
        plan = build_retrieval_plan(need, (old_candidate, recent_candidate))
        self.assertEqual([result.memory_id for result in plan.selected], [recent.memory_id, old.memory_id])
        recent_result, old_result = plan.selected
        self.assertGreater(recent_result.rank_score, old_result.rank_score)
        self.assertEqual(dict(recent_result.signal_scores_bp)[AXIS_TEMPORAL], recent_projection.temporal_signal.score_bp)
        self.assertEqual(dict(recent_result.signal_scores_bp)[AXIS_STATE], recent_projection.state_signal.score_bp)

    def test_bare_retrieval_does_not_advance_anchor_or_self_reinforce(self) -> None:
        memory = self.memory("memory-feedback-control")
        policy = self.policy(decay=500)
        evidence = self.evidence(memory, reference=20, anchor=0, kind=ANCHOR_CREATION)
        baseline = build_memory_salience_projection(memory, policy=policy, evidence=evidence)
        need = RetrievalNeed.create(
            need_id="need:feedback-control",
            axis_weights_bp={AXIS_GOAL: 10000, AXIS_TEMPORAL: 10000, AXIS_STATE: 10000},
            min_overlap_axes=2,
            limit=1,
            evidence_refs=("need:feedback",),
        )
        for index in range(20):
            candidate = RetrievalCandidate.create(
                memory=memory,
                signals=(
                    RetrievalSignal.create(axis=AXIS_GOAL, score_bp=10000, evidence_refs=(f"goal:{index}",)),
                    *baseline.signals,
                ),
                candidate_evidence_refs=(f"candidate:{index}",),
            )
            build_retrieval_plan(need, (candidate,))
        after_retrievals = build_memory_salience_projection(memory, policy=policy, evidence=evidence)
        self.assertEqual(after_retrievals.anchor_tick, 0)
        self.assertEqual(after_retrievals.temporal_signal.score_bp, baseline.temporal_signal.score_bp)
        self.assertEqual(after_retrievals.sha256(), baseline.sha256())

    def test_verified_use_changes_anchor_only_when_explicit_typed_evidence_changes(self) -> None:
        memory = self.memory("memory-verified-use")
        policy = self.policy(decay=500)
        creation = build_memory_salience_projection(
            memory,
            policy=policy,
            evidence=self.evidence(memory, reference=20, anchor=0, kind=ANCHOR_CREATION),
        )
        verified_use_evidence = MemorySalienceEvidence.create(
            memory=memory,
            reference_tick=20,
            anchor_tick=18,
            anchor_kind=ANCHOR_VERIFIED_USE,
            anchor_evidence_refs=("typed-outcome:verified-use:001",),
        )
        verified = build_memory_salience_projection(
            memory,
            policy=policy,
            evidence=verified_use_evidence,
        )
        self.assertEqual(creation.temporal_signal.score_bp, 0)
        self.assertEqual(verified.temporal_signal.score_bp, 9000)
        self.assertEqual(verified.anchor_kind, ANCHOR_VERIFIED_USE)
        self.assertEqual(verified.payload_ref, creation.payload_ref)
        self.assertNotEqual(verified.evidence_sha256, creation.evidence_sha256)
        self.assertNotEqual(verified.sha256(), creation.sha256())

    def test_policy_is_explicit_and_content_addressed(self) -> None:
        first = self.policy(decay=500, degraded=4000)
        same = self.policy(decay=500, degraded=4000)
        changed = self.policy(decay=501, degraded=4000)
        self.assertEqual(first.sha256(), same.sha256())
        self.assertNotEqual(first.sha256(), changed.sha256())


if __name__ == "__main__":
    unittest.main(verbosity=2)
