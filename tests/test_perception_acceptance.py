import unittest

from frankenstein2.perception_acceptance import (
    ASSESSMENT_BLOCKED,
    ASSESSMENT_ELIGIBLE_FOR_FINAL_REVIEW,
    ASSESSMENT_FAIL_CLOSED,
    CASE_RESULT_FAIL,
    CASE_RESULT_NOT_RUN,
    CASE_RESULT_PASS,
    REQUIRED_CASE_IDS,
    REQUIRED_UPSTREAM_WORKPACKAGES,
    PerceptionAcceptanceCase,
    PerceptionAcceptanceError,
    UpstreamAcceptance,
    assess_perception_acceptance,
)


H = "0" * 64


def upstreams(*, omit=()):
    return tuple(
        UpstreamAcceptance(
            workpackage_id=workpackage_id,
            accepted_scope=f"{workpackage_id}:REPOSITORY_HOSTED_COMPONENT_CI_ONLY",
            receipt_ref=f"workpackages/receipts/{workpackage_id}.json",
            receipt_sha256=H,
        )
        for workpackage_id in REQUIRED_UPSTREAM_WORKPACKAGES
        if workpackage_id not in set(omit)
    )


def cases(*, overrides=None, local_synthetic=False):
    overrides = overrides or {}
    values = []
    for case_id in REQUIRED_CASE_IDS:
        values.append(
            PerceptionAcceptanceCase(
                case_id=case_id,
                result=overrides.get(case_id, CASE_RESULT_PASS),
                evidence_refs=(f"runs/wp714/{case_id}.json",),
                synthetic=(
                    local_synthetic
                    if case_id == "LOCAL_REAL_DEVICE_OS_PERMISSION_ACCEPTANCE"
                    else True
                ),
            )
        )
    return tuple(values)


class PerceptionAcceptanceTests(unittest.TestCase):
    def test_missing_upstream_acceptance_blocks(self):
        assessment = assess_perception_acceptance(
            upstream_acceptances=upstreams(omit={"F2-WP-712"}),
            cases=cases(),
        )
        self.assertEqual(assessment.assessment, ASSESSMENT_BLOCKED)
        self.assertEqual(assessment.dependency_blockers, ("F2-WP-712",))
        self.assertFalse(assessment.terminal_acceptance_minted)
        self.assertFalse(assessment.as_dict()["whole_system_acceptance"])

    def test_not_run_case_blocks(self):
        assessment = assess_perception_acceptance(
            upstream_acceptances=upstreams(),
            cases=cases(overrides={"CLOCK_SKEW_NO_FALSE_CONTEMPORANEITY": CASE_RESULT_NOT_RUN}),
        )
        self.assertEqual(assessment.assessment, ASSESSMENT_BLOCKED)
        self.assertIn("CLOCK_SKEW_NO_FALSE_CONTEMPORANEITY", assessment.case_blockers)

    def test_synthetic_local_device_result_cannot_satisfy_local_gate(self):
        assessment = assess_perception_acceptance(
            upstream_acceptances=upstreams(),
            cases=cases(local_synthetic=True),
        )
        self.assertEqual(assessment.assessment, ASSESSMENT_BLOCKED)
        self.assertFalse(assessment.local_hardware_receipt_bound)
        self.assertIn(
            "LOCAL_REAL_DEVICE_OS_PERMISSION_ACCEPTANCE:NON_SYNTHETIC_REQUIRED",
            assessment.case_blockers,
        )
        self.assertFalse(assessment.terminal_acceptance_minted)

    def test_any_failed_case_dominates(self):
        assessment = assess_perception_acceptance(
            upstream_acceptances=upstreams(omit={"F2-WP-708"}),
            cases=cases(overrides={"RESOURCE_PRESSURE_DEGRADES_PERCEPTION_FIRST": CASE_RESULT_FAIL}),
        )
        self.assertEqual(assessment.assessment, ASSESSMENT_FAIL_CLOSED)
        self.assertEqual(
            assessment.failed_cases,
            ("RESOURCE_PRESSURE_DEGRADES_PERCEPTION_FIRST",),
        )
        self.assertFalse(assessment.terminal_acceptance_minted)

    def test_complete_evidence_is_only_eligible_for_final_review(self):
        assessment = assess_perception_acceptance(
            upstream_acceptances=upstreams(),
            cases=cases(local_synthetic=False),
        )
        self.assertEqual(assessment.assessment, ASSESSMENT_ELIGIBLE_FOR_FINAL_REVIEW)
        self.assertTrue(assessment.local_hardware_receipt_bound)
        self.assertEqual(assessment.dependency_blockers, ())
        self.assertEqual(assessment.case_blockers, ())
        self.assertEqual(assessment.failed_cases, ())
        self.assertFalse(assessment.terminal_acceptance_minted)
        self.assertEqual(assessment.as_dict()["effect_authority"], "NONE")
        self.assertEqual(assessment.as_dict()["completion_authority"], "NONE")

    def test_case_order_does_not_change_provenance_digest(self):
        ordered = cases()
        reversed_cases = tuple(reversed(ordered))
        a = assess_perception_acceptance(
            upstream_acceptances=upstreams(),
            cases=ordered,
        )
        b = assess_perception_acceptance(
            upstream_acceptances=tuple(reversed(upstreams())),
            cases=reversed_cases,
        )
        self.assertEqual(a.provenance_digest, b.provenance_digest)
        self.assertEqual(a.sha256(), b.sha256())

    def test_duplicate_case_ids_fail_closed(self):
        duplicate = cases() + (cases()[0],)
        with self.assertRaises(PerceptionAcceptanceError):
            assess_perception_acceptance(
                upstream_acceptances=upstreams(),
                cases=duplicate,
            )

    def test_unknown_case_id_rejected_at_construction(self):
        with self.assertRaises(PerceptionAcceptanceError):
            PerceptionAcceptanceCase(
                case_id="MADE_UP_PASS",
                result=CASE_RESULT_PASS,
                evidence_refs=("runs/fake.json",),
                synthetic=True,
            )

    def test_unexpected_upstream_cannot_self_admit(self):
        unexpected = upstreams() + (
            UpstreamAcceptance(
                workpackage_id="F2-WP-999",
                accepted_scope="MADE_UP",
                receipt_ref="workpackages/receipts/fake.json",
                receipt_sha256=H,
            ),
        )
        with self.assertRaises(PerceptionAcceptanceError):
            assess_perception_acceptance(
                upstream_acceptances=unexpected,
                cases=cases(),
            )


if __name__ == "__main__":
    unittest.main()
