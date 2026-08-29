"""CANDIDATE_FALSIFIER for F2-WP-714 generation 1.

This review-only test does not mutate the active WP714 implementation. It demonstrates that
mere presence of an UpstreamAcceptance object is currently sufficient to clear a dependency,
even when its declared scope explicitly says the workpackage is not accepted.
"""
import unittest

from src.frankenstein2.perception_acceptance import (
    ASSESSMENT_BLOCKED,
    ASSESSMENT_ELIGIBLE_FOR_FINAL_REVIEW,
    CASE_RESULT_PASS,
    REQUIRED_CASE_IDS,
    REQUIRED_UPSTREAM_WORKPACKAGES,
    PerceptionAcceptanceCase,
    UpstreamAcceptance,
    assess_perception_acceptance,
)


class WP714UpstreamAcceptanceStatusFalsifier(unittest.TestCase):
    def test_unaccepted_upstream_markers_must_not_become_final_review_eligible(self):
        upstream = tuple(
            UpstreamAcceptance(
                workpackage_id=workpackage_id,
                accepted_scope="NOT_ACCEPTED",
                receipt_ref=f"review-only:not-accepted:{workpackage_id}",
                receipt_sha256=(f"{index:x}" * 64)[:64],
            )
            for index, workpackage_id in enumerate(REQUIRED_UPSTREAM_WORKPACKAGES, start=1)
        )
        cases = tuple(
            PerceptionAcceptanceCase(
                case_id=case_id,
                result=CASE_RESULT_PASS,
                evidence_refs=(f"review-only:{case_id}",),
                synthetic=(case_id != "LOCAL_REAL_DEVICE_OS_PERMISSION_ACCEPTANCE"),
            )
            for case_id in REQUIRED_CASE_IDS
        )

        assessment = assess_perception_acceptance(
            upstream_acceptances=upstream,
            cases=cases,
        )

        self.assertNotEqual(
            assessment.assessment,
            ASSESSMENT_ELIGIBLE_FOR_FINAL_REVIEW,
            "unaccepted upstream markers must never satisfy WP714 dependency acceptance",
        )
        self.assertEqual(assessment.assessment, ASSESSMENT_BLOCKED)


if __name__ == "__main__":
    unittest.main()
