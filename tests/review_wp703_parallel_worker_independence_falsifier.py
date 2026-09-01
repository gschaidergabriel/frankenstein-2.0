from __future__ import annotations

import unittest

from frankenstein2.epistemic_perception import EpistemicPerceptClaim
from frankenstein2.presence_kernel import (
    PresenceFreshnessPolicy,
    PresenceKernelError,
    PresenceSourceBinding,
    build_fresh_presence_snapshot,
)


class WP703ParallelWorkerIndependenceFalsifier(unittest.TestCase):
    """REVIEW_ONLY: prove whether source slots mechanically enforce worker independence."""

    @staticmethod
    def claim(*, claim_id: str, source_time_ns: int) -> EpistemicPerceptClaim:
        return EpistemicPerceptClaim(
            claim_id=claim_id,
            semantic_key="user.present",
            modality="vision",
            epistemic_type="OBSERVED",
            value=True,
            confidence_micros=900_000,
            source_generation=1,
            source_time_ns=source_time_ns,
            provenance_refs=(f"review:{claim_id}",),
            upstream_retina_assessment_sha256="a" * 64,
        )

    def test_same_worker_cannot_occupy_two_independent_retina_slots(self) -> None:
        policy = PresenceFreshnessPolicy(
            policy_id="review-policy-wp703-worker-independence",
            generation=1,
            semantic_key="user.present",
            allowed_modalities=("vision",),
            max_age_ns=1_000,
            min_confidence_micros=500_000,
            max_source_slots=4,
            provenance_refs=("issue:373",),
        )
        first = self.claim(claim_id="observed-camera-a", source_time_ns=9_900)
        second = self.claim(claim_id="observed-camera-b", source_time_ns=9_901)
        sources = (
            PresenceSourceBinding(
                source_id="camera-a",
                worker_id="retina-worker-1",
                claim=first,
                expected_claim_sha256=first.sha256(),
            ),
            PresenceSourceBinding(
                source_id="camera-b",
                worker_id="retina-worker-1",
                claim=second,
                expected_claim_sha256=second.sha256(),
            ),
        )

        # WP703's accepted scope describes one-through-four independent source slots so
        # later Retina workers can contribute in parallel.  If the same worker may occupy
        # two slots without an explicit alias policy, worker independence is not enforced.
        with self.assertRaisesRegex(PresenceKernelError, "worker"):
            build_fresh_presence_snapshot(
                snapshot_id="review-snapshot-wp703-worker-independence",
                evaluated_monotonic_ns=10_000,
                policy=policy,
                expected_policy_sha256=policy.sha256(),
                sources=sources,
                provenance_refs=("issue:373",),
            )


if __name__ == "__main__":
    unittest.main()
