from __future__ import annotations

import unittest

from frankenstein2.process_distillation import (
    OUTCOME_REPORTED_FAILURE,
    OUTCOME_REPORTED_SUCCESS,
    OUTCOME_UNKNOWN,
    PROCESS_PATTERN_SCHEMA,
    ProcessDistillationError,
    ProcessEvidence,
    ProcessPatternCandidate,
    distill_process,
)


class ProcessDistillationTests(unittest.TestCase):
    def evidence(
        self,
        *,
        generation: int = 1,
        outcome: str = OUTCOME_REPORTED_SUCCESS,
        steps=("step:observe", "step:test", "step:verify"),
    ) -> ProcessEvidence:
        return ProcessEvidence.create(
            process_id="process:wp304:test",
            generation=generation,
            step_refs=steps,
            outcome_classification=outcome,
            outcome_refs=("receipt:outcome:1",),
            falsifier_refs=("test:falsifier:1",),
            failure_signature_refs=("failure:signature:known",),
            transfer_condition_refs=("transfer:condition:explicit",),
            provenance_refs=("source:fixture", "claim:F2-WP-304-G1"),
        )

    def test_same_explicit_evidence_is_deterministic(self) -> None:
        left = distill_process(self.evidence(), candidate_id="candidate:1")
        right = distill_process(self.evidence(), candidate_id="candidate:1")
        self.assertEqual(left.canonical_json(), right.canonical_json())
        self.assertEqual(left.sha256(), right.sha256())
        self.assertEqual(left.depth, 0)
        self.assertEqual(left.parent_candidate_sha256, ())
        self.assertIn("NOT_FACT", left.classification)

    def test_step_order_is_preserved_not_semantically_rewritten(self) -> None:
        forward = distill_process(
            self.evidence(steps=("step:a", "step:b")), candidate_id="candidate:forward"
        )
        reverse = distill_process(
            self.evidence(steps=("step:b", "step:a")), candidate_id="candidate:reverse"
        )
        self.assertEqual(forward.step_refs, ("step:a", "step:b"))
        self.assertEqual(reverse.step_refs, ("step:b", "step:a"))
        self.assertNotEqual(forward.process_evidence_sha256, reverse.process_evidence_sha256)

    def test_declared_outcome_is_preserved_not_promoted(self) -> None:
        success = distill_process(
            self.evidence(outcome=OUTCOME_REPORTED_SUCCESS), candidate_id="candidate:success"
        )
        failure = distill_process(
            self.evidence(outcome=OUTCOME_REPORTED_FAILURE), candidate_id="candidate:failure"
        )
        unknown = distill_process(
            self.evidence(outcome=OUTCOME_UNKNOWN), candidate_id="candidate:unknown"
        )
        self.assertEqual(success.outcome_classification, OUTCOME_REPORTED_SUCCESS)
        self.assertEqual(failure.outcome_classification, OUTCOME_REPORTED_FAILURE)
        self.assertEqual(unknown.outcome_classification, OUTCOME_UNKNOWN)
        self.assertEqual(success.classification, failure.classification)
        self.assertEqual(failure.classification, unknown.classification)

    def test_empty_required_evidence_fails_closed(self) -> None:
        with self.assertRaises(ProcessDistillationError):
            ProcessEvidence.create(
                process_id="process:empty",
                generation=0,
                step_refs=(),
                outcome_classification=OUTCOME_UNKNOWN,
                outcome_refs=("receipt:unknown",),
                provenance_refs=("source:fixture",),
            )
        with self.assertRaises(ProcessDistillationError):
            ProcessEvidence.create(
                process_id="process:empty",
                generation=0,
                step_refs=("step:one",),
                outcome_classification=OUTCOME_UNKNOWN,
                outcome_refs=(),
                provenance_refs=("source:fixture",),
            )
        with self.assertRaises(ProcessDistillationError):
            ProcessEvidence.create(
                process_id="process:empty",
                generation=0,
                step_refs=("step:one",),
                outcome_classification=OUTCOME_UNKNOWN,
                outcome_refs=("receipt:unknown",),
                provenance_refs=(),
            )

    def test_unsupported_outcome_fails_closed(self) -> None:
        with self.assertRaises(ProcessDistillationError):
            self.evidence(outcome="VERIFIED_FACT")

    def test_reference_sets_are_canonical_but_steps_are_ordered(self) -> None:
        one = ProcessEvidence.create(
            process_id="process:canonical",
            generation=2,
            step_refs=("step:1", "step:2"),
            outcome_classification=OUTCOME_UNKNOWN,
            outcome_refs=("outcome:b", "outcome:a"),
            falsifier_refs=("falsifier:b", "falsifier:a"),
            provenance_refs=("source:b", "source:a"),
        )
        two = ProcessEvidence.create(
            process_id="process:canonical",
            generation=2,
            step_refs=("step:1", "step:2"),
            outcome_classification=OUTCOME_UNKNOWN,
            outcome_refs=("outcome:a", "outcome:b"),
            falsifier_refs=("falsifier:a", "falsifier:b"),
            provenance_refs=("source:a", "source:b"),
        )
        self.assertEqual(one.sha256(), two.sha256())

    def test_recursive_candidate_binds_exact_parent_digest_and_ancestry(self) -> None:
        root = distill_process(
            self.evidence(generation=0), candidate_id="candidate:root"
        )
        child = distill_process(
            self.evidence(generation=1), candidate_id="candidate:child", parents=(root,)
        )
        grandchild = distill_process(
            self.evidence(generation=2), candidate_id="candidate:grandchild", parents=(child,)
        )
        self.assertEqual(child.depth, 1)
        self.assertEqual(child.parent_candidate_sha256, (root.sha256(),))
        self.assertIn(root.sha256(), grandchild.ancestry_sha256)
        self.assertIn(child.sha256(), grandchild.ancestry_sha256)
        self.assertEqual(grandchild.depth, 2)

    def test_parent_process_and_generation_fences_fail_closed(self) -> None:
        root = distill_process(
            self.evidence(generation=2), candidate_id="candidate:root"
        )
        with self.assertRaises(ProcessDistillationError):
            distill_process(
                self.evidence(generation=1), candidate_id="candidate:older", parents=(root,)
            )

        other = ProcessEvidence.create(
            process_id="process:other",
            generation=2,
            step_refs=("step:x",),
            outcome_classification=OUTCOME_UNKNOWN,
            outcome_refs=("outcome:x",),
            provenance_refs=("source:x",),
        )
        with self.assertRaises(ProcessDistillationError):
            distill_process(other, candidate_id="candidate:other", parents=(root,))

    def test_duplicate_parent_or_self_reference_fails_closed(self) -> None:
        root = distill_process(
            self.evidence(generation=0), candidate_id="candidate:root"
        )
        with self.assertRaises(ProcessDistillationError):
            distill_process(
                self.evidence(generation=1),
                candidate_id="candidate:child",
                parents=(root, root),
            )
        with self.assertRaises(ProcessDistillationError):
            distill_process(
                self.evidence(generation=1),
                candidate_id="candidate:root",
                parents=(root,),
            )

    def test_recursive_depth_is_bounded(self) -> None:
        parent = distill_process(
            self.evidence(generation=0), candidate_id="candidate:d0"
        )
        for depth in range(1, 9):
            parent = distill_process(
                self.evidence(generation=depth),
                candidate_id=f"candidate:d{depth}",
                parents=(parent,),
            )
            self.assertEqual(parent.depth, depth)
        with self.assertRaises(ProcessDistillationError):
            distill_process(
                self.evidence(generation=9),
                candidate_id="candidate:d9",
                parents=(parent,),
            )

    def test_pattern_cannot_be_forged_through_public_constructor(self) -> None:
        evidence = self.evidence()
        with self.assertRaises(ProcessDistillationError):
            ProcessPatternCandidate(
                schema=PROCESS_PATTERN_SCHEMA,
                candidate_id="candidate:forged",
                process_id=evidence.process_id,
                generation=evidence.generation,
                process_evidence_sha256=evidence.sha256(),
                step_refs=evidence.step_refs,
                outcome_classification=evidence.outcome_classification,
                outcome_refs=evidence.outcome_refs,
                falsifier_refs=evidence.falsifier_refs,
                failure_signature_refs=evidence.failure_signature_refs,
                transfer_condition_refs=evidence.transfer_condition_refs,
                provenance_refs=evidence.provenance_refs,
                parent_candidate_sha256=(),
                ancestry_sha256=(),
                depth=0,
                classification="PROCESS_PATTERN_CANDIDATE_NOT_FACT_METHOD_VALIDATION_TRANSFER_OR_AUTHORITY",
            )


if __name__ == "__main__":
    unittest.main()
