import unittest

from frankenstein2.memory_lifecycle import (
    MEMORY_STATE_SCHEMA,
    STATUS_ACTIVE,
    STATUS_DEGRADED,
    STATUS_SUPERSEDED,
    TRANSITION_DEGRADE,
    TRANSITION_RESTORE,
    TRANSITION_SUPERSEDE,
    MemoryLifecycleError,
    MemoryLifecycleState,
    MemoryTransition,
    apply_memory_transition,
    create_memory,
)

PAYLOAD_SHA = "a" * 64


def memory(refs=("source:event-1", "packet:1")):
    return create_memory(
        memory_id="memory-1",
        payload_ref="payload:memory-1",
        payload_sha256=PAYLOAD_SHA,
        provenance_refs=refs,
    )


def transition(state, kind, *, tid="transition-1", successor_ref=None, evidence=("evidence:1",)):
    return MemoryTransition.create(
        transition_id=tid,
        memory_id=state.memory_id,
        expected_generation=state.generation,
        expected_state_sha256=state.sha256(),
        kind=kind,
        evidence_refs=evidence,
        successor_ref=successor_ref,
    )


class MemoryLifecycleTests(unittest.TestCase):
    def test_generation_zero_memory_is_deterministic_and_provenance_order_normalized(self):
        left = memory(("packet:1", "source:event-1"))
        right = memory(("source:event-1", "packet:1"))
        self.assertEqual(left.schema, MEMORY_STATE_SCHEMA)
        self.assertEqual(left.status, STATUS_ACTIVE)
        self.assertEqual(left.generation, 0)
        self.assertIsNone(left.parent_state_sha256)
        self.assertEqual(left.provenance_refs, ("packet:1", "source:event-1"))
        self.assertEqual(left.sha256(), right.sha256())

    def test_direct_state_construction_cannot_bypass_lifecycle_api(self):
        with self.assertRaisesRegex(MemoryLifecycleError, "created through"):
            MemoryLifecycleState(
                schema=MEMORY_STATE_SCHEMA,
                memory_id="memory-1",
                generation=0,
                payload_ref="payload:memory-1",
                payload_sha256=PAYLOAD_SHA,
                provenance_refs=("source:event-1",),
                status=STATUS_ACTIVE,
                successor_ref=None,
                parent_state_sha256=None,
                classification="PRESERVED_MEMORY_PAYLOAD_LIFECYCLE_NOT_TRUTH_OR_RETRIEVAL_AUTHORITY",
            )

    def test_degrade_preserves_payload_and_source_provenance(self):
        before = memory()
        after, receipt = apply_memory_transition(before, transition(before, TRANSITION_DEGRADE))
        self.assertEqual(after.status, STATUS_DEGRADED)
        self.assertEqual(after.generation, 1)
        self.assertEqual(after.payload_ref, before.payload_ref)
        self.assertEqual(after.payload_sha256, before.payload_sha256)
        self.assertEqual(after.provenance_refs, before.provenance_refs)
        self.assertEqual(after.parent_state_sha256, before.sha256())
        self.assertEqual(receipt.from_state_sha256, before.sha256())
        self.assertEqual(receipt.to_state_sha256, after.sha256())

    def test_restore_is_explicit_and_preserves_payload(self):
        initial = memory()
        degraded, _ = apply_memory_transition(initial, transition(initial, TRANSITION_DEGRADE))
        restored, receipt = apply_memory_transition(
            degraded,
            transition(degraded, TRANSITION_RESTORE, tid="transition-2"),
        )
        self.assertEqual(restored.status, STATUS_ACTIVE)
        self.assertEqual(restored.generation, 2)
        self.assertEqual(restored.payload_ref, initial.payload_ref)
        self.assertEqual(restored.payload_sha256, initial.payload_sha256)
        self.assertEqual(restored.provenance_refs, initial.provenance_refs)
        self.assertEqual(receipt.from_generation, 1)
        self.assertEqual(receipt.to_generation, 2)

    def test_supersede_requires_explicit_successor_and_is_terminal(self):
        initial = memory()
        with self.assertRaisesRegex(MemoryLifecycleError, "requires successor_ref"):
            transition(initial, TRANSITION_SUPERSEDE)
        superseded, _ = apply_memory_transition(
            initial,
            transition(initial, TRANSITION_SUPERSEDE, successor_ref="memory-2"),
        )
        self.assertEqual(superseded.status, STATUS_SUPERSEDED)
        self.assertEqual(superseded.successor_ref, "memory-2")
        with self.assertRaisesRegex(MemoryLifecycleError, "terminal"):
            apply_memory_transition(
                superseded,
                transition(superseded, TRANSITION_DEGRADE, tid="transition-2"),
            )

    def test_supersede_rejects_self_reference(self):
        state = memory()
        with self.assertRaisesRegex(MemoryLifecycleError, "must not self-reference"):
            transition(state, TRANSITION_SUPERSEDE, successor_ref=state.memory_id)

    def test_delete_or_unknown_transition_is_not_a_supported_operation(self):
        state = memory()
        with self.assertRaisesRegex(MemoryLifecycleError, "unsupported memory transition"):
            MemoryTransition.create(
                transition_id="delete-1",
                memory_id=state.memory_id,
                expected_generation=state.generation,
                expected_state_sha256=state.sha256(),
                kind="DELETE",
                evidence_refs=("request:delete",),
            )

    def test_stale_generation_fails_closed(self):
        state = memory()
        request = MemoryTransition.create(
            transition_id="stale-generation",
            memory_id=state.memory_id,
            expected_generation=1,
            expected_state_sha256=state.sha256(),
            kind=TRANSITION_DEGRADE,
            evidence_refs=("evidence:1",),
        )
        with self.assertRaisesRegex(MemoryLifecycleError, "generation fence mismatch"):
            apply_memory_transition(state, request)

    def test_stale_state_digest_fails_closed(self):
        state = memory()
        request = MemoryTransition.create(
            transition_id="stale-digest",
            memory_id=state.memory_id,
            expected_generation=0,
            expected_state_sha256="b" * 64,
            kind=TRANSITION_DEGRADE,
            evidence_refs=("evidence:1",),
        )
        with self.assertRaisesRegex(MemoryLifecycleError, "state digest fence mismatch"):
            apply_memory_transition(state, request)

    def test_memory_id_fence_fails_closed(self):
        state = memory()
        request = MemoryTransition.create(
            transition_id="wrong-memory",
            memory_id="memory-other",
            expected_generation=0,
            expected_state_sha256=state.sha256(),
            kind=TRANSITION_DEGRADE,
            evidence_refs=("evidence:1",),
        )
        with self.assertRaisesRegex(MemoryLifecycleError, "memory_id fence mismatch"):
            apply_memory_transition(state, request)

    def test_invalid_lifecycle_edges_fail_closed(self):
        active = memory()
        with self.assertRaisesRegex(MemoryLifecycleError, "RESTORE requires DEGRADED"):
            apply_memory_transition(active, transition(active, TRANSITION_RESTORE))
        degraded, _ = apply_memory_transition(active, transition(active, TRANSITION_DEGRADE))
        with self.assertRaisesRegex(MemoryLifecycleError, "DEGRADE requires ACTIVE"):
            apply_memory_transition(
                degraded,
                transition(degraded, TRANSITION_DEGRADE, tid="transition-2"),
            )

    def test_duplicate_provenance_and_transition_evidence_fail_closed(self):
        with self.assertRaisesRegex(MemoryLifecycleError, "duplicate references"):
            memory(("source:event-1", "source:event-1"))
        state = memory()
        with self.assertRaisesRegex(MemoryLifecycleError, "duplicate references"):
            transition(state, TRANSITION_DEGRADE, evidence=("evidence:1", "evidence:1"))

    def test_transition_receipt_binds_evidence_without_mutating_source_provenance(self):
        state = memory()
        request = transition(
            state,
            TRANSITION_DEGRADE,
            evidence=("review:2", "observation:9"),
        )
        after, receipt = apply_memory_transition(state, request)
        self.assertEqual(receipt.evidence_refs, ("observation:9", "review:2"))
        self.assertEqual(after.provenance_refs, state.provenance_refs)
        self.assertEqual(receipt.transition_sha256, request.sha256())

    def test_same_transition_is_deterministic(self):
        state = memory()
        request_a = transition(state, TRANSITION_DEGRADE, evidence=("b", "a"))
        request_b = transition(state, TRANSITION_DEGRADE, evidence=("a", "b"))
        after_a, receipt_a = apply_memory_transition(state, request_a)
        after_b, receipt_b = apply_memory_transition(state, request_b)
        self.assertEqual(request_a.sha256(), request_b.sha256())
        self.assertEqual(after_a.sha256(), after_b.sha256())
        self.assertEqual(receipt_a.sha256(), receipt_b.sha256())

    def test_serialized_contract_contains_no_clock_retrieval_effect_or_completion_authority(self):
        state = memory()
        after, receipt = apply_memory_transition(state, transition(state, TRANSITION_DEGRADE))
        joined = (after.canonical_json() + str(receipt.as_dict())).lower()
        for forbidden in (
            "timestamp",
            "created_at",
            "expires_at",
            "retrieval_score",
            "semantic_score",
            "effect_request",
            "completion",
            "provider",
            "tool_call",
        ):
            self.assertNotIn(forbidden, joined)


if __name__ == "__main__":
    unittest.main(verbosity=2)
