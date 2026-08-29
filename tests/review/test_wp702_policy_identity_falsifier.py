"""REVIEW_ONLY falsifier for F2-WP-702 policy-identity closure.

This does not mutate the canonical WP702 implementation. It tests whether the public
PerceptionControlResult contract can be forged into evidence-bearing states without the
immutable policy identity required by the active WP702 claim.
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
REFS = ("review:wp702-policy-identity",)


class WP702PolicyIdentityFalsifier(unittest.TestCase):
    def _result(self, *, status, policy_sha256, value=None, confidence=None,
                computed=True, internal_computed=True, egress=True,
                memory=False, persistence=False, reason="review"):
        return PerceptionControlResult(
            evaluation_id="review-eval",
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

    def test_ok_result_without_policy_identity_must_fail_closed(self):
        with self.assertRaises(PerceptionControlError):
            self._result(
                status="OK",
                policy_sha256=None,
                value=True,
                confidence=900000,
            )

    def test_output_blocked_result_without_policy_identity_must_fail_closed(self):
        with self.assertRaises(PerceptionControlError):
            self._result(
                status="OUTPUT_BLOCKED",
                policy_sha256=None,
                value=None,
                confidence=None,
                computed=True,
                internal_computed=True,
                egress=False,
                reason="output_off_transient_internal_only",
            )

    def test_compute_error_without_policy_identity_must_fail_closed(self):
        with self.assertRaises(PerceptionControlError):
            self._result(
                status="COMPUTE_ERROR",
                policy_sha256=None,
                value=None,
                confidence=None,
                computed=True,
                internal_computed=False,
                egress=False,
                reason="compute_error:RuntimeError",
            )


if __name__ == "__main__":
    unittest.main()
