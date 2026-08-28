#!/usr/bin/env python3
"""Deterministic falsification suite for F2-WP-303 typed memory split."""
from __future__ import annotations

import unittest

from frankenstein2.memory_lifecycle import (
    TRANSITION_DEGRADE,
    MemoryTransition,
    apply_memory_transition,
    create_memory,
)
from frankenstein2.typed_memory import (
    KIND_EPISODE,
    KIND_FACT,
    KIND_METHOD,
    KIND_PROCESS,
    TYPED_MEMORY_SCHEMA,
    TypedMemoryError,
    TypedMemoryRecord,
    create_typed_memory,
    verify_typed_memory_binding,
)


PAYLOAD_SHA = "1" * 64


def base_memory():
    return create_memory(
        memory_id="memory-001",
        payload_ref="payloads/memory-001.json",
        payload_sha256=PAYLOAD_SHA,
        provenance_refs=("event:alpha", "source:unit-test"),
    )


class TypedMemoryTests(unittest.TestCase):
    def test_fact_binds_exact_lifecycle_identity_without_payload_inspection(self):
        state = base_memory()
        record = create_typed_memory(
            state=state,
            memory_kind=KIND_FACT,
            refs={
                "counterevidence": ("evidence:counter-2", "evidence:counter-1"),
                "evidence": ("evidence:obs-1",),
            },
        )
        self.assertEqual(record.schema, TYPED_MEMORY_SCHEMA)
        self.assertEqual(record.memory_kind, KIND_FACT)
        self.assertEqual(record.memory_id, state.memory_id)
        self.assertEqual(record.lifecycle_generation, state.generation)
        self.assertEqual(record.lifecycle_state_sha256, state.sha256())
        self.assertEqual(record.payload_ref, state.payload_ref)
        self.assertEqual(record.payload_sha256, state.payload_sha256)
        self.assertEqual(record.provenance_refs, state.provenance_refs)
        self.assertEqual(record.refs_for("evidence"), ("evidence:obs-1",))
        self.assertEqual(
            record.refs_for("counterevidence"),
            ("evidence:counter-1", "evidence:counter-2"),
        )
        self.assertEqual(record.classification, "FACT_MEMORY_RECORD_NOT_WORLD_TRUTH_AUTHORITY")
        self.assertIn("NOT_INFERRED_TRUTH_OR_AUTHORITY", record.authority_boundary)
        verify_typed_memory_binding(record, state)

    def test_kind_specific_metadata_is_mechanically_separated(self):
        state = base_memory()
        with self.assertRaisesRegex(TypedMemoryError, "cannot carry ref tag 'falsifier'"):
            create_typed_memory(
                state=state,
                memory_kind=KIND_FACT,
                refs={"evidence": ("e:1",), "falsifier": ("f:1",)},
            )
        with self.assertRaisesRegex(TypedMemoryError, "cannot carry ref tag 'evidence'"):
            create_typed_memory(
                state=state,
                memory_kind=KIND_METHOD,
                refs={"method": ("m:1",), "evidence": ("e:1",)},
            )
        with self.assertRaisesRegex(TypedMemoryError, "cannot carry ref tag 'checkpoint'"):
            create_typed_memory(
                state=state,
                memory_kind=KIND_EPISODE,
                refs={"event": ("event:1",), "checkpoint": ("cp:1",)},
            )

    def test_method_memory_carries_method_specific_refs_without_becoming_fact(self):
        record = create_typed_memory(
            state=base_memory(),
            memory_kind=KIND_METHOD,
            refs={
                "method": ("method:smallest-discriminator",),
                "discriminator": ("test:ablation-7",),
                "falsifier": ("falsifier:counterexample",),
                "failure_signature": ("failure:stale-digest",),
                "transfer_condition": ("condition:shared-state-boundary",),
                "anti_pattern": ("anti:component-pass-whole-pass",),
            },
        )
        self.assertEqual(record.memory_kind, KIND_METHOD)
        self.assertEqual(record.classification, "METHOD_MEMORY_RECORD_NOT_FACT_OR_TRANSFER_AUTHORITY")
        self.assertEqual(record.refs_for("falsifier"), ("falsifier:counterexample",))
        self.assertEqual(record.refs_for("evidence"), ())

    def test_episode_and_process_require_distinct_minimum_lineage(self):
        state = base_memory()
        episode = create_typed_memory(
            state=state,
            memory_kind=KIND_EPISODE,
            refs={"event": ("event:42",), "causal": ("causal:7",)},
        )
        process = create_typed_memory(
            state=state,
            memory_kind=KIND_PROCESS,
            refs={
                "process": ("process:goal-evaluation",),
                "checkpoint": ("checkpoint:12",),
                "next_action": ("action:observe",),
            },
        )
        self.assertEqual(episode.classification, "EPISODE_MEMORY_RECORD_NOT_CAUSAL_TRUTH_AUTHORITY")
        self.assertEqual(process.classification, "PROCESS_MEMORY_RECORD_NOT_COMPLETION_OR_EFFECT_AUTHORITY")
        with self.assertRaisesRegex(TypedMemoryError, "missing required typed ref tags"):
            create_typed_memory(state=state, memory_kind=KIND_EPISODE, refs={"causal": ("c:1",)})
        with self.assertRaisesRegex(TypedMemoryError, "missing required typed ref tags"):
            create_typed_memory(state=state, memory_kind=KIND_PROCESS, refs={"process": ("p:1",)})

    def test_fact_requires_explicit_evidence_but_evidence_does_not_mint_truth(self):
        with self.assertRaisesRegex(TypedMemoryError, "missing required typed ref tags"):
            create_typed_memory(
                state=base_memory(),
                memory_kind=KIND_FACT,
                refs={"counterevidence": ("counter:1",)},
            )
        record = create_typed_memory(
            state=base_memory(),
            memory_kind=KIND_FACT,
            refs={"evidence": ("source:receipt-1",)},
        )
        self.assertNotIn("VERIFIED", record.classification)
        self.assertNotIn("CANONICAL", record.classification)

    def test_unknown_or_normalized_kind_is_not_inferred(self):
        for kind in ("fact", " FACT", "FACT ", "UNKNOWN", ""):
            with self.subTest(kind=kind):
                with self.assertRaises(TypedMemoryError):
                    create_typed_memory(
                        state=base_memory(),
                        memory_kind=kind,
                        refs={"evidence": ("e:1",)},
                    )

    def test_digest_is_deterministic_under_mapping_and_reference_order(self):
        state = base_memory()
        left = create_typed_memory(
            state=state,
            memory_kind=KIND_METHOD,
            refs={
                "method": ("method:b", "method:a"),
                "falsifier": ("falsifier:z", "falsifier:a"),
            },
        )
        right = create_typed_memory(
            state=state,
            memory_kind=KIND_METHOD,
            refs={
                "falsifier": ("falsifier:a", "falsifier:z"),
                "method": ("method:a", "method:b"),
            },
        )
        self.assertEqual(left.canonical_json(), right.canonical_json())
        self.assertEqual(left.sha256(), right.sha256())

    def test_duplicate_or_malformed_refs_fail_closed(self):
        state = base_memory()
        with self.assertRaisesRegex(TypedMemoryError, "duplicate references"):
            create_typed_memory(
                state=state,
                memory_kind=KIND_FACT,
                refs={"evidence": ("e:1", "e:1")},
            )
        with self.assertRaisesRegex(TypedMemoryError, "iterable of reference strings"):
            create_typed_memory(
                state=state,
                memory_kind=KIND_FACT,
                refs={"evidence": "e:1"},
            )
        with self.assertRaisesRegex(TypedMemoryError, "control characters"):
            create_typed_memory(
                state=state,
                memory_kind=KIND_FACT,
                refs={"evidence": ("bad\nref",)},
            )

    def test_stale_typed_record_does_not_bind_after_lifecycle_transition(self):
        state = base_memory()
        record = create_typed_memory(
            state=state,
            memory_kind=KIND_FACT,
            refs={"evidence": ("evidence:obs-1",)},
        )
        transition = MemoryTransition.create(
            transition_id="transition:degrade-1",
            memory_id=state.memory_id,
            expected_generation=state.generation,
            expected_state_sha256=state.sha256(),
            kind=TRANSITION_DEGRADE,
            evidence_refs=("evidence:degradation-test",),
        )
        degraded, _ = apply_memory_transition(state, transition)
        with self.assertRaisesRegex(TypedMemoryError, "lifecycle binding mismatch"):
            verify_typed_memory_binding(record, degraded)

    def test_direct_record_construction_is_rejected(self):
        with self.assertRaisesRegex(TypedMemoryError, "must be created through create_typed_memory"):
            TypedMemoryRecord(
                schema=TYPED_MEMORY_SCHEMA,
                memory_kind=KIND_FACT,
                memory_id="memory-001",
                lifecycle_generation=0,
                lifecycle_status="ACTIVE",
                lifecycle_state_sha256="2" * 64,
                payload_ref="payload",
                payload_sha256=PAYLOAD_SHA,
                provenance_refs=("source:test",),
                typed_refs=(),
                classification="FACT_MEMORY_RECORD_NOT_WORLD_TRUTH_AUTHORITY",
                authority_boundary="CALLER_DECLARED_MEMORY_KIND_NOT_INFERRED_TRUTH_OR_AUTHORITY",
            )


if __name__ == "__main__":
    unittest.main()
