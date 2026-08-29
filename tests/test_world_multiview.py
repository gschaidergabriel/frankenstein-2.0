import unittest

from frankenstein2.sparse_world_basis import KnowledgeState, WorldSlice
from frankenstein2.world_multiview import (
    AtomOverlayStatus,
    MultiViewError,
    ViewAtomState,
    WorldView,
    compare_world_views,
)


def make_slice(tag, atoms, *, cycle="cycle-1", generation=1, vector="vs-1"):
    digest = (tag * 64)[:64]
    return WorldSlice(
        slice_id="world-slice:" + digest[:24],
        need_id="need-" + tag,
        cycle_id=cycle,
        generation=generation,
        vector_space_version=vector,
        selected_atom_ids=tuple(sorted(atoms)),
        selected_operator_ids=(),
        unresolved_target_atom_ids=(),
        tainted_atom_ids=(),
        depth_reached=0,
        stopped_reason="NO_EXPANSION_AVAILABLE",
        evidence_refs=("slice:" + tag,),
        provenance_digest=digest,
    )


def make_view(view_id, tag, states, **slice_kwargs):
    world_slice = make_slice(tag, states, **slice_kwargs)
    return WorldView(
        view_id=view_id,
        world_slice=world_slice,
        atom_states=tuple(
            ViewAtomState(
                atom_id=atom_id,
                knowledge_state=state,
                provenance_refs=(f"{view_id}:{atom_id}",),
            )
            for atom_id, state in states.items()
        ),
        provenance_refs=("view:" + view_id,),
    )


def overlay_map(result):
    return {item.atom_id: item for item in result.atom_overlays}


