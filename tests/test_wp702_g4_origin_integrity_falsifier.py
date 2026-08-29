import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import frankenstein2.perception_control as perception_control  # noqa: E402
from frankenstein2.perception_control import (  # noqa: E402
    PerceptionControlError,
    PerceptionControlResult,
    PerceptionDependency,
    PerceptionHeadPolicy,
    PerceptionPolicyRegistry,
    evaluate_perception_head,
)

REFS = ("review:wp702-g4-origin-integrity",)


def policy(head_id, tier="ON", *, enabled=True, memory_allowed=True):
    return PerceptionHeadPolicy(
        head_id=head_id,
        generation=1,
        tier=tier,
        enabled=enabled,
        memory_allowed=memory_allowed,
        provenance_refs=REFS,
    )


def registry(*heads):
    return PerceptionPolicyRegistry(
        registry_id="review-registry",
        generation=1,
        heads=tuple(heads),
        dependencies=tuple(
            PerceptionDependency(head_id=head.head_id, depends_on=()) for head in heads
        ),
        provenance_refs=REFS,
    )


def evaluate(reg, head_id, fn):
    return evaluate_perception_head(
        evaluation_id=f"review-eval-{head_id}",
        registry=reg,
        expected_registry_sha256=reg.sha256(),
        head_id=head_id,
        compute_fn=fn,
        provenance_refs=REFS,
    )


class WP702G4OriginIntegrityFalsifier(unittest.TestCase):
    """REVIEW_ONLY counterexamples against PR #395's narrow origin-token mechanism.

    These tests claim no WP702 mutation authority. They ask whether a downstream-consumable
    result is actually bound to the evaluator path/current evaluated content, rather than only
    carrying a Python-convention sentinel.
    """

    def test_module_origin_token_cannot_be_reused_to_mint_direct_persistent_result(self):
        protected = policy("protected.head", "COMPUTE_OFF")
        reg = registry(protected)
        calls = []
        canonical = evaluate(
            reg,
            "protected.head",
            lambda: (calls.append("must-not-run") or {"forged": True}, 1_000_000),
        )
        self.assertEqual(calls, [])
        self.assertEqual(canonical.status, "NOT_COMPUTED")
        self.assertFalse(canonical.persistence_allowed)

        # PR #395 places the admission sentinel at module scope. Python privacy is conventional,
        # so a caller in the same process can retrieve that exact object and pass it back through
        # the still-public constructor. The declared producer-lineage boundary should fail closed
        # even when a caller knows implementation details.
        with self.assertRaises(PerceptionControlError):
            PerceptionControlResult(
                _evaluator_origin=perception_control._EVALUATOR_ORIGIN,
                evaluation_id="review-forged-with-reused-origin",
                head_id="protected.head",
                registry_sha256=reg.sha256(),
                policy_sha256=protected.sha256(),
                status="OK",
                value={"forged": True},
                confidence_micros=1_000_000,
                computed=True,
                internal_computed=True,
                egress_allowed=True,
                memory_match_allowed=True,
                persistence_allowed=True,
                blocked_by=None,
                reason="reused_module_origin_token",
                provenance_refs=("caller:self-attested",),
            )

    def test_evaluator_result_cannot_be_post_mutated_into_persistent_authority(self):
        protected = policy("sensitive.head", "MEMORY_OFF")
        reg = registry(protected)
        result = evaluate(reg, "sensitive.head", lambda: ({"same_cycle": True}, 900_000))

        self.assertEqual(result.status, "OK")
        self.assertTrue(result.egress_allowed)
        self.assertFalse(result.memory_match_allowed)
        self.assertFalse(result.persistence_allowed)
        original_digest = result.sha256()

        # frozen=True is not a same-process integrity boundary: object.__setattr__ bypasses the
        # generated FrozenInstanceError path. A producer-origin token that is not content-bound
        # survives while the authority-relevant readout is changed after evaluator validation.
        object.__setattr__(result, "memory_match_allowed", True)
        object.__setattr__(result, "persistence_allowed", True)
        object.__setattr__(result, "reason", "post_evaluation_drift")

        self.assertFalse(
            result.memory_match_allowed,
            "evaluator-origin result was post-mutated after policy validation",
        )
        self.assertFalse(
            result.persistence_allowed,
            "post-evaluation mutation escalated MEMORY_OFF into persistence",
        )
        self.assertEqual(
            result.sha256(),
            original_digest,
            "producer-lineage evidence is not bound to the exact current result content",
        )


if __name__ == "__main__":
    unittest.main()
