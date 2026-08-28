from __future__ import annotations

import hashlib
import unittest

from frankenstein2.epistemic_context_view import (
    KNOWN_RECORD_SCHEMAS,
    NOT_SELECTED_LIMIT,
    NOT_SELECTED_SCHEMA,
    SELECTED_EXPLICIT_RELEVANCE,
    EpistemicContextCandidate,
    EpistemicContextRequest,
    EpistemicContextViewError,
    compile_epistemic_context_view,
)
from frankenstein2.epistemic_records import (
    InferredHypothesis,
    NegativeResult,
    ObservedEvidence,
    RetrievalPrior,
    UnknownEvidence,
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _observed(record_id: str = "r:observed") -> ObservedEvidence:
    return ObservedEvidence.create(
        record_id=record_id,
        generation=1,
        payload={"value": 7},
        provenance_sha256=_sha(f"prov:{record_id}"),
        observation_ref=f"obs:{record_id}",
        causal_refs=(f"cause:{record_id}",),
    )


def _inferred(record_id: str = "r:inferred") -> InferredHypothesis:
    return InferredHypothesis.create(
        record_id=record_id,
        generation=2,
        payload={"hypothesis": "candidate"},
        provenance_sha256=_sha(f"prov:{record_id}"),
        support_refs=(f"support:{record_id}",),
    )


def _retrieval(record_id: str = "r:retrieval") -> RetrievalPrior:
    return RetrievalPrior.create(
        record_id=record_id,
        generation=3,
        payload={"memory_ref": "m:1"},
        provenance_sha256=_sha(f"prov:{record_id}"),
        retrieval_ref=f"retrieval:{record_id}",
        query_sha256=_sha(f"query:{record_id}"),
    )


def _negative(record_id: str = "r:negative") -> NegativeResult:
    return NegativeResult.create(
        record_id=record_id,
        generation=4,
        payload={"result": "failed"},
        provenance_sha256=_sha(f"prov:{record_id}"),
        attempt_ref=f"attempt:{record_id}",
        falsifier_ref=f"falsifier:{record_id}",
    )


def _unknown(record_id: str = "r:unknown") -> UnknownEvidence:
    return UnknownEvidence.create(
        record_id=record_id,
        generation=5,
        payload={"known": False},
        provenance_sha256=_sha(f"prov:{record_id}"),
        reason="insufficient current evidence",
    )


def _candidate(record, relevance: int) -> EpistemicContextCandidate:
    return EpistemicContextCandidate.create(
        record=record,
        expected_record_sha256=record.identity_sha256,
        relevance_bp=relevance,
        relevance_evidence_refs=(f"score:{record.record_id}",),
    )


def _request(*, max_records: int = 3, allowed=KNOWN_RECORD_SCHEMAS):
    return EpistemicContextRequest.create(
        view_id="view:1",
        max_records=max_records,
        allowed_record_schemas=allowed,
        policy_evidence_refs=("policy:explicit-bounded-context",),
    )


class EpistemicContextViewTests(unittest.TestCase):
    def test_deterministic_selection_order_and_view_digest(self) -> None:
        candidates = (
            _candidate(_observed("r:b"), 8_000),
            _candidate(_inferred("r:a"), 8_000),
            _candidate(_unknown("r:c"), 9_000),
        )
        request = _request(max_records=3)

        forward = compile_epistemic_context_view(request, candidates)
        reverse = compile_epistemic_context_view(request, tuple(reversed(candidates)))

        self.assertEqual(forward.as_dict(), reverse.as_dict())
        self.assertEqual(forward.sha256(), reverse.sha256())
        self.assertEqual(
            tuple(item.record_id for item in forward.selected),
            ("r:c", "r:a", "r:b"),
        )
        self.assertTrue(
            all(item.selection_reason == SELECTED_EXPLICIT_RELEVANCE for item in forward.selected)
        )

    def test_all_epistemic_types_preserve_schema_classification_and_provenance(self) -> None:
        records = (
            _observed(),
            _inferred(),
            _retrieval(),
            _negative(),
            _unknown(),
        )
        view = compile_epistemic_context_view(
            _request(max_records=5),
            tuple(_candidate(record, 5_000) for record in records),
        )

        by_id = {item.record_id: item for item in view.selected}
        for record in records:
            ref = by_id[record.record_id]
            self.assertEqual(ref.record_schema, type(record).schema)
            self.assertEqual(ref.record_classification, type(record).classification)
            self.assertEqual(ref.record_identity_sha256, record.identity_sha256)
            self.assertEqual(ref.provenance_sha256, record.provenance_sha256)

    def test_unknown_is_not_coerced_when_schema_is_not_requested(self) -> None:
        unknown = _unknown()
        observed = _observed()
        request = _request(
            max_records=2,
            allowed=(ObservedEvidence.schema,),
        )
        view = compile_epistemic_context_view(
            request,
            (_candidate(unknown, 10_000), _candidate(observed, 1_000)),
        )

        self.assertEqual(tuple(item.record_id for item in view.selected), (observed.record_id,))
        self.assertEqual(len(view.not_selected), 1)
        excluded = view.not_selected[0]
        self.assertEqual(excluded.record_id, unknown.record_id)
        self.assertEqual(excluded.record_schema, UnknownEvidence.schema)
        self.assertEqual(excluded.record_classification, UnknownEvidence.classification)
        self.assertEqual(excluded.selection_reason, NOT_SELECTED_SCHEMA)

    def test_limit_is_bounded_and_nonselected_records_remain_explicit(self) -> None:
        a = _candidate(_observed("r:a"), 9_000)
        b = _candidate(_inferred("r:b"), 8_000)
        c = _candidate(_negative("r:c"), 7_000)
        view = compile_epistemic_context_view(_request(max_records=2), (a, b, c))

        self.assertEqual(tuple(item.record_id for item in view.selected), ("r:a", "r:b"))
        self.assertEqual(tuple(item.record_id for item in view.not_selected), ("r:c",))
        self.assertEqual(view.not_selected[0].selection_reason, NOT_SELECTED_LIMIT)
        self.assertEqual(view.candidate_count, 3)

    def test_stale_or_wrong_record_digest_fails_closed(self) -> None:
        record = _observed()
        with self.assertRaisesRegex(EpistemicContextViewError, "record identity digest mismatch"):
            EpistemicContextCandidate.create(
                record=record,
                expected_record_sha256=_sha("wrong"),
                relevance_bp=5_000,
                relevance_evidence_refs=("score:wrong",),
            )

    def test_duplicate_record_identity_fails_closed_even_across_candidates(self) -> None:
        record = _observed("r:dup")
        first = _candidate(record, 8_000)
        second = _candidate(record, 7_000)
        with self.assertRaisesRegex(EpistemicContextViewError, "duplicate record_id"):
            compile_epistemic_context_view(_request(), (first, second))

    def test_boolean_or_out_of_range_relevance_is_rejected(self) -> None:
        record = _observed()
        for value in (True, -1, 10_001):
            with self.subTest(value=value):
                with self.assertRaisesRegex(EpistemicContextViewError, "relevance_bp"):
                    EpistemicContextCandidate.create(
                        record=record,
                        expected_record_sha256=record.identity_sha256,
                        relevance_bp=value,
                        relevance_evidence_refs=("score:invalid",),
                    )

    def test_unknown_schema_and_duplicate_schema_policy_fail_closed(self) -> None:
        with self.assertRaisesRegex(EpistemicContextViewError, "unknown schema"):
            _request(allowed=("NOT_A_REAL_SCHEMA",))
        with self.assertRaisesRegex(EpistemicContextViewError, "duplicates"):
            _request(allowed=(ObservedEvidence.schema, ObservedEvidence.schema))

    def test_reference_view_never_contains_record_payload_json(self) -> None:
        record = _observed()
        view = compile_epistemic_context_view(_request(max_records=1), (_candidate(record, 9_000),))
        rendered = view.as_dict()
        selected = rendered["selected"][0]

        self.assertNotIn("payload", selected)
        self.assertNotIn("payload_json", selected)
        self.assertEqual(selected["record_identity_sha256"], record.identity_sha256)

    def test_request_bounds_reject_zero_bool_and_excessive_limits(self) -> None:
        for value in (0, True, 1_025):
            with self.subTest(value=value):
                with self.assertRaisesRegex(EpistemicContextViewError, "max_records"):
                    _request(max_records=value)

    def test_non_candidate_input_fails_closed(self) -> None:
        with self.assertRaisesRegex(EpistemicContextViewError, "EpistemicContextCandidate"):
            compile_epistemic_context_view(_request(), (_observed(),))


if __name__ == "__main__":
    unittest.main()
