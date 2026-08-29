import unittest

from frankenstein2.sparse_world_basis import EpistemicOrigin, KnowledgeState, WorldAtom, WorldOperator
from frankenstein2.world_maintenance import (
    AtomMaintenanceAction,
    MaintenanceEvidence,
    MaintenanceEvidenceClass,
    OperatorMaintenanceAction,
    WorldMaintenanceError,
    assimilate_atom,
    assess_operator,
)


def atom(atom_id: str, *, vector=(1, 2), generation=1, state=KnowledgeState.KNOWN, provenance=None):
    return WorldAtom(
        atom_id=atom_id,
        generation=generation,
        vector_space_version="space-v1",
        vector=vector,
        epistemic_origin=EpistemicOrigin.OBSERVED,
        knowledge_state=state,
        provenance_refs=provenance or (f"source:{atom_id}",),
        evidence_refs=(f"evidence:{atom_id}",) if state is KnowledgeState.KNOWN else (),
        confidence_micros=900_000 if state is KnowledgeState.KNOWN else None,
    )


def operator():
    return WorldOperator(
        operator_id="op:a-b",
        generation=1,
        operator_version="op-v1",
        vector_space_version="space-v1",
        input_atom_ids=("a",),
        output_atom_ids=("b",),
        provenance_refs=("operator-source",),
    )


def evidence(evidence_id: str, op: WorldOperator, cls: MaintenanceEvidenceClass, *, sha=None, generation=1):
    return MaintenanceEvidence(
        evidence_id=evidence_id,
        generation=generation,
        target_id=op.operator_id,
        target_sha256=sha or op.sha256(),
        evidence_class=cls,
        provenance_refs=(f"prov:{evidence_id}",),
    )


class AtomAssimilationTests(unittest.TestCase):
    def test_same_identity_same_digest_is_no_change(self):
        current = atom("a")
        result = assimilate_atom(
            incoming=current,
            existing_atoms=(current,),
            expected_generation=1,
            expected_vector_space_version="space-v1",
        )
        self.assertEqual(result.action, AtomMaintenanceAction.NO_CHANGE)
        self.assertFalse(result.as_dict()["mutation_performed"])
        self.assertEqual(result.as_dict()["truth_authority"], "NONE")

    def test_same_identity_different_content_preserves_conflict(self):
        result = assimilate_atom(
            incoming=atom("a", vector=(9, 9)),
            existing_atoms=(atom("a"),),
            expected_generation=1,
            expected_vector_space_version="space-v1",
        )
        self.assertEqual(result.action, AtomMaintenanceAction.CONFLICT_PRESERVED)
        self.assertEqual(result.conflicting_atom_ids, ("a",))

    def test_identity_independent_exact_content_duplicate_is_proposal_only(self):
        existing = atom("z", provenance=("shared-source",))
        incoming = atom("a", provenance=("shared-source",))
        result = assimilate_atom(
            incoming=incoming,
            existing_atoms=(existing,),
            expected_generation=1,
            expected_vector_space_version="space-v1",
        )
        self.assertEqual(result.action, AtomMaintenanceAction.EXACT_DUPLICATE_CANDIDATE)
        self.assertEqual(result.canonical_candidate_atom_id, "a")
        self.assertFalse(result.as_dict()["mutation_performed"])

    def test_new_atom_is_add_candidate_not_automatic_write(self):
        result = assimilate_atom(
            incoming=atom("new", vector=(3, 4)),
            existing_atoms=(atom("old"),),
            expected_generation=1,
            expected_vector_space_version="space-v1",
        )
        self.assertEqual(result.action, AtomMaintenanceAction.ADD_CANDIDATE)
        self.assertFalse(result.as_dict()["mutation_performed"])

    def test_generation_and_vector_space_mismatch_fail_closed(self):
        with self.assertRaisesRegex(WorldMaintenanceError, "generation mismatch"):
            assimilate_atom(
                incoming=atom("a", generation=2),
                existing_atoms=(),
                expected_generation=1,
                expected_vector_space_version="space-v1",
            )
        wrong_space = WorldAtom(
            atom_id="b", generation=1, vector_space_version="space-v2", vector=(1,),
            epistemic_origin=EpistemicOrigin.OBSERVED, knowledge_state=KnowledgeState.KNOWN,
            provenance_refs=("p",), evidence_refs=("e",), confidence_micros=1,
        )
        with self.assertRaisesRegex(WorldMaintenanceError, "vector_space_version mismatch"):
            assimilate_atom(
                incoming=wrong_space,
                existing_atoms=(),
                expected_generation=1,
                expected_vector_space_version="space-v1",
            )

    def test_existing_duplicate_identity_fails_closed(self):
        with self.assertRaisesRegex(WorldMaintenanceError, "duplicate atom_id"):
            assimilate_atom(
                incoming=atom("c", vector=(8, 8)),
                existing_atoms=(atom("a"), atom("a")),
                expected_generation=1,
                expected_vector_space_version="space-v1",
            )


