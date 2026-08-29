import unittest

from frankenstein2.sparse_world_basis import KnowledgeState, WorldSlice
from frankenstein2.visual_need import VisualNeedError, VisualReason, plan_visual_need
from frankenstein2.world_multiview import ViewAtomState, WorldView, compare_world_views


def make_slice(
    tag,
    selected=("x",),
    unresolved=("u",),
    *,
    cycle="cycle-1",
    generation=1,
    vector="vs-1",
):
    digest = (tag * 64)[:64]
    return WorldSlice(
        slice_id="world-slice:" + digest[:24],
        need_id="need-" + tag,
        cycle_id=cycle,
        generation=generation,
        vector_space_version=vector,
        selected_atom_ids=tuple(selected),
        selected_operator_ids=(),
        unresolved_target_atom_ids=tuple(unresolved),
        tainted_atom_ids=(),
        depth_reached=0,
        stopped_reason="NO_EXPANSION_AVAILABLE",
        evidence_refs=("slice:" + tag,),
        provenance_digest=digest,
    )


def view(view_id, world_slice, states):
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


class VisualNeedTests(unittest.TestCase):
    def test_unresolved_visualizable_target_emits_candidate_only(self):
        world_slice = make_slice("a", unresolved=("u", "not-visual"))
        need = plan_visual_need(
            world_slice=world_slice,
            visualizable_atom_ids=("u",),
            provenance_refs=("caller",),
        )
        self.assertIsNotNone(need)
        self.assertEqual(tuple(target.atom_id for target in need.targets), ("u",))
        self.assertEqual(need.targets[0].reasons, (VisualReason.UNRESOLVED_TARGET,))
        self.assertEqual(need.as_dict()["perception_execution_authority"], "NONE")
        self.assertEqual(need.as_dict()["truth_authority"], "NONE")

    def test_no_eligible_visual_target_returns_none(self):
        world_slice = make_slice("a", unresolved=("u",))
        self.assertIsNone(
            plan_visual_need(
                world_slice=world_slice,
                visualizable_atom_ids=("x",),
                provenance_refs=("caller",),
            )
        )

    def test_overlay_disagreement_can_create_relook_target(self):
        first = make_slice("a", selected=("x",), unresolved=())
        second = make_slice("b", selected=("x",), unresolved=())
        overlay = compare_world_views(
            views=(
                view("a", first, {"x": KnowledgeState.KNOWN}),
                view("b", second, {"x": KnowledgeState.CONFLICT}),
            )
        )
        need = plan_visual_need(
            world_slice=first,
            overlay=overlay,
            visualizable_atom_ids=("x",),
            provenance_refs=("caller",),
        )
        self.assertEqual(
            need.targets[0].reasons,
            (VisualReason.MULTIVIEW_DISAGREEMENT,),
        )
        self.assertEqual(need.source_overlay_id, overlay.overlay_id)
        self.assertTrue(
            any(
                ref.startswith("world-multiview-sha256:")
                for ref in need.provenance_refs
            )
        )

    def test_unresolved_and_disagreement_reasons_are_preserved_together(self):
        first = make_slice("a", selected=("x",), unresolved=("x",))
        second = make_slice("b", selected=("x",), unresolved=())
        overlay = compare_world_views(
            views=(
                view("a", first, {"x": KnowledgeState.UNKNOWN}),
                view("b", second, {"x": KnowledgeState.KNOWN}),
            )
        )
        need = plan_visual_need(
            world_slice=first,
            overlay=overlay,
            visualizable_atom_ids=("x",),
            provenance_refs=("caller",),
        )
        self.assertEqual(
            set(need.targets[0].reasons),
            {VisualReason.UNRESOLVED_TARGET, VisualReason.MULTIVIEW_DISAGREEMENT},
        )

    def test_visualizable_input_order_is_canonical_and_bounded(self):
        world_slice = make_slice("a", unresolved=("c", "a", "b"))
        first = plan_visual_need(
            world_slice=world_slice,
            visualizable_atom_ids=("c", "b", "a"),
            max_targets=2,
            provenance_refs=("caller",),
        )
        second = plan_visual_need(
            world_slice=world_slice,
            visualizable_atom_ids=("a", "b", "c"),
            max_targets=2,
            provenance_refs=("caller",),
        )
        self.assertEqual(first.as_dict(), second.as_dict())
        self.assertEqual(tuple(target.atom_id for target in first.targets), ("a", "b"))

    def test_rejects_nonpositive_max_targets(self):
        world_slice = make_slice("a")
        for value in (0, -1, True):
            with self.assertRaisesRegex(VisualNeedError, "max_targets"):
                plan_visual_need(
                    world_slice=world_slice,
                    visualizable_atom_ids=("u",),
                    max_targets=value,
                    provenance_refs=("caller",),
                )

    def test_rejects_overlay_cycle_generation_vector_mismatch(self):
        base = make_slice("a", selected=("x",), unresolved=())
        cases = (
            ({"cycle": "cycle-2"}, "cycle_id"),
            ({"generation": 2}, "generation"),
            ({"vector": "vs-2"}, "vector_space_version"),
        )
        for kwargs, match in cases:
            other = make_slice("b", selected=("x",), unresolved=(), **kwargs)
            another = make_slice("c", selected=("x",), unresolved=(), **kwargs)
            overlay = compare_world_views(
                views=(
                    view("b", other, {"x": KnowledgeState.KNOWN}),
                    view("c", another, {"x": KnowledgeState.CONFLICT}),
                )
            )
            with self.assertRaisesRegex(VisualNeedError, match):
                plan_visual_need(
                    world_slice=base,
                    overlay=overlay,
                    visualizable_atom_ids=("x",),
                    provenance_refs=("caller",),
                )

    def test_rejects_overlay_that_does_not_reference_source_slice(self):
        source = make_slice("a", selected=("x",), unresolved=())
        second = make_slice("b", selected=("x",), unresolved=())
        third = make_slice("c", selected=("x",), unresolved=())
        overlay = compare_world_views(
            views=(
                view("b", second, {"x": KnowledgeState.KNOWN}),
                view("c", third, {"x": KnowledgeState.CONFLICT}),
            )
        )
        with self.assertRaisesRegex(VisualNeedError, "exact source WorldSlice"):
            plan_visual_need(
                world_slice=source,
                overlay=overlay,
                visualizable_atom_ids=("x",),
                provenance_refs=("caller",),
            )

    def test_rejects_forged_slice_identity(self):
        raw = make_slice("a")
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
        with self.assertRaisesRegex(VisualNeedError, "binding mismatch"):
            plan_visual_need(
                world_slice=forged,
                visualizable_atom_ids=("u",),
                provenance_refs=("caller",),
            )


if __name__ == "__main__":
    unittest.main()
