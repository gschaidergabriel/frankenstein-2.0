#!/usr/bin/env python3
"""Independent numeric-domain falsifier for F2-WP-400 G1.

CANDIDATE_FALSIFIER only. This test does not own or mutate the canonical WP400
implementation and does not mint runtime, GRID10, GWT, training, or whole-system credit.
"""
from __future__ import annotations

import math
import unittest

from frankenstein2.sparse_world_basis import AtomActivation, SparseWorldError, WorldAtom, EpistemicOrigin, KnowledgeState


class SparseWorldNumericDomainFalsifier(unittest.TestCase):
    def test_activation_rejects_non_integer_nonfinite_and_bool_values(self):
        bad_values = (True, False, float("nan"), float("inf"), float("-inf"), 0.0, -0.0)
        for value in bad_values:
            with self.subTest(value=repr(value)):
                with self.assertRaises(SparseWorldError):
                    AtomActivation(
                        atom_id="a",
                        activation_micros=value,  # type: ignore[arg-type]
                        provenance_refs=("signal:test",),
                    )

    def test_vector_rejects_noninteger_nonfinite_bool_and_signed_zero_values(self):
        bad_values = (True, False, float("nan"), float("inf"), float("-inf"), 0.0, -0.0)
        for value in bad_values:
            with self.subTest(value=repr(value)):
                with self.assertRaises(SparseWorldError):
                    WorldAtom(
                        atom_id="a",
                        generation=1,
                        vector_space_version="vs:1",
                        vector=(value,),  # type: ignore[arg-type]
                        epistemic_origin=EpistemicOrigin.OBSERVED,
                        knowledge_state=KnowledgeState.KNOWN,
                        provenance_refs=("source:test",),
                        evidence_refs=("evidence:test",),
                        confidence_micros=1,
                    )

    def test_integer_micro_domain_has_no_nonfinite_values(self):
        for value in (0, 1, 500_000, 1_000_000):
            item = AtomActivation(
                atom_id=f"a:{value}",
                activation_micros=value,
                provenance_refs=("signal:test",),
            )
            self.assertIsInstance(item.activation_micros, int)
            self.assertTrue(math.isfinite(item.activation_micros))


if __name__ == "__main__":
    unittest.main()
