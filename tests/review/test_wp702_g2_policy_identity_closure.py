"""REVIEW_ONLY falsifier for F2-WP-702 G2 policy-identity closure.

This does not mutate canonical WP702 implementation/state. It verifies that the
combined G2 successor rejects evidence-bearing/compute-attempt results that omit
immutable policy identity.
"""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from frankenstein2.perception_control import (  # noqa: E402
    PerceptionControlError,
    PerceptionControlResult,
)

SHA = "0" * 64
REFS = ("review:wp702-g2-policy-identity",)


class WP702G2PolicyIdentityClosure(unittest.TestCase):
    def _result(self, *, status, policy_sha256, value=None, confidence=None,
                computed=True, internal_computed=True, egress=True,
                memory=False, persistence=False, reason="review"):
        return PerceptionControlResult(
            evaluation_id="review-g2-eval",
            head_id="person.presence",
            registry_sha256=SHA,
            policy_sha256=policy_sha256,
            status=status,
            value=value,
            confidence_micros=confidence,
            computed=computed,
            internal_computed=internal_computed,
            egress_allowed=egress,
            memory_match_allowed=memory,
            persistence_allowed=persistence,
            blocked_by=None,
            reason=reason,
            provenance_refs=REFS,
        )

    def test_ok_without_policy_identity_fails_closed(self):
        with self.assertRaises(PerceptionControlError):
            self._result(status="OK", policy_sha256=None, value=True, confidence=900000)

    def test_output_blocked_without_policy_identity_fails_closed(self):
        with self.assertRaises(PerceptionControlError):
            self._result(status="OUTPUT_BLOCKED", policy_sha256=None, value=None,
                         confidence=None, computed=True, internal_computed=True,
                         egress=False, reason="output_off_transient_internal_only")

    def test_compute_error_without_policy_identity_fails_closed(self):
        with self.assertRaises(PerceptionControlError):
            self._result(status="COMPUTE_ERROR", policy_sha256=None, value=None,
                         confidence=None, computed=True, internal_computed=False,
                         egress=False, reason="compute_error:RuntimeError")

    def test_unknown_head_not_computed_may_remain_policyless(self):
        result = self._result(status="NOT_COMPUTED", policy_sha256=None, value=None,
                              confidence=None, computed=False, internal_computed=False,
                              egress=False, reason="unknown_head_not_in_registry")
        self.assertEqual(result.status, "NOT_COMPUTED")
        self.assertIsNone(result.policy_sha256)


if __name__ == "__main__":
    unittest.main()
