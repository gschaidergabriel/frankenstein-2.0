from __future__ import annotations

import dataclasses
import unittest

from frankenstein2.epistemic_perception import EpistemicPerceptClaim
from frankenstein2.presence_kernel import (
    ABSENT,
    CONFLICT,
    FRESH,
    INSUFFICIENT_CONFIDENCE,
    PRESENT,
    STALE,
    UNKNOWN,
    FreshPresenceSnapshot,
    PresenceFreshnessPolicy,
    PresenceKernelError,
    PresenceSourceBinding,
    build_fresh_presence_snapshot,
)


D64_A = "a" * 64
D64_B = "b" * 64


class ForgedClaim(EpistemicPerceptClaim):
    pass


class PresenceKernelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 10_000_000
        self.policy = PresenceFreshnessPolicy(
            policy_id="presence-policy-1",
            generation=1,
            semantic_key="person.presence",
            allowed_modalities=("camera-front", "screen-presence", "camera-side"),
            max_age_ns=1_000,
            min_confidence_micros=500_000,
            max_source_slots=4,
            provenance_refs=("policy:owner",),
        )

    def claim(
        self,
        *,
        claim_id: str,
        value: object,
        source_time_ns: int | None = None,
        confidence_micros: int = 900_000,
        epistemic_type: str = "OBSERVED",
        semantic_key: str = "person.presence",
        modality: str = "camera-front",
        generation: int = 1,
    ) -> EpistemicPerceptClaim:
        return EpistemicPerceptClaim(
            claim_id=claim_id,
            semantic_key=semantic_key,
            modality=modality,
            epistemic_type=epistemic_type,
            value=value,
            confidence_micros=confidence_micros,
            source_generation=generation,
            source_time_ns=self.now - 100 if source_time_ns is None else source_time_ns,
            provenance_refs=(f"evidence:{claim_id}",),
            upstream_retina_assessment_sha256=D64_A if epistemic_type == "OBSERVED" else None,
        )

    @staticmethod
    def binding(source_id: str, worker_id: str, claim: EpistemicPerceptClaim) -> PresenceSourceBinding:
        return PresenceSourceBinding(
            source_id=source_id,
            worker_id=worker_id,
            claim=claim,
            expected_claim_sha256=claim.sha256(),
        )

    def build(self, *bindings: PresenceSourceBinding, policy: PresenceFreshnessPolicy | None = None) -> FreshPresenceSnapshot:
        policy = policy or self.policy
        return build_fresh_presence_snapshot(
            snapshot_id="presence-snapshot-1",
            evaluated_monotonic_ns=self.now,
            policy=policy,
            expected_policy_sha256=policy.sha256(),
            sources=tuple(bindings),
            provenance_refs=("cycle:presence-test",),
        )

    def test_single_fresh_present_is_present(self) -> None:
        claim = self.claim(claim_id="c-present", value=True)
        snapshot = self.build(self.binding("retina-1", "worker-1", claim))
        self.assertEqual(snapshot.presence_status, PRESENT)
        self.assertEqual(snapshot.fresh_present_claim_sha256s, (claim.sha256(),))
        self.assertEqual(snapshot.fresh_absent_claim_sha256s, ())
        self.assertEqual(snapshot.source_evidence[0].freshness_status, FRESH)
        self.assertFalse(snapshot.as_dict()["raw_frame_present"])
        self.assertEqual(snapshot.as_dict()["world_truth_authority"], "NONE")
        self.assertEqual(snapshot.as_dict()["effect_authority"], "NONE")

    def test_single_fresh_absent_is_absent(self) -> None:
        claim = self.claim(claim_id="c-absent", value=False)
        snapshot = self.build(self.binding("retina-1", "worker-1", claim))
        self.assertEqual(snapshot.presence_status, ABSENT)
        self.assertEqual(snapshot.fresh_absent_claim_sha256s, (claim.sha256(),))

    def test_multiple_agreeing_sources_are_deterministic_and_order_independent(self) -> None:
        first = self.claim(claim_id="c-a", value=True, modality="camera-front")
        second = self.claim(claim_id="c-b", value=True, modality="camera-side")
        a = self.binding("retina-a", "worker-a", first)
        b = self.binding("retina-b", "worker-b", second)
        forward = self.build(a, b)
        reverse = self.build(b, a)
        self.assertEqual(forward.presence_status, PRESENT)
        self.assertEqual(forward.sha256(), reverse.sha256())
        self.assertEqual(tuple(row.source_id for row in forward.source_evidence), ("retina-a", "retina-b"))
        self.assertEqual(forward.as_dict()["max_supported_parallel_source_slots"], 4)

    def test_disagreeing_fresh_sources_preserve_conflict(self) -> None:
        present = self.claim(claim_id="c-present", value=True, modality="camera-front")
        absent = self.claim(claim_id="c-absent", value=False, modality="camera-side")
        snapshot = self.build(
            self.binding("retina-a", "worker-a", present),
            self.binding("retina-b", "worker-b", absent),
        )
        self.assertEqual(snapshot.presence_status, CONFLICT)
        self.assertTrue(snapshot.as_dict()["conflict_is_first_class"])
        self.assertEqual(snapshot.fresh_present_claim_sha256s, (present.sha256(),))
        self.assertEqual(snapshot.fresh_absent_claim_sha256s, (absent.sha256(),))

    def test_stale_only_stays_unknown(self) -> None:
        claim = self.claim(claim_id="c-stale", value=True, source_time_ns=self.now - 1_001)
        snapshot = self.build(self.binding("retina-1", "worker-1", claim))
        self.assertEqual(snapshot.presence_status, UNKNOWN)
        self.assertEqual(snapshot.stale_source_ids, ("retina-1",))
        self.assertEqual(snapshot.source_evidence[0].freshness_status, STALE)
        self.assertTrue(snapshot.as_dict()["unknown_is_first_class"])

    def test_low_confidence_only_stays_unknown(self) -> None:
        claim = self.claim(claim_id="c-low", value=True, confidence_micros=499_999)
        snapshot = self.build(self.binding("retina-1", "worker-1", claim))
        self.assertEqual(snapshot.presence_status, UNKNOWN)
        self.assertEqual(snapshot.insufficient_confidence_source_ids, ("retina-1",))
        self.assertEqual(snapshot.source_evidence[0].freshness_status, INSUFFICIENT_CONFIDENCE)

    def test_stale_disagreement_does_not_create_conflict_with_fresh_evidence(self) -> None:
        fresh = self.claim(claim_id="fresh", value=True, modality="camera-front")
        stale = self.claim(
            claim_id="stale",
            value=False,
            modality="camera-side",
            source_time_ns=self.now - 5_000,
        )
        snapshot = self.build(
            self.binding("retina-fresh", "worker-a", fresh),
            self.binding("retina-stale", "worker-b", stale),
        )
        self.assertEqual(snapshot.presence_status, PRESENT)
        self.assertEqual(snapshot.stale_source_ids, ("retina-stale",))

    def test_inferred_or_retrieved_claim_cannot_mint_current_presence(self) -> None:
        for kind in ("INFERRED", "RETRIEVED"):
            with self.subTest(kind=kind):
                claim = self.claim(claim_id=f"c-{kind.lower()}", value=True, epistemic_type=kind)
                with self.assertRaisesRegex(PresenceKernelError, "only OBSERVED"):
                    self.build(self.binding("retina-1", "worker-1", claim))

    def test_future_timestamp_fails_closed(self) -> None:
        claim = self.claim(claim_id="c-future", value=True, source_time_ns=self.now + 1)
        with self.assertRaisesRegex(PresenceKernelError, "future"):
            self.build(self.binding("retina-1", "worker-1", claim))

    def test_digest_mismatch_fails_at_binding(self) -> None:
        claim = self.claim(claim_id="c-digest", value=True)
        with self.assertRaisesRegex(PresenceKernelError, "claim digest mismatch"):
            PresenceSourceBinding(
                source_id="retina-1",
                worker_id="worker-1",
                claim=claim,
                expected_claim_sha256=D64_B,
            )

    def test_exact_concrete_claim_type_is_required(self) -> None:
        forged = ForgedClaim(
            claim_id="forged",
            semantic_key="person.presence",
            modality="camera-front",
            epistemic_type="OBSERVED",
            value=True,
            confidence_micros=900_000,
            source_generation=1,
            source_time_ns=self.now - 1,
            provenance_refs=("evidence:forged",),
            upstream_retina_assessment_sha256=D64_A,
        )
        with self.assertRaisesRegex(PresenceKernelError, "concrete EpistemicPerceptClaim"):
            PresenceSourceBinding(
                source_id="retina-1",
                worker_id="worker-1",
                claim=forged,
                expected_claim_sha256=forged.sha256(),
            )

    def test_duplicate_source_or_duplicate_observation_alias_fails_closed(self) -> None:
        first = self.claim(claim_id="c-one", value=True, modality="camera-front")
        second = self.claim(claim_id="c-two", value=True, modality="camera-side")
        with self.assertRaisesRegex(PresenceKernelError, "source_id must be unique"):
            self.build(
                self.binding("retina-1", "worker-a", first),
                self.binding("retina-1", "worker-b", second),
            )
        with self.assertRaisesRegex(PresenceKernelError, "same observation claim"):
            self.build(
                self.binding("retina-1", "worker-a", first),
                self.binding("retina-2", "worker-b", first),
            )

    def test_policy_and_hard_slot_ceiling_are_enforced(self) -> None:
        narrow = dataclasses.replace(self.policy, max_source_slots=2)
        claims = [
            self.claim(claim_id=f"c-{i}", value=True, modality="camera-front", generation=i + 1)
            for i in range(5)
        ]
        bindings = [self.binding(f"retina-{i}", f"worker-{i}", claim) for i, claim in enumerate(claims)]
        with self.assertRaisesRegex(PresenceKernelError, "source count exceeds"):
            self.build(*bindings[:3], policy=narrow)
        with self.assertRaisesRegex(PresenceKernelError, "max_source_slots"):
            dataclasses.replace(self.policy, max_source_slots=5)
        with self.assertRaisesRegex(PresenceKernelError, "source count exceeds"):
            self.build(*bindings)

    def test_semantic_modality_and_bool_boundaries_fail_closed(self) -> None:
        wrong_key = self.claim(claim_id="wrong-key", value=True, semantic_key="person.identity")
        with self.assertRaisesRegex(PresenceKernelError, "semantic_key"):
            self.build(self.binding("retina-1", "worker-1", wrong_key))
        wrong_modality = self.claim(claim_id="wrong-modality", value=True, modality="microphone")
        with self.assertRaisesRegex(PresenceKernelError, "modality"):
            self.build(self.binding("retina-1", "worker-1", wrong_modality))
        non_bool = self.claim(claim_id="non-bool", value=1)
        with self.assertRaisesRegex(PresenceKernelError, "exact bool"):
            self.build(self.binding("retina-1", "worker-1", non_bool))

    def test_policy_digest_is_bound_exactly(self) -> None:
        claim = self.claim(claim_id="c-policy", value=True)
        with self.assertRaisesRegex(PresenceKernelError, "policy digest mismatch"):
            build_fresh_presence_snapshot(
                snapshot_id="presence-snapshot-1",
                evaluated_monotonic_ns=self.now,
                policy=self.policy,
                expected_policy_sha256=D64_B,
                sources=(self.binding("retina-1", "worker-1", claim),),
                provenance_refs=("cycle:presence-test",),
            )

    def test_direct_snapshot_tampering_cannot_claim_present_without_fresh_evidence(self) -> None:
        claim = self.claim(claim_id="c-stale-direct", value=True, source_time_ns=self.now - 5_000)
        unknown = self.build(self.binding("retina-1", "worker-1", claim))
        with self.assertRaisesRegex(PresenceKernelError, "exact fresh-evidence state"):
            dataclasses.replace(unknown, presence_status=PRESENT)


if __name__ == "__main__":
    unittest.main()
