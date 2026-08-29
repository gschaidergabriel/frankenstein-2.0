#!/usr/bin/env python3
"""Deterministic falsification suite for F2-WP-400 sparse world basis."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from frankenstein2.sparse_world_basis import (
    AtomActivation,
    EpistemicOrigin,
    KnowledgeState,
    SparseWorldError,
    WorldAtom,
    WorldNeed,
    WorldOperator,
    materialize_world_slice,
)


def atom(
    atom_id: str,
    *,
    state: KnowledgeState = KnowledgeState.KNOWN,
    vector_space: str = "vs:1",
    generation: int = 4,
) -> WorldAtom:
    return WorldAtom(
        atom_id=atom_id,
        generation=generation,
        vector_space_version=vector_space,
        vector=(len(atom_id), 1, -1),
        epistemic_origin=EpistemicOrigin.OBSERVED,
        knowledge_state=state,
        provenance_refs=(f"source:{atom_id}",),
        evidence_refs=() if state in (KnowledgeState.UNKNOWN, KnowledgeState.NOT_COMPUTED) else (f"evidence:{atom_id}",),
        confidence_micros=None if state in (KnowledgeState.UNKNOWN, KnowledgeState.NOT_COMPUTED) else 900_000,
    )


def op(operator_id: str, inputs: tuple[str, ...], outputs: tuple[str, ...], *, generation: int = 4) -> WorldOperator:
    return WorldOperator(
        operator_id=operator_id,
        generation=generation,
        operator_version="opv:1",
        vector_space_version="vs:1",
        input_atom_ids=inputs,
        output_atom_ids=outputs,
        provenance_refs=(f"operator-source:{operator_id}",),
    )


def need(*, targets: tuple[str, ...] = ("d",), max_depth: int = 4, max_atoms: int = 4) -> WorldNeed:
    return WorldNeed(
        need_id="need:1",
        cycle_id="cycle:1",
        generation=4,
        vector_space_version="vs:1",
        start_atom_ids=("a",),
        target_atom_ids=targets,
        max_depth=max_depth,
        max_atoms=max_atoms,
        provenance_refs=("need-source:test",),
    )


class SparseWorldBasisTests(unittest.TestCase):
    def test_bounded_expansion_reconstructs_only_reachable_local_slice(self):
        result = materialize_world_slice(
            atoms=(atom("a"), atom("b"), atom("c"), atom("d"), atom("irrelevant")),
            operators=(
                op("op:ab", ("a",), ("b",)),
                op("op:bc", ("b",), ("c",)),
                op("op:cd", ("c",), ("d",)),
            ),
            activations=(),
            need=need(),
        )
        self.assertEqual(result.selected_atom_ids, ("a", "b", "c", "d"))
        self.assertNotIn("irrelevant", result.selected_atom_ids)
        self.assertEqual(result.unresolved_target_atom_ids, ())
        self.assertEqual(result.stopped_reason, "TARGETS_REACHED")
        self.assertEqual(result.depth_reached, 3)
        self.assertIn("NONCANONICAL", result.classification)
        self.assertEqual(result.as_dict()["truth_authority"], "NONE")

    def test_activation_is_explicit_routing_signal_and_ties_are_deterministic(self):
        atoms = (atom("a"), atom("b"), atom("c"), atom("d"))
        operators = (
            op("op:ab", ("a",), ("b",)),
            op("op:ac", ("a",), ("c",)),
            op("op:ad", ("a",), ("d",)),
        )
        limited = need(targets=(), max_depth=1, max_atoms=3)
        first = materialize_world_slice(
            atoms=atoms,
            operators=operators,
            activations=(
                AtomActivation(atom_id="d", activation_micros=900_000, provenance_refs=("signal:d",)),
                AtomActivation(atom_id="c", activation_micros=500_000, provenance_refs=("signal:c",)),
                AtomActivation(atom_id="b", activation_micros=500_000, provenance_refs=("signal:b",)),
            ),
            need=limited,
        )
        second = materialize_world_slice(
            atoms=tuple(reversed(atoms)),
            operators=tuple(reversed(operators)),
            activations=(
                AtomActivation(atom_id="b", activation_micros=500_000, provenance_refs=("signal:b",)),
                AtomActivation(atom_id="c", activation_micros=500_000, provenance_refs=("signal:c",)),
                AtomActivation(atom_id="d", activation_micros=900_000, provenance_refs=("signal:d",)),
            ),
            need=limited,
        )
        self.assertEqual(first.selected_atom_ids, ("a", "b", "d"))
        self.assertEqual(first.canonical_json(), second.canonical_json())
        self.assertEqual(first.sha256(), second.sha256())

    def test_not_computed_taint_propagates_through_downstream_dependencies(self):
        result = materialize_world_slice(
            atoms=(
                atom("a", state=KnowledgeState.NOT_COMPUTED),
                atom("b"),
                atom("c"),
                atom("safe"),
            ),
            operators=(
                op("op:ab", ("a",), ("b",)),
                op("op:bc", ("b",), ("c",)),
                op("op:asafe", ("safe",), ("c",)),
            ),
            activations=(),
            need=WorldNeed(
                need_id="need:taint",
                cycle_id="cycle:1",
                generation=4,
                vector_space_version="vs:1",
                start_atom_ids=("a",),
                target_atom_ids=("c",),
                max_depth=4,
                max_atoms=4,
                provenance_refs=("need-source:test",),
            ),
        )
        self.assertEqual(result.selected_atom_ids, ("a",))
        self.assertEqual(result.tainted_atom_ids, ("a", "b", "c"))
        self.assertEqual(result.unresolved_target_atom_ids, ("c",))

    def test_unknown_reference_and_version_or_generation_mismatch_fail_closed(self):
        with self.assertRaisesRegex(SparseWorldError, "unknown atoms"):
            materialize_world_slice(
                atoms=(atom("a"), atom("b")),
                operators=(op("op:bad", ("a",), ("missing",)),),
                activations=(),
                need=need(targets=(), max_depth=1, max_atoms=2),
            )
        with self.assertRaisesRegex(SparseWorldError, "vector_space_version mismatch"):
            materialize_world_slice(
                atoms=(atom("a"), atom("b", vector_space="vs:2")),
                operators=(),
                activations=(),
                need=need(targets=(), max_depth=1, max_atoms=2),
            )
        with self.assertRaisesRegex(SparseWorldError, "generation mismatch"):
            materialize_world_slice(
                atoms=(atom("a"), atom("b", generation=3)),
                operators=(),
                activations=(),
                need=need(targets=(), max_depth=1, max_atoms=2),
            )

    def test_duplicate_atom_operator_and_activation_identity_fail_closed(self):
        with self.assertRaisesRegex(SparseWorldError, "duplicate atom_id"):
            materialize_world_slice(
                atoms=(atom("a"), atom("a")),
                operators=(),
                activations=(),
                need=need(targets=(), max_depth=0, max_atoms=2),
            )
        with self.assertRaisesRegex(SparseWorldError, "duplicate operator_id"):
            materialize_world_slice(
                atoms=(atom("a"), atom("b"), atom("c")),
                operators=(
                    op("op:x", ("a",), ("b",)),
                    op("op:x", ("a",), ("c",)),
                ),
                activations=(),
                need=need(targets=(), max_depth=1, max_atoms=3),
            )
        with self.assertRaisesRegex(SparseWorldError, "duplicate activation atom_id"):
            materialize_world_slice(
                atoms=(atom("a"), atom("b")),
                operators=(),
                activations=(
                    AtomActivation(atom_id="b", activation_micros=1, provenance_refs=("s:1",)),
                    AtomActivation(atom_id="b", activation_micros=2, provenance_refs=("s:2",)),
                ),
                need=need(targets=(), max_depth=1, max_atoms=2),
            )

    def test_hard_bounds_stop_expansion_without_false_target_success(self):
        result = materialize_world_slice(
            atoms=(atom("a"), atom("b"), atom("c"), atom("d")),
            operators=(
                op("op:ab", ("a",), ("b",)),
                op("op:bc", ("b",), ("c",)),
                op("op:cd", ("c",), ("d",)),
            ),
            activations=(),
            need=need(max_depth=1, max_atoms=4),
        )
        self.assertEqual(result.selected_atom_ids, ("a", "b"))
        self.assertEqual(result.unresolved_target_atom_ids, ("d",))
        self.assertEqual(result.stopped_reason, "MAX_DEPTH_REACHED")

        result2 = materialize_world_slice(
            atoms=(atom("a"), atom("b"), atom("c"), atom("d")),
            operators=(
                op("op:ab", ("a",), ("b",)),
                op("op:ac", ("a",), ("c",)),
                op("op:ad", ("a",), ("d",)),
            ),
            activations=(),
            need=need(max_depth=2, max_atoms=2),
        )
        self.assertEqual(len(result2.selected_atom_ids), 2)
        self.assertEqual(result2.stopped_reason, "MAX_ATOMS_REACHED")

    def test_world_need_cannot_start_over_atom_budget(self):
        with self.assertRaisesRegex(SparseWorldError, "exceed max_atoms"):
            WorldNeed(
                need_id="need:bad",
                cycle_id="cycle:1",
                generation=4,
                vector_space_version="vs:1",
                start_atom_ids=("a", "b"),
                target_atom_ids=(),
                max_depth=1,
                max_atoms=1,
                provenance_refs=("source:test",),
            )

    def test_not_computed_and_unknown_cannot_smuggle_confidence(self):
        with self.assertRaisesRegex(SparseWorldError, "NOT_COMPUTED"):
            WorldAtom(
                atom_id="n",
                generation=4,
                vector_space_version="vs:1",
                vector=(0,),
                epistemic_origin=EpistemicOrigin.OBSERVED,
                knowledge_state=KnowledgeState.NOT_COMPUTED,
                provenance_refs=("source:test",),
                evidence_refs=("evidence:smuggled",),
                confidence_micros=None,
            )
        with self.assertRaisesRegex(SparseWorldError, "UNKNOWN"):
            WorldAtom(
                atom_id="u",
                generation=4,
                vector_space_version="vs:1",
                vector=(0,),
                epistemic_origin=EpistemicOrigin.INFERRED,
                knowledge_state=KnowledgeState.UNKNOWN,
                provenance_refs=("source:test",),
                confidence_micros=1,
            )

    def test_structures_are_frozen_and_authority_is_explicitly_none(self):
        item = atom("a")
        with self.assertRaises(FrozenInstanceError):
            item.atom_id = "mutated"  # type: ignore[misc]
        self.assertEqual(item.as_dict()["truth_authority"], "NONE")
        self.assertEqual(AtomActivation(
            atom_id="a", activation_micros=1, provenance_refs=("source:test",)
        ).classification, "CALLER_SUPPLIED_ROUTING_SIGNAL_NOT_TRUTH")


if __name__ == "__main__":
    unittest.main()