class WorldMultiViewTests(unittest.TestCase):
    def test_preserves_agreement_disagreement_and_view_only_without_winner(self):
        a = make_view("a", "a", {"x": KnowledgeState.KNOWN, "y": KnowledgeState.UNKNOWN})
        b = make_view(
            "b",
            "b",
            {
                "x": KnowledgeState.KNOWN,
                "y": KnowledgeState.CONFLICT,
                "z": KnowledgeState.NOT_COMPUTED,
            },
        )
        result = compare_world_views(views=(a, b))
        items = overlay_map(result)
        self.assertIs(items["x"].status, AtomOverlayStatus.FULL_AGREEMENT)
        self.assertIs(items["y"].status, AtomOverlayStatus.FULL_DISAGREEMENT)
        self.assertIs(items["z"].status, AtomOverlayStatus.VIEW_ONLY)
        self.assertEqual(result.disagreement_atom_ids, ("y",))
        self.assertEqual(result.view_only_atom_ids, ("z",))
        self.assertIsNone(result.as_dict()["winner_view_id"])
        self.assertEqual(result.as_dict()["truth_authority"], "NONE")

    def test_three_view_partial_overlap_is_explicit(self):
        a = make_view("a", "a", {"x": KnowledgeState.UNKNOWN, "p": KnowledgeState.KNOWN})
        b = make_view("b", "b", {"x": KnowledgeState.UNKNOWN, "p": KnowledgeState.CONFLICT})
        c = make_view("c", "c", {"q": KnowledgeState.KNOWN})
        items = overlay_map(compare_world_views(views=(a, b, c)))
        self.assertIs(items["x"].status, AtomOverlayStatus.PARTIAL_AGREEMENT)
        self.assertIs(items["p"].status, AtomOverlayStatus.PARTIAL_DISAGREEMENT)
        self.assertIs(items["q"].status, AtomOverlayStatus.VIEW_ONLY)

    def test_unknown_conflict_not_computed_remain_distinct(self):
        a = make_view("a", "a", {"x": KnowledgeState.UNKNOWN})
        b = make_view("b", "b", {"x": KnowledgeState.CONFLICT})
        c = make_view("c", "c", {"x": KnowledgeState.NOT_COMPUTED})
        item = compare_world_views(views=(a, b, c)).atom_overlays[0]
        self.assertEqual(
            [state.value for _, state in item.states_by_view],
            ["UNKNOWN", "CONFLICT", "NOT_COMPUTED"],
        )
        self.assertIs(item.status, AtomOverlayStatus.FULL_DISAGREEMENT)

    def test_view_input_order_does_not_change_result(self):
        a = make_view("a", "a", {"x": KnowledgeState.KNOWN})
        b = make_view("b", "b", {"x": KnowledgeState.UNKNOWN})
        forward = compare_world_views(views=(a, b))
        reverse = compare_world_views(views=(b, a))
        self.assertEqual(forward.as_dict(), reverse.as_dict())
        self.assertEqual(forward.sha256(), reverse.sha256())

    def test_requires_two_views(self):
        a = make_view("a", "a", {"x": KnowledgeState.KNOWN})
        with self.assertRaisesRegex(MultiViewError, "at least two"):
            compare_world_views(views=(a,))

    def test_rejects_duplicate_view_id(self):
        a = make_view("same", "a", {"x": KnowledgeState.KNOWN})
        b = make_view("same", "b", {"x": KnowledgeState.KNOWN})
        with self.assertRaisesRegex(MultiViewError, "repeat view_id"):
            compare_world_views(views=(a, b))

    def test_rejects_duplicate_exact_slice(self):
        a = make_view("a", "a", {"x": KnowledgeState.KNOWN})
        b = WorldView(
            view_id="b",
            world_slice=a.world_slice,
            atom_states=(
                ViewAtomState(
                    atom_id="x",
                    knowledge_state=KnowledgeState.UNKNOWN,
                    provenance_refs=("b:x",),
                ),
            ),
            provenance_refs=("view:b",),
        )
        with self.assertRaisesRegex(MultiViewError, "duplicate the same exact WorldSlice"):
            compare_world_views(views=(a, b))

    def test_rejects_cycle_generation_and_vector_mismatch(self):
        a = make_view("a", "a", {"x": KnowledgeState.KNOWN})
        with self.assertRaisesRegex(MultiViewError, "cycle_id"):
            compare_world_views(
                views=(
                    a,
                    make_view("b", "b", {"x": KnowledgeState.KNOWN}, cycle="cycle-2"),
                )
            )
        with self.assertRaisesRegex(MultiViewError, "generation"):
            compare_world_views(
                views=(
                    a,
                    make_view("b", "b", {"x": KnowledgeState.KNOWN}, generation=2),
                )
            )
        with self.assertRaisesRegex(MultiViewError, "vector_space_version"):
            compare_world_views(
                views=(
                    a,
                    make_view("b", "b", {"x": KnowledgeState.KNOWN}, vector="vs-2"),
                )
            )

    def test_world_view_requires_exact_selected_atom_coverage(self):
        world_slice = make_slice("a", {"x", "y"})
        with self.assertRaisesRegex(MultiViewError, "exactly cover"):
            WorldView(
                view_id="a",
                world_slice=world_slice,
                atom_states=(
                    ViewAtomState(
                        atom_id="x",
                        knowledge_state=KnowledgeState.KNOWN,
                        provenance_refs=("x",),
                    ),
                ),
                provenance_refs=("view:a",),
            )
        with self.assertRaisesRegex(MultiViewError, "exactly cover"):
            WorldView(
                view_id="a",
                world_slice=world_slice,
                atom_states=(
                    ViewAtomState(
                        atom_id="x",
                        knowledge_state=KnowledgeState.KNOWN,
                        provenance_refs=("x",),
                    ),
                    ViewAtomState(
                        atom_id="y",
                        knowledge_state=KnowledgeState.KNOWN,
                        provenance_refs=("y",),
                    ),
                    ViewAtomState(
                        atom_id="z",
                        knowledge_state=KnowledgeState.KNOWN,
                        provenance_refs=("z",),
                    ),
                ),
                provenance_refs=("view:a",),
            )

    def test_rejects_forged_slice_id_digest_binding(self):
        raw = make_slice("a", {"x"})
        forged = WorldSlice(
            slice_id="world-slice:" + "b" * 24,
            need_id=raw.need_id,
            cycle_id=raw.cycle_id,
            generation=raw.generation,
            vector_space_version=raw.vector_space_version,
            selected_atom_ids=raw.selected_atom_ids,
            selected_operator_ids=raw.selected_operator_ids,
            unresolved_target_atom_ids=raw.unresolved_target_atom_ids,
            tainted_atom_ids=raw.tainted_atom_ids,
            depth_reached=raw.depth_reached,
            stopped_reason=raw.stopped_reason,
            evidence_refs=raw.evidence_refs,
            provenance_digest=raw.provenance_digest,
        )
        with self.assertRaisesRegex(MultiViewError, "binding mismatch"):
            WorldView(
                view_id="a",
                world_slice=forged,
                atom_states=(
                    ViewAtomState(
                        atom_id="x",
                        knowledge_state=KnowledgeState.KNOWN,
                        provenance_refs=("x",),
                    ),
                ),
                provenance_refs=("view:a",),
            )

    def test_output_binds_slice_and_observation_provenance(self):
        a = make_view("a", "a", {"x": KnowledgeState.KNOWN})
        b = make_view("b", "b", {"x": KnowledgeState.KNOWN})
        result = compare_world_views(views=(a, b))
        self.assertIn("view:a", result.provenance_refs)
        self.assertIn("a:x", result.provenance_refs)
        self.assertTrue(
            any(ref.startswith("world-slice-sha256:") for ref in result.provenance_refs)
        )
        self.assertEqual(
            result.overlay_id,
            "world-multiview:" + result.provenance_digest[:24],
        )


if __name__ == "__main__":
    unittest.main()
