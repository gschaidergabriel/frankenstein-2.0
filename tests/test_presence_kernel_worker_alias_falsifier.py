from __future__ import annotations

import unittest

from frankenstein2.epistemic_perception import EpistemicPerceptClaim
from frankenstein2.presence_kernel import (
    PresenceFreshnessPolicy,
    PresenceKernelError,
    PresenceSourceBinding,
    build_fresh_presence_snapshot,
)


D64_A = "a" * 64


class PresenceKernelWorkerAliasFalsifier(unittest.TestCase):
    def test_distinct_source_slots_cannot_reuse_one_worker_identity(self) -> None:
        now = 10_000_000
        policy = PresenceFreshnessPolicy(
            policy_id="presence-policy-worker-alias-falsifier",
            generation=1,
            semantic_key="person.presence",
            allowed_modalities=("camera-front", "camera-side"),
            max_age_ns=1_000,
            min_confidence_micros=500_000,
            max_source_slots=4,
            provenance_refs=("review:issue-373",),
        )

        first = EpistemicPerceptClaim(
            claim_id="alias-first",
            semantic_key="person.presence",
            modality="camera-front",
            epistemic_type="OBSERVED",
            value=True,
            confidence_micros=900_000,
            source_generation=1,
            source_time_ns=now - 100,
            provenance_refs=("evidence:alias-first",),
            upstream_retina_assessment_sha256=D64_A,
        )
        second = EpistemicPerceptClaim(
            claim_id="alias-second",
            semantic_key="person.presence",
            modality="camera-side",
            epistemic_type="OBSERVED",
            value=True,
            confidence_micros=900_000,
            source_generation=2,
            source_time_ns=now - 90,
            provenance_refs=("evidence:alias-second",),
            upstream_retina_assessment_sha256=D64_A,
        )

        bindings = (
            PresenceSourceBinding(
                source_id="retina-a",
                worker_id="same-worker",
                claim=first,
                expected_claim_sha256=first.sha256(),
            ),
            PresenceSourceBinding(
                source_id="retina-b",
                worker_id="same-worker",
                claim=second,
                expected_claim_sha256=second.sha256(),
            ),
        )

        with self.assertRaisesRegex(PresenceKernelError, "worker_id must be unique"):
            build_fresh_presence_snapshot(
                snapshot_id="presence-snapshot-worker-alias-falsifier",
                evaluated_monotonic_ns=now,
                policy=policy,
                expected_policy_sha256=policy.sha256(),
                sources=bindings,
                provenance_refs=("review:issue-373",),
            )


if __name__ == "__main__":
    unittest.main()
