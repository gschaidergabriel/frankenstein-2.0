import unittest

from src.frankenstein2.epistemic_perception import EpistemicPerceptClaim
from src.frankenstein2.perception_clock_alignment_admission import (
    ClockAlignmentAdmissionRecord,
    ClockAlignmentAdmissionRegistrySnapshot,
)
from src.frankenstein2.perception_temporal import (
    ClockAlignmentWitness,
    PerceptionTemporalError,
    bind_observed_claim,
    build_observation_window,
)


P = ("test:temporal",)
EVIDENCE_SHA = "1" * 64
AUTHORITY_RECEIPT_SHA = "3" * 64


def claim(
    claim_id="c1",
    source_time_ns=100,
    epistemic_type="OBSERVED",
    source_generation=1,
):
    return EpistemicPerceptClaim(
        claim_id=claim_id,
        semantic_key="screen.app",
        modality="visual",
        epistemic_type=epistemic_type,
        value="Firefox",
        confidence_micros=900_000,
        source_generation=source_generation,
        source_time_ns=source_time_ns,
        provenance_refs=P,
    )


def bind(
    c,
    *,
    ref_id,
    source_id,
    sequence,
    offset=0,
    uncertainty=0,
    freshness=100,
    clock_domain=None,
):
    return bind_observed_claim(
        claim=c,
        expected_claim_sha256=c.sha256(),
        ref_id=ref_id,
        source_id=source_id,
        source_sequence=sequence,
        clock_domain=clock_domain or f"clock:{source_id}",
        reference_offset_ns=offset,
        clock_uncertainty_ns=uncertainty,
        max_freshness_ns=freshness,
        provenance_refs=P,
    )


def witness(
    left,
    right,
    *,
    alignment_id="alignment:1",
    left_offset=None,
    right_offset=None,
    left_uncertainty=None,
    right_uncertainty=None,
    valid_from=0,
    valid_through=2_000,
):
    return ClockAlignmentWitness(
        alignment_id=alignment_id,
        alignment_generation=1,
        left_clock_domain=left.clock_domain,
        left_source_generation=left.source_generation,
        left_reference_offset_ns=(
            left.reference_offset_ns if left_offset is None else left_offset
        ),
        left_max_uncertainty_ns=(
            left.clock_uncertainty_ns if left_uncertainty is None else left_uncertainty
        ),
        right_clock_domain=right.clock_domain,
        right_source_generation=right.source_generation,
        right_reference_offset_ns=(
            right.reference_offset_ns if right_offset is None else right_offset
        ),
        right_max_uncertainty_ns=(
            right.clock_uncertainty_ns if right_uncertainty is None else right_uncertainty
        ),
        valid_from_reference_ns=valid_from,
        valid_through_reference_ns=valid_through,
        evidence_sha256=EVIDENCE_SHA,
        provenance_refs=("test:clock-alignment-evidence",),
    )


def admission_record(w, *, admission_id=None, witness_sha=None, alignment_id=None):
    return ClockAlignmentAdmissionRecord(
        admission_id=admission_id or f"admission:{w.alignment_id}",
        admission_generation=1,
        alignment_id=alignment_id or w.alignment_id,
        witness_sha256=w.sha256() if witness_sha is None else witness_sha,
        provenance_refs=("test:upstream-clock-admission-record",),
    )


def registry_for(
    *witnesses,
    records=None,
    registry_id="clock-registry:1",
    authority_id="unifieddb:clock-alignment-admission",
    authority_generation=7,
    authority_receipt_sha256=AUTHORITY_RECEIPT_SHA,
):
    if records is None:
        records = tuple(admission_record(w) for w in witnesses)
    return ClockAlignmentAdmissionRegistrySnapshot(
        registry_id=registry_id,
        registry_generation=4,
        authority_id=authority_id,
        authority_generation=authority_generation,
        authority_receipt_sha256=authority_receipt_sha256,
        admissions=tuple(records),
        provenance_refs=("test:upstream-clock-admission-registry",),
    )


