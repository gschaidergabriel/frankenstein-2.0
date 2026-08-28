from __future__ import annotations

from dataclasses import replace
import math
import unittest

from frankenstein2.epistemic_records import (
    EpistemicRecordError,
    InferredHypothesis,
    NegativeResult,
    ObservedEvidence,
    RetrievalPrior,
    UnknownEvidence,
)


PROVENANCE_A = "a" * 64
PROVENANCE_B = "b" * 64
QUERY = "c" * 64


class EpistemicRecordTests(unittest.TestCase):
    def test_observed_evidence_is_canonical_and_identity_stable(self):
        first = ObservedEvidence.create(
            record_id="obs-1",
            generation=3,
            payload={"b": 2, "a": 1},
            provenance_sha256=PROVENANCE_A,
            observation_ref="camera:frame:7",
        )
        second = ObservedEvidence.create(
            record_id="obs-1",
            generation=3,
            payload={"a": 1, "b": 2},
            provenance_sha256=PROVENANCE_A,
            observation_ref="camera:frame:7",
        )
        self.assertEqual(first.payload_json, '{"a":1,"b":2}')
        self.assertEqual(first.identity_sha256, second.identity_sha256)
        self.assertEqual(first.classification, "OBSERVED_EVIDENCE_NOT_WORLD_TRUTH")

    def test_returned_payload_is_detached_from_record_identity(self):
        record = ObservedEvidence.create(
            record_id="obs-1",
            generation=1,
            payload={"values": [1, 2]},
            provenance_sha256=PROVENANCE_A,
            observation_ref="sensor:1",
        )
        identity_before = record.identity_sha256
        decoded = record.payload()
        decoded["values"].append(3)
        self.assertEqual(record.identity_sha256, identity_before)
        self.assertEqual(record.payload(), {"values": [1, 2]})

    def test_classification_is_type_fixed_not_replaceable(self):
        observed = ObservedEvidence.create(
            record_id="obs-1",
            generation=1,
            payload={"value": 1},
            provenance_sha256=PROVENANCE_A,
            observation_ref="sensor:1",
        )
        with self.assertRaises(TypeError):
            replace(observed, classification="WORLD_TRUTH")

    def test_provenance_change_changes_identity(self):
        observed = ObservedEvidence.create(
            record_id="obs-1",
            generation=1,
            payload={"value": 1},
            provenance_sha256=PROVENANCE_A,
            observation_ref="sensor:1",
        )
        changed = replace(observed, provenance_sha256=PROVENANCE_B)
        self.assertNotEqual(observed.identity_sha256, changed.identity_sha256)

    def test_hypothesis_requires_support_and_is_not_observation(self):
        with self.assertRaisesRegex(EpistemicRecordError, "support_refs must not be empty"):
            InferredHypothesis.create(
                record_id="hyp-1",
                generation=1,
                payload={"claim": "cup moved"},
                provenance_sha256=PROVENANCE_A,
                support_refs=(),
            )
        hypothesis = InferredHypothesis.create(
            record_id="hyp-1",
            generation=1,
            payload={"claim": "cup moved"},
            provenance_sha256=PROVENANCE_A,
            support_refs=("obs-1",),
        )
        self.assertEqual(
            hypothesis.classification,
            "INFERRED_HYPOTHESIS_NOT_OBSERVATION_OR_WORLD_TRUTH",
        )

    def test_retrieval_prior_requires_bound_query_digest(self):
        with self.assertRaisesRegex(EpistemicRecordError, "query_sha256"):
            RetrievalPrior.create(
                record_id="prior-1",
                generation=1,
                payload={"memory": "candidate"},
                provenance_sha256=PROVENANCE_A,
                retrieval_ref="unifieddb:row:9",
                query_sha256="not-a-digest",
            )
        prior = RetrievalPrior.create(
            record_id="prior-1",
            generation=1,
            payload={"memory": "candidate"},
            provenance_sha256=PROVENANCE_A,
            retrieval_ref="unifieddb:row:9",
            query_sha256=QUERY,
        )
        self.assertEqual(
            prior.classification,
            "RETRIEVAL_PRIOR_NOT_OBSERVATION_OR_WORLD_TRUTH",
        )

    def test_negative_result_requires_attempt_and_falsifier(self):
        with self.assertRaisesRegex(EpistemicRecordError, "falsifier_ref"):
            NegativeResult.create(
                record_id="neg-1",
                generation=1,
                payload={"outcome": "counterexample"},
                provenance_sha256=PROVENANCE_A,
                attempt_ref="experiment:4",
                falsifier_ref="",
            )
        result = NegativeResult.create(
            record_id="neg-1",
            generation=1,
            payload={"outcome": "counterexample"},
            provenance_sha256=PROVENANCE_A,
            attempt_ref="experiment:4",
            falsifier_ref="test:test_counterexample",
        )
        self.assertEqual(
            result.classification,
            "NEGATIVE_RESULT_NOT_ABSENCE_OF_ALL_ALTERNATIVES",
        )

    def test_unknown_is_explicit_and_not_fillable_by_retrieval(self):
        with self.assertRaisesRegex(EpistemicRecordError, "reason"):
            UnknownEvidence.create(
                record_id="unknown-1",
                generation=1,
                payload={"field": "object.identity"},
                provenance_sha256=PROVENANCE_A,
                reason="",
            )
        unknown = UnknownEvidence.create(
            record_id="unknown-1",
            generation=1,
            payload={"field": "object.identity"},
            provenance_sha256=PROVENANCE_A,
            reason="sensor evidence insufficient",
            causal_refs=("obs-1",),
        )
        self.assertEqual(
            unknown.classification,
            "UNKNOWN_NOT_FILLED_BY_INFERENCE_OR_RETRIEVAL",
        )

    def test_non_json_and_noncanonical_direct_constructor_fail_closed(self):
        with self.assertRaisesRegex(EpistemicRecordError, "canonical-JSON encodable"):
            ObservedEvidence.create(
                record_id="obs-nan",
                generation=1,
                payload={"value": math.nan},
                provenance_sha256=PROVENANCE_A,
                observation_ref="sensor:1",
            )
        with self.assertRaisesRegex(EpistemicRecordError, "already be canonical JSON"):
            ObservedEvidence(
                record_id="obs-raw",
                generation=1,
                payload_json='{"b": 2, "a": 1}',
                provenance_sha256=PROVENANCE_A,
                observation_ref="sensor:1",
            )

    def test_causal_refs_are_immutable_unique_refs(self):
        with self.assertRaisesRegex(EpistemicRecordError, "immutable tuple"):
            ObservedEvidence.create(
                record_id="obs-list",
                generation=1,
                payload={"value": 1},
                provenance_sha256=PROVENANCE_A,
                observation_ref="sensor:1",
                causal_refs=["parent-1"],  # type: ignore[arg-type]
            )
        with self.assertRaisesRegex(EpistemicRecordError, "duplicates"):
            ObservedEvidence.create(
                record_id="obs-dup",
                generation=1,
                payload={"value": 1},
                provenance_sha256=PROVENANCE_A,
                observation_ref="sensor:1",
                causal_refs=("parent-1", "parent-1"),
            )

    def test_identity_and_provenance_refs_must_be_already_trimmed(self):
        cases = (
            dict(record_id=" obs-1", observation_ref="sensor:1", causal_refs=()),
            dict(record_id="obs-1", observation_ref="sensor:1 ", causal_refs=()),
            dict(record_id="obs-1", observation_ref="sensor:1", causal_refs=(" parent-1",)),
        )
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaisesRegex(EpistemicRecordError, "already trimmed"):
                    ObservedEvidence.create(
                        generation=1,
                        payload={"value": 1},
                        provenance_sha256=PROVENANCE_A,
                        **kwargs,
                    )


if __name__ == "__main__":
    unittest.main(verbosity=2)