class OperatorAssessmentTests(unittest.TestCase):
    def test_inferred_and_simulated_alone_never_promote(self):
        op = operator()
        result = assess_operator(
            operator=op,
            evidence=(
                evidence("i", op, MaintenanceEvidenceClass.INFERRED),
                evidence("s", op, MaintenanceEvidenceClass.SIMULATED),
            ),
            expected_generation=1,
            min_verified_support=1,
        )
        self.assertEqual(result.action, OperatorMaintenanceAction.HOLD_UNVERIFIED)
        self.assertEqual(result.verified_support_count, 0)
        self.assertFalse(result.as_dict()["mutation_performed"])

    def test_verified_support_threshold_yields_candidate_not_truth(self):
        op = operator()
        result = assess_operator(
            operator=op,
            evidence=(
                evidence("o", op, MaintenanceEvidenceClass.VERIFIED_OBSERVATION),
                evidence("m", op, MaintenanceEvidenceClass.VERIFIED_OUTCOME_MATCH),
            ),
            expected_generation=1,
            min_verified_support=2,
        )
        self.assertEqual(result.action, OperatorMaintenanceAction.PROMOTION_CANDIDATE)
        self.assertEqual(result.as_dict()["truth_authority"], "NONE")
        self.assertEqual(result.as_dict()["effect_authority"], "NONE")

    def test_verified_failure_yields_downgrade_candidate(self):
        op = operator()
        result = assess_operator(
            operator=op,
            evidence=(evidence("f", op, MaintenanceEvidenceClass.VERIFIED_OUTCOME_FAILURE),),
            expected_generation=1,
        )
        self.assertEqual(result.action, OperatorMaintenanceAction.DOWNGRADE_CANDIDATE)

    def test_support_plus_failure_preserves_conflict(self):
        op = operator()
        result = assess_operator(
            operator=op,
            evidence=(
                evidence("m", op, MaintenanceEvidenceClass.VERIFIED_OUTCOME_MATCH),
                evidence("f", op, MaintenanceEvidenceClass.VERIFIED_OUTCOME_FAILURE),
            ),
            expected_generation=1,
            min_verified_support=1,
        )
        self.assertEqual(result.action, OperatorMaintenanceAction.CONFLICT_PRESERVED)

    def test_forged_target_digest_fails_closed(self):
        op = operator()
        with self.assertRaisesRegex(WorldMaintenanceError, "target digest mismatch"):
            assess_operator(
                operator=op,
                evidence=(evidence("bad", op, MaintenanceEvidenceClass.VERIFIED_OUTCOME_MATCH, sha="0" * 64),),
                expected_generation=1,
            )

    def test_wrong_target_and_generation_fail_closed(self):
        op = operator()
        wrong_target = MaintenanceEvidence(
            evidence_id="bad-target", generation=1, target_id="op:other",
            target_sha256=op.sha256(), evidence_class=MaintenanceEvidenceClass.VERIFIED_OBSERVATION,
            provenance_refs=("p",),
        )
        with self.assertRaisesRegex(WorldMaintenanceError, "target_id mismatch"):
            assess_operator(operator=op, evidence=(wrong_target,), expected_generation=1)
        with self.assertRaisesRegex(WorldMaintenanceError, "evidence generation mismatch"):
            assess_operator(
                operator=op,
                evidence=(evidence("bad-generation", op, MaintenanceEvidenceClass.VERIFIED_OBSERVATION, generation=2),),
                expected_generation=1,
            )

    def test_duplicate_evidence_identity_fails_closed(self):
        op = operator()
        item = evidence("same", op, MaintenanceEvidenceClass.VERIFIED_OBSERVATION)
        with self.assertRaisesRegex(WorldMaintenanceError, "duplicate evidence_id"):
            assess_operator(operator=op, evidence=(item, item), expected_generation=1)

    def test_evidence_order_does_not_change_result_digest(self):
        op = operator()
        a = evidence("a", op, MaintenanceEvidenceClass.VERIFIED_OBSERVATION)
        b = evidence("b", op, MaintenanceEvidenceClass.VERIFIED_OUTCOME_MATCH)
        first = assess_operator(operator=op, evidence=(a, b), expected_generation=1)
        second = assess_operator(operator=op, evidence=(b, a), expected_generation=1)
        self.assertEqual(first.sha256(), second.sha256())
        self.assertEqual(first.evidence_ids, ("a", "b"))


if __name__ == "__main__":
    unittest.main()
