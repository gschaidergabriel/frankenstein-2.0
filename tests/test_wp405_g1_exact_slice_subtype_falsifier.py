import unittest

from frankenstein2.sparse_world_basis import KnowledgeState, WorldSlice
from frankenstein2.world_multiview import (
    MultiViewError,
    ViewAtomState,
    WorldView,
    compare_world_views,
)


class SliceDigestOne(WorldSlice):
    def sha256(self) -> str:
        return "1" * 64


class SliceDigestTwo(WorldSlice):
    def sha256(self) -> str:
        return "2" * 64


def make_slice(slice_type):
    digest = "a" * 64
    return slice_type(
        slice_id="world-slice:" + digest[:24],
        need_id="need:wp405-subtype-falsifier",
        cycle_id="cycle:wp405-subtype-falsifier",
        generation=7,
        vector_space_version="vs:wp405-subtype-falsifier",
        selected_atom_ids=("atom:x",),
        selected_operator_ids=(),
        unresolved_target_atom_ids=(),
        tainted_atom_ids=(),
        depth_reached=0,
        stopped_reason="BOUNDED_FALSIFIER",
        evidence_refs=("evidence:wp405-subtype-falsifier",),
        provenance_digest=digest,
    )


def make_view(view_id, world_slice, state):
    return WorldView(
        view_id=view_id,
        world_slice=world_slice,
        atom_states=(
            ViewAtomState(
                atom_id="atom:x",
                knowledge_state=state,
                provenance_refs=(f"{view_id}:atom:x",),
            ),
        ),
        provenance_refs=(f"view:{view_id}",),
    )


class WP405Generation1ExactSliceSubtypeFalsifier(unittest.TestCase):
    def test_canonically_identical_worldslice_subtypes_cannot_bypass_duplicate_guard(self):
        first_slice = make_slice(SliceDigestOne)
        second_slice = make_slice(SliceDigestTwo)

        # Exact canonical WorldSlice contents are identical when evaluated through
        # the base implementation. Only attacker-controlled subtype dispatch differs.
        self.assertEqual(first_slice.canonical_json(), second_slice.canonical_json())
        self.assertEqual(WorldSlice.sha256(first_slice), WorldSlice.sha256(second_slice))
        self.assertNotEqual(first_slice.sha256(), second_slice.sha256())

        first_view = make_view("view:a", first_slice, KnowledgeState.KNOWN)
        second_view = make_view("view:b", second_slice, KnowledgeState.UNKNOWN)

        with self.assertRaisesRegex(MultiViewError, "duplicate the same exact WorldSlice"):
            compare_world_views(views=(first_view, second_view))


if __name__ == "__main__":
    unittest.main(verbosity=2)
