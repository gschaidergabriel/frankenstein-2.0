from __future__ import annotations

import unittest

from frankenstein2.perception_control import (
    PerceptionControlError,
    PerceptionControlResult,
    PerceptionDependency,
    PerceptionHeadPolicy,
    PerceptionPolicyRegistry,
    evaluate_perception_head,
)

REFS = ("review:wp702-pr371-producer-lineage",)


class WP702PR371ProducerLineageFalsifier(unittest.TestCase):
    def test_non_null_real_policy_digest_still_cannot_self_attest_ok(self) -> None:
        policy = PerceptionHeadPolicy(
            head_id="protected.head",
            generation=7,
            tier="COMPUTE_OFF",
            enabled=True,
            memory_allowed=True,
            provenance_refs=REFS,
        )
        registry = PerceptionPolicyRegistry(
            registry_id="registry:wp702-pr371-review",
            generation=11,
            heads=(policy,),
            dependencies=(PerceptionDependency(head_id="protected.head", depends_on=()),),
            provenance_refs=REFS,
        )

        calls: list[str] = []
        evaluated = evaluate_perception_head(
            evaluation_id="eval:canonical",
            registry=registry,
            expected_registry_sha256=registry.sha256(),
            head_id="protected.head",
            compute_fn=lambda: (calls.append("must-not-run") or {"forged": True}, 1_000_000),
            provenance_refs=REFS,
        )
        self.assertEqual(calls, [])
        self.assertEqual(evaluated.status, "NOT_COMPUTED")

        # PR371 requires policy_sha256 to be present for evidence-bearing states.
        # Use the exact real non-null digest and prove that presence alone still does
        # not establish evaluator producer lineage or policy-semantic consistency.
        with self.assertRaises(PerceptionControlError):
            PerceptionControlResult(
                evaluation_id="eval:forged",
                head_id="protected.head",
                registry_sha256=registry.sha256(),
                policy_sha256=policy.sha256(),
                status="OK",
                value={"forged": True},
                confidence_micros=1_000_000,
                computed=True,
                internal_computed=True,
                egress_allowed=True,
                memory_match_allowed=True,
                persistence_allowed=True,
                blocked_by=None,
                reason="caller_forged_policy_bypass",
                provenance_refs=("caller:self-attested",),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