class PerceptionTemporalTests(unittest.TestCase):
    def test_only_observed_claims_enter_current_window(self):
        inferred = claim(epistemic_type="INFERRED")
        with self.assertRaisesRegex(PerceptionTemporalError, "only OBSERVED"):
            bind(inferred, ref_id="r1", source_id="screen:1", sequence=1)

    def test_claim_digest_is_exact(self):
        c = claim()
        with self.assertRaisesRegex(PerceptionTemporalError, "claim digest mismatch"):
            bind_observed_claim(
                claim=c,
                expected_claim_sha256="0" * 64,
                ref_id="r1",
                source_id="screen:1",
                source_sequence=1,
                clock_domain="clock:screen:1",
                reference_offset_ns=0,
                clock_uncertainty_ns=0,
                max_freshness_ns=100,
                provenance_refs=P,
            )

    def test_fresh_stale_and_uncertain_partition_explicitly(self):
        fresh = bind(claim("c1", 950), ref_id="fresh", source_id="screen:1", sequence=1)
        stale = bind(claim("c2", 700), ref_id="stale", source_id="screen:2", sequence=1)
        uncertain = bind(
            claim("c3", 950),
            ref_id="uncertain",
            source_id="camera:1",
            sequence=1,
            uncertainty=30,
        )
        window = build_observation_window(
            refs=(fresh, stale, uncertain),
            reference_now_ns=1_000,
            max_join_skew_ns=100,
            max_clock_uncertainty_ns=20,
            provenance_refs=P,
        )
        self.assertEqual(window.current_ref_ids, ("fresh",))
        self.assertEqual(window.stale_ref_ids, ("stale",))
        self.assertEqual(window.unaligned_ref_ids, ("uncertain",))
        self.assertEqual(window.alignment_status, "PARTIAL_UNALIGNED")

    def test_pr398_unproven_distinct_clock_domains_remain_unaligned(self):
        a = bind(
            claim("c1", 980),
            ref_id="a",
            source_id="screen:1",
            sequence=1,
            clock_domain="clock:host-a",
        )
        b = bind(
            claim("c2", 980),
            ref_id="b",
            source_id="camera:1",
            sequence=1,
            clock_domain="clock:host-b",
        )
        window = build_observation_window(
            refs=(a, b),
            reference_now_ns=1_000,
            max_join_skew_ns=20,
            max_clock_uncertainty_ns=5,
            provenance_refs=P,
        )
        self.assertEqual(window.current_ref_ids, ())
        self.assertEqual(set(window.unaligned_ref_ids), {"a", "b"})
        self.assertEqual(window.alignment_witness_refs, ())
        self.assertEqual(window.alignment_admission_refs, ())
        self.assertIsNone(window.alignment_admission_registry_sha256)

    def test_pr409_caller_minted_witness_without_registry_admission_is_unaligned(self):
        """Permanent regression for the executable G2 self-authorizing witness falsifier."""
        a = bind(
            claim("c1", 980),
            ref_id="a",
            source_id="screen:1",
            sequence=1,
            clock_domain="clock:host-a",
        )
        b = bind(
            claim("c2", 480),
            ref_id="b",
            source_id="camera:1",
            sequence=1,
            offset=500,
            clock_domain="clock:host-b",
        )
        fabricated = witness(a, b)
        window = build_observation_window(
            refs=(a, b),
            reference_now_ns=1_000,
            max_join_skew_ns=20,
            max_clock_uncertainty_ns=5,
            provenance_refs=P,
            alignment_witnesses=(fabricated,),
        )
        self.assertEqual(window.current_ref_ids, ())
        self.assertEqual(set(window.unaligned_ref_ids), {"a", "b"})
        self.assertEqual(window.alignment_witness_refs, ())
        self.assertEqual(window.alignment_admission_refs, ())
        self.assertIsNone(window.alignment_admission_registry_sha256)

    def test_pr425_bare_caller_digest_is_rejected_as_admission_authority(self):
        """Permanent regression for run 33253449628 / job 99102982300."""
        local = bind(
            claim("c1", 980),
            ref_id="local",
            source_id="screen:1",
            sequence=1,
            clock_domain="clock:local",
        )
        remote = bind(
            claim("c2", 480),
            ref_id="remote",
            source_id="camera:remote",
            sequence=1,
            offset=500,
            clock_domain="clock:remote",
        )
        fabricated = witness(local, remote)
        with self.assertRaisesRegex(
            PerceptionTemporalError,
            "bare caller-supplied witness digests",
        ):
            build_observation_window(
                refs=(local, remote),
                reference_now_ns=1_000,
                max_join_skew_ns=30,
                max_clock_uncertainty_ns=5,
                provenance_refs=P,
                alignment_witnesses=(fabricated,),
                admitted_alignment_witness_sha256s=(fabricated.sha256(),),
            )

    def test_upstream_registry_admitted_exact_witness_enables_bounded_join_and_is_recorded(self):
        local = bind(
            claim("c1", 980),
            ref_id="local",
            source_id="screen:1",
            sequence=1,
            clock_domain="clock:local",
        )
        remote = bind(
            claim("c2", 480),
            ref_id="remote",
            source_id="camera:remote",
            sequence=1,
            offset=500,
            uncertainty=5,
            clock_domain="clock:remote",
        )
        alignment = witness(local, remote, left_uncertainty=5, right_uncertainty=5)
        registry = registry_for(alignment)
        record = registry.admissions[0]
        window = build_observation_window(
            refs=(local, remote),
            reference_now_ns=1_000,
            max_join_skew_ns=30,
            max_clock_uncertainty_ns=10,
            provenance_refs=P,
            alignment_witnesses=(alignment,),
            alignment_admission_registry=registry,
        )
        alignment_sha = alignment.sha256()
        self.assertEqual(set(window.current_ref_ids), {"local", "remote"})
        self.assertEqual(window.unaligned_ref_ids, ())
        self.assertEqual(window.alignment_witness_refs, ((alignment.alignment_id, alignment_sha),))
        self.assertEqual(
            window.alignment_admission_refs,
            ((record.admission_id, alignment_sha, record.sha256()),),
        )
        self.assertEqual(window.alignment_admission_registry_sha256, registry.sha256())
        self.assertIn(
            f"clock-alignment-admission-registry-sha256:{registry.sha256()}",
            window.provenance_refs,
        )
        self.assertIn(
            f"clock-alignment-admission-authority-receipt-sha256:{AUTHORITY_RECEIPT_SHA}",
            window.provenance_refs,
        )

    def test_registry_record_mismatch_or_ambiguity_remains_unaligned(self):
        local = bind(
            claim("c1", 980),
            ref_id="local",
            source_id="screen:1",
            sequence=1,
            clock_domain="clock:a",
        )
        remote = bind(
            claim("c2", 480),
            ref_id="remote",
            source_id="camera:1",
            sequence=1,
            offset=500,
            clock_domain="clock:b",
        )
        alignment = witness(local, remote)

        mismatched = registry_for(
            records=(admission_record(alignment, witness_sha="2" * 64),),
        )
        ambiguous = registry_for(
            records=(
                admission_record(alignment, admission_id="admission:a"),
                admission_record(alignment, admission_id="admission:b"),
            ),
        )
        for registry in (mismatched, ambiguous):
            with self.subTest(registry=registry.registry_id, count=len(registry.admissions)):
                window = build_observation_window(
                    refs=(local, remote),
                    reference_now_ns=1_000,
                    max_join_skew_ns=30,
                    max_clock_uncertainty_ns=5,
                    provenance_refs=P,
                    alignment_witnesses=(alignment,),
                    alignment_admission_registry=registry,
                )
                self.assertEqual(window.current_ref_ids, ())
                self.assertEqual(set(window.unaligned_ref_ids), {"local", "remote"})
                self.assertEqual(window.alignment_admission_refs, ())
                self.assertIsNone(window.alignment_admission_registry_sha256)

    def test_wrong_or_expired_registry_admitted_witness_remains_unaligned(self):
        local = bind(
            claim("c1", 980),
            ref_id="local",
            source_id="screen:1",
            sequence=1,
            clock_domain="clock:a",
        )
        remote = bind(
            claim("c2", 480),
            ref_id="remote",
            source_id="camera:1",
            sequence=1,
            offset=500,
            clock_domain="clock:b",
        )
        wrong = witness(local, remote, alignment_id="wrong", right_offset=499)
        expired = witness(local, remote, alignment_id="expired", valid_through=900)
        for candidate in (wrong, expired):
            window = build_observation_window(
                refs=(local, remote),
                reference_now_ns=1_000,
                max_join_skew_ns=30,
                max_clock_uncertainty_ns=5,
                provenance_refs=P,
                alignment_witnesses=(candidate,),
                alignment_admission_registry=registry_for(candidate),
            )
            self.assertEqual(window.current_ref_ids, ())
            self.assertEqual(set(window.unaligned_ref_ids), {"local", "remote"})

    def test_two_structurally_matching_witnesses_remain_ambiguous_even_if_registry_admits_both(self):
        local = bind(
            claim("c1", 980),
            ref_id="local",
            source_id="screen:1",
            sequence=1,
            clock_domain="clock:a",
        )
        remote = bind(
            claim("c2", 480),
            ref_id="remote",
            source_id="camera:1",
            sequence=1,
            offset=500,
            clock_domain="clock:b",
        )
        first = witness(local, remote, alignment_id="alignment:1")
        second = witness(local, remote, alignment_id="alignment:2")
        window = build_observation_window(
            refs=(local, remote),
            reference_now_ns=1_000,
            max_join_skew_ns=30,
            max_clock_uncertainty_ns=5,
            provenance_refs=P,
            alignment_witnesses=(first, second),
            alignment_admission_registry=registry_for(first, second),
        )
        self.assertEqual(window.current_ref_ids, ())
        self.assertEqual(set(window.unaligned_ref_ids), {"local", "remote"})
        self.assertEqual(window.alignment_witness_refs, ())
        self.assertEqual(window.alignment_admission_refs, ())

    def test_registry_authority_identity_changes_window_identity(self):
        local = bind(
            claim("c1", 980),
            ref_id="local",
            source_id="screen:1",
            sequence=1,
            clock_domain="clock:a",
        )
        remote = bind(
            claim("c2", 480),
            ref_id="remote",
            source_id="camera:1",
            sequence=1,
            offset=500,
            clock_domain="clock:b",
        )
        alignment = witness(local, remote)
        first_registry = registry_for(alignment, authority_receipt_sha256="4" * 64)
        second_registry = registry_for(alignment, authority_receipt_sha256="5" * 64)
        first = build_observation_window(
            refs=(local, remote),
            reference_now_ns=1_000,
            max_join_skew_ns=30,
            max_clock_uncertainty_ns=5,
            provenance_refs=P,
            alignment_witnesses=(alignment,),
            alignment_admission_registry=first_registry,
        )
        second = build_observation_window(
            refs=(local, remote),
            reference_now_ns=1_000,
            max_join_skew_ns=30,
            max_clock_uncertainty_ns=5,
            provenance_refs=P,
            alignment_witnesses=(alignment,),
            alignment_admission_registry=second_registry,
        )
        self.assertNotEqual(first.window_id, second.window_id)
        self.assertNotEqual(first.sha256(), second.sha256())

    def test_shared_clock_still_obeys_join_skew(self):
        a = bind(
            claim("c1", 900), ref_id="a", source_id="screen:1", sequence=1,
            freshness=500, clock_domain="clock:shared"
        )
        b = bind(
            claim("c2", 990), ref_id="b", source_id="camera:1", sequence=1,
            freshness=500, clock_domain="clock:shared"
        )
        window = build_observation_window(
            refs=(a, b), reference_now_ns=1_000, max_join_skew_ns=50,
            max_clock_uncertainty_ns=10, provenance_refs=P
        )
        self.assertEqual(window.current_ref_ids, ())
        self.assertEqual(set(window.unaligned_ref_ids), {"a", "b"})

    def test_source_generation_change_is_unaligned_without_relation(self):
        first = bind(
            claim("c1", 980, source_generation=1), ref_id="g1", source_id="screen:1",
            sequence=1, clock_domain="clock:screen"
        )
        rebound = bind(
            claim("c2", 985, source_generation=2), ref_id="g2", source_id="screen:1",
            sequence=2, clock_domain="clock:screen"
        )
        window = build_observation_window(
            refs=(first, rebound), reference_now_ns=1_000, max_join_skew_ns=20,
            max_clock_uncertainty_ns=5, provenance_refs=P
        )
        self.assertEqual(window.current_ref_ids, ())
        self.assertEqual(set(window.unaligned_ref_ids), {"g1", "g2"})

    def test_future_time_and_source_time_regression_fail_closed(self):
        future = bind(claim("c1", 1_010), ref_id="future", source_id="screen:1", sequence=1)
        window = build_observation_window(
            refs=(future,), reference_now_ns=1_000, max_join_skew_ns=20,
            max_clock_uncertainty_ns=10, provenance_refs=P
        )
        self.assertEqual(window.unaligned_ref_ids, ("future",))

        later_sequence_older_time = bind(
            claim("c3", 90), ref_id="r2", source_id="screen:2", sequence=2
        )
        earlier = bind(claim("c2", 100), ref_id="r1", source_id="screen:2", sequence=1)
        with self.assertRaisesRegex(PerceptionTemporalError, "source time regressed"):
            build_observation_window(
                refs=(later_sequence_older_time, earlier), reference_now_ns=150,
                max_join_skew_ns=100, max_clock_uncertainty_ns=10, provenance_refs=P
            )

    def test_arrival_permutation_does_not_change_window_identity(self):
        a = bind(
            claim("c1", 980), ref_id="a", source_id="screen:1", sequence=1,
            clock_domain="clock:shared"
        )
        b = bind(
            claim("c2", 985), ref_id="b", source_id="camera:1", sequence=1,
            clock_domain="clock:shared"
        )
        first = build_observation_window(
            refs=(a, b), reference_now_ns=1_000, max_join_skew_ns=20,
            max_clock_uncertainty_ns=5, provenance_refs=P
        )
        second = build_observation_window(
            refs=(b, a), reference_now_ns=1_000, max_join_skew_ns=20,
            max_clock_uncertainty_ns=5, provenance_refs=P
        )
        self.assertEqual(first.window_id, second.window_id)
        self.assertEqual(first.sha256(), second.sha256())

    def test_window_never_mints_admission_truth_effect_or_completion_authority(self):
        a = bind(claim("c1", 980), ref_id="a", source_id="screen:1", sequence=1)
        window = build_observation_window(
            refs=(a,), reference_now_ns=1_000, max_join_skew_ns=20,
            max_clock_uncertainty_ns=5, provenance_refs=P
        )
        payload = window.as_dict()
        self.assertEqual(payload["world_truth_authority"], "NONE")
        self.assertEqual(payload["effect_authority"], "NONE")
        self.assertEqual(payload["completion_authority"], "NONE")
        self.assertFalse(payload["resolves_semantic_disagreement"])
        self.assertTrue(payload["unproven_cross_clock_is_unaligned"])
        self.assertFalse(payload["numeric_reference_offset_self_attests_alignment"])
        self.assertFalse(payload["raw_clock_alignment_witness_is_admission_authority"])
        self.assertFalse(payload["bare_witness_digest_is_admission_authority"])
        self.assertTrue(payload["requires_upstream_admission_registry"])
        self.assertFalse(payload["registry_receipt_authenticated_here"])


if __name__ == "__main__":
    unittest.main()
