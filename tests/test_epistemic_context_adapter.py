from __future__ import annotations

import hashlib
import unittest

from frankenstein2.context_compiler import (
    CHANNEL_COUNTEREVIDENCE,
    CHANNEL_EVIDENCE,
    CHANNEL_HYPERPOSITION,
    CHANNEL_RETRIEVAL_REFERENCE,
    ContextCompilerError,
)
from frankenstein2.epistemic_context_adapter import (
    EpistemicContextAdapterError,
    context_item_from_epistemic_record,
)
from frankenstein2.epistemic_records import (
    InferredHypothesis,
    NegativeResult,
    ObservedEvidence,
    RetrievalPrior,
    UnknownEvidence,
)


PROVENANCE = "a" * 64
QUERY = "b" * 64


def bind(record, *, item_id="ctx-1", priority_bp=7000, cost_units=3, required=False):
    return context_item_from_epistemic_record(
        record,
        item_id=item_id,
        payload_ref=f"payload:{record.record_id}",
        priority_bp=priority_bp,
        cost_units=cost_units,
        required=required,
    )


class EpistemicContextAdapterTests(unittest.TestCase):
    def test_observed_evidence_binds_exact_identity_and_payload_digest(self):
        record = ObservedEvidence.create(
            record_id="obs-1",
            generation=0,
            payload={"value": 7},
            provenance_sha256=PROVENANCE,
            observation_ref="sensor:frame:7",
            causal_refs=("cause:6",),
        )
        item = bind(record, required=True)
        self.assertEqual(item.channel, CHANNEL_EVIDENCE)
        self.assertEqual(item.source_ref, record.record_id)
        self.assertEqual(item.source_generation, 0)
        self.assertEqual(item.source_sha256, record.identity_sha256)
        self.assertEqual(
            item.payload_sha256,
            hashlib.sha256(record.payload_json.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(item.source_classification, record.classification)
        self.assertIn("sensor:frame:7", item.evidence_refs)
        self.assertIn("cause:6", item.evidence_refs)
        self.assertIn(f"provenance-sha256:{PROVENANCE}", item.provenance_refs)

    def test_hypothesis_cannot_be_laundered_into_observed_evidence(self):
        record = InferredHypothesis.create(
            record_id="hyp-1",
            generation=1,
            payload={"candidate": "A"},
            provenance_sha256=PROVENANCE,
            support_refs=("obs-1",),
        )
        item = bind(record)
        self.assertEqual(item.channel, CHANNEL_HYPERPOSITION)
        self.assertNotEqual(item.channel, CHANNEL_EVIDENCE)
        self.assertEqual(item.source_classification, record.classification)
        self.assertIn("obs-1", item.evidence_refs)

    def test_retrieval_prior_stays_reference_only(self):
        record = RetrievalPrior.create(
            record_id="prior-1",
            generation=2,
            payload={"candidate_ref": "memory:4"},
            provenance_sha256=PROVENANCE,
            retrieval_ref="retrieval-plan:9",
            query_sha256=QUERY,
        )
        item = bind(record)
        self.assertEqual(item.channel, CHANNEL_RETRIEVAL_REFERENCE)
        self.assertNotEqual(item.channel, CHANNEL_EVIDENCE)
        self.assertIn("retrieval-plan:9", item.evidence_refs)
        self.assertIn(f"query-sha256:{QUERY}", item.evidence_refs)

    def test_negative_result_is_counterevidence_not_global_do_not_repeat(self):
        record = NegativeResult.create(
            record_id="neg-1",
            generation=3,
            payload={"outcome": "falsified under fixture A"},
            provenance_sha256=PROVENANCE,
            attempt_ref="attempt:1",
            falsifier_ref="test:test_fixture_a",
        )
        item = bind(record)
        self.assertEqual(item.channel, CHANNEL_COUNTEREVIDENCE)
        self.assertIn("attempt:1", item.evidence_refs)
        self.assertIn("test:test_fixture_a", item.evidence_refs)

    def test_unknown_remains_explicit_unknown_in_hyperposition_bucket(self):
        record = UnknownEvidence.create(
            record_id="unknown-1",
            generation=4,
            payload={"field": "object.identity"},
            provenance_sha256=PROVENANCE,
            reason="insufficient observation",
        )
        item = bind(record)
        self.assertEqual(item.channel, CHANNEL_HYPERPOSITION)
        self.assertNotEqual(item.channel, CHANNEL_EVIDENCE)
        self.assertEqual(
            item.source_classification,
            "UNKNOWN_NOT_FILLED_BY_INFERENCE_OR_RETRIEVAL",
        )
        self.assertEqual(len(item.evidence_refs), 1)
        self.assertTrue(item.evidence_refs[0].startswith("epistemic-record-sha256:"))

    def test_unsupported_or_forged_type_fails_closed(self):
        class ForgedRecord:
            record_id = "obs-forged"
            generation = 1
            payload_json = "{}"
            provenance_sha256 = PROVENANCE
            classification = "OBSERVED_EVIDENCE_NOT_WORLD_TRUTH"
            identity_sha256 = "c" * 64
            causal_refs = ()

        with self.assertRaisesRegex(
            EpistemicContextAdapterError,
            "exact accepted F2-WP-207 epistemic record type",
        ):
            bind(ForgedRecord())

    def test_budget_validation_is_not_bypassed_by_adapter(self):
        record = ObservedEvidence.create(
            record_id="obs-budget",
            generation=1,
            payload={"value": 1},
            provenance_sha256=PROVENANCE,
            observation_ref="sensor:1",
        )
        with self.assertRaisesRegex(ContextCompilerError, "priority_bp"):
            bind(record, priority_bp=10001)
        with self.assertRaisesRegex(ContextCompilerError, "cost_units"):
            bind(record, cost_units=0)

    def test_binding_is_deterministic_and_payload_semantics_do_not_choose_priority(self):
        record_a = ObservedEvidence.create(
            record_id="obs-a",
            generation=1,
            payload={"semantic": "highly important"},
            provenance_sha256=PROVENANCE,
            observation_ref="sensor:a",
        )
        record_b = ObservedEvidence.create(
            record_id="obs-b",
            generation=1,
            payload={"semantic": "irrelevant"},
            provenance_sha256=PROVENANCE,
            observation_ref="sensor:b",
        )
        item_a = bind(record_a, item_id="item-a", priority_bp=1234)
        item_b = bind(record_b, item_id="item-b", priority_bp=1234)
        self.assertEqual(item_a.priority_bp, 1234)
        self.assertEqual(item_b.priority_bp, 1234)
        self.assertNotEqual(item_a.source_sha256, item_b.source_sha256)


if __name__ == "__main__":
    unittest.main(verbosity=2)
