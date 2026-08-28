from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import unittest

from frankenstein2.epistemic_records import (
    AUTHORITY_SCOPE,
    EPISTEMIC_RECORD_SCHEMA,
    INFERRED_HYPOTHESIS,
    NEGATIVE_RESULT,
    OBSERVED_EVIDENCE,
    RETRIEVAL_PRIOR,
    UNKNOWN,
    EpistemicRecord,
    EpistemicRecordError,
    create_epistemic_record,
    validate_epistemic_record,
)


PAYLOAD_SHA = "1" * 64
PARENT_SHA = "2" * 64


def make_record(
    *,
    classification: str = OBSERVED_EVIDENCE,
    generation: int = 0,
    parent_record_sha256: str | None = None,
):
    return create_epistemic_record(
        record_id="record:alpha",
        subject_ref="subject:widget",
        generation=generation,
        payload_ref="payload:opaque:alpha",
        payload_sha256=PAYLOAD_SHA,
        provenance_refs=("source:z", "source:a"),
        support_refs=("evidence:2", "evidence:1"),
        counterevidence_refs=("counter:1",),
        classification=classification,
        parent_record_sha256=parent_record_sha256,
    )


class EpistemicRecordTests(unittest.TestCase):
    def test_all_declared_classifications_construct_without_authority_promotion(self):
        for classification in (
            OBSERVED_EVIDENCE,
            INFERRED_HYPOTHESIS,
            RETRIEVAL_PRIOR,
            NEGATIVE_RESULT,
            UNKNOWN,
        ):
            with self.subTest(classification=classification):
                record = make_record(classification=classification)
                self.assertEqual(record.classification, classification)
                self.assertEqual(record.authority_scope, AUTHORITY_SCOPE)
                self.assertEqual(record.schema, EPISTEMIC_RECORD_SCHEMA)
                self.assertIs(validate_epistemic_record(record), record)

    def test_identity_is_deterministic_and_refs_are_canonicalized(self):
        record_a = make_record()
        record_b = create_epistemic_record(
            record_id="record:alpha",
            subject_ref="subject:widget",
            generation=0,
            payload_ref="payload:opaque:alpha",
            payload_sha256=PAYLOAD_SHA,
            provenance_refs=("source:a", "source:z"),
            support_refs=("evidence:1", "evidence:2"),
            counterevidence_refs=("counter:1",),
            classification=OBSERVED_EVIDENCE,
        )
        self.assertEqual(record_a.identity_sha256, record_b.identity_sha256)
        self.assertEqual(record_a.provenance_refs, ("source:a", "source:z"))
        self.assertEqual(record_a.support_refs, ("evidence:1", "evidence:2"))
        self.assertEqual(record_a.sha256(), record_a.identity_sha256)

    def test_frozen_record_rejects_normal_mutation(self):
        record = make_record()
        with self.assertRaises(FrozenInstanceError):
            record.classification = UNKNOWN  # type: ignore[misc]

    def test_post_construction_relabel_fails_re_admission(self):
        record = make_record(classification=RETRIEVAL_PRIOR)
        object.__setattr__(record, "classification", OBSERVED_EVIDENCE)
        with self.assertRaisesRegex(
            EpistemicRecordError, "identity digest mismatch"
        ):
            validate_epistemic_record(record)

    def test_post_construction_provenance_mutation_fails_re_admission(self):
        record = make_record()
        object.__setattr__(record, "provenance_refs", ("source:forged",))
        with self.assertRaisesRegex(
            EpistemicRecordError, "identity digest mismatch"
        ):
            validate_epistemic_record(record)

    def test_post_construction_authority_scope_mutation_fails_closed(self):
        record = make_record()
        object.__setattr__(record, "authority_scope", "WORLD_TRUTH")
        with self.assertRaisesRegex(
            EpistemicRecordError, "authority scope mismatch"
        ):
            validate_epistemic_record(record)

    def test_dataclasses_replace_cannot_relabel_record(self):
        record = make_record(classification=INFERRED_HYPOTHESIS)
        with self.assertRaisesRegex(
            EpistemicRecordError,
            "must be created through create_epistemic_record",
        ):
            replace(record, classification=OBSERVED_EVIDENCE)

    def test_direct_constructor_is_not_an_admission_path(self):
        with self.assertRaisesRegex(
            EpistemicRecordError,
            "must be created through create_epistemic_record",
        ):
            EpistemicRecord(
                schema=EPISTEMIC_RECORD_SCHEMA,
                record_id="record:direct",
                subject_ref="subject:widget",
                generation=0,
                payload_ref="payload:direct",
                payload_sha256=PAYLOAD_SHA,
                provenance_refs=("source:1",),
                support_refs=("evidence:1",),
                counterevidence_refs=(),
                classification=OBSERVED_EVIDENCE,
                parent_record_sha256=None,
                authority_scope=AUTHORITY_SCOPE,
                identity_sha256="3" * 64,
            )

    def test_unknown_is_first_class_and_does_not_become_false(self):
        record = make_record(classification=UNKNOWN)
        self.assertEqual(record.classification, UNKNOWN)
        self.assertNotEqual(record.classification, NEGATIVE_RESULT)
        self.assertIn("NOT_CANONICAL_TRUTH", record.authority_scope)

    def test_retrieval_prior_is_not_observation(self):
        prior = make_record(classification=RETRIEVAL_PRIOR)
        observed = make_record(classification=OBSERVED_EVIDENCE)
        self.assertNotEqual(prior.identity_sha256, observed.identity_sha256)
        self.assertEqual(prior.payload_ref, observed.payload_ref)
        self.assertEqual(prior.payload_sha256, observed.payload_sha256)

    def test_missing_provenance_fails_closed(self):
        with self.assertRaisesRegex(
            EpistemicRecordError, "provenance_ref must contain at least one"
        ):
            create_epistemic_record(
                record_id="record:no-provenance",
                subject_ref="subject:widget",
                generation=0,
                payload_ref="payload:opaque",
                payload_sha256=PAYLOAD_SHA,
                provenance_refs=(),
                support_refs=("evidence:1",),
                classification=OBSERVED_EVIDENCE,
            )

    def test_missing_support_fails_closed(self):
        with self.assertRaisesRegex(
            EpistemicRecordError, "support_ref must contain at least one"
        ):
            create_epistemic_record(
                record_id="record:no-support",
                subject_ref="subject:widget",
                generation=0,
                payload_ref="payload:opaque",
                payload_sha256=PAYLOAD_SHA,
                provenance_refs=("source:1",),
                support_refs=(),
                classification=INFERRED_HYPOTHESIS,
            )

    def test_support_and_counterevidence_must_be_disjoint(self):
        with self.assertRaisesRegex(EpistemicRecordError, "must be disjoint"):
            create_epistemic_record(
                record_id="record:conflict",
                subject_ref="subject:widget",
                generation=0,
                payload_ref="payload:opaque",
                payload_sha256=PAYLOAD_SHA,
                provenance_refs=("source:1",),
                support_refs=("evidence:same",),
                counterevidence_refs=("evidence:same",),
                classification=INFERRED_HYPOTHESIS,
            )

    def test_duplicate_refs_fail_closed(self):
        with self.assertRaisesRegex(EpistemicRecordError, "duplicate references"):
            create_epistemic_record(
                record_id="record:duplicate",
                subject_ref="subject:widget",
                generation=0,
                payload_ref="payload:opaque",
                payload_sha256=PAYLOAD_SHA,
                provenance_refs=("source:1", "source:1"),
                support_refs=("evidence:1",),
                classification=NEGATIVE_RESULT,
            )

    def test_unknown_classification_fails_closed(self):
        with self.assertRaisesRegex(
            EpistemicRecordError, "unsupported epistemic classification"
        ):
            create_epistemic_record(
                record_id="record:bad-class",
                subject_ref="subject:widget",
                generation=0,
                payload_ref="payload:opaque",
                payload_sha256=PAYLOAD_SHA,
                provenance_refs=("source:1",),
                support_refs=("evidence:1",),
                classification="WORLD_TRUTH",
            )

    def test_payload_digest_must_be_lowercase_sha256(self):
        with self.assertRaisesRegex(EpistemicRecordError, "lowercase 64-hex"):
            create_epistemic_record(
                record_id="record:bad-sha",
                subject_ref="subject:widget",
                generation=0,
                payload_ref="payload:opaque",
                payload_sha256="A" * 64,
                provenance_refs=("source:1",),
                support_refs=("evidence:1",),
                classification=OBSERVED_EVIDENCE,
            )

    def test_generation_zero_rejects_parent_digest(self):
        with self.assertRaisesRegex(
            EpistemicRecordError, "generation 0 must not carry"
        ):
            make_record(generation=0, parent_record_sha256=PARENT_SHA)

    def test_nonzero_generation_requires_parent_digest(self):
        with self.assertRaisesRegex(
            EpistemicRecordError, "nonzero generation requires"
        ):
            make_record(generation=1, parent_record_sha256=None)

    def test_nonzero_generation_binds_parent_identity(self):
        child = make_record(generation=1, parent_record_sha256=PARENT_SHA)
        sibling = create_epistemic_record(
            record_id=child.record_id,
            subject_ref=child.subject_ref,
            generation=1,
            payload_ref=child.payload_ref,
            payload_sha256=child.payload_sha256,
            provenance_refs=child.provenance_refs,
            support_refs=child.support_refs,
            counterevidence_refs=child.counterevidence_refs,
            classification=child.classification,
            parent_record_sha256="4" * 64,
        )
        self.assertNotEqual(child.identity_sha256, sibling.identity_sha256)

    def test_identity_binds_subject_and_payload_without_reading_payload(self):
        original = make_record()
        changed_subject = create_epistemic_record(
            record_id=original.record_id,
            subject_ref="subject:other",
            generation=0,
            payload_ref=original.payload_ref,
            payload_sha256=original.payload_sha256,
            provenance_refs=original.provenance_refs,
            support_refs=original.support_refs,
            counterevidence_refs=original.counterevidence_refs,
            classification=original.classification,
        )
        changed_payload_ref = create_epistemic_record(
            record_id=original.record_id,
            subject_ref=original.subject_ref,
            generation=0,
            payload_ref="payload:opaque:other",
            payload_sha256=original.payload_sha256,
            provenance_refs=original.provenance_refs,
            support_refs=original.support_refs,
            counterevidence_refs=original.counterevidence_refs,
            classification=original.classification,
        )
        self.assertNotEqual(original.identity_sha256, changed_subject.identity_sha256)
        self.assertNotEqual(original.identity_sha256, changed_payload_ref.identity_sha256)


if __name__ == "__main__":
    unittest.main()
