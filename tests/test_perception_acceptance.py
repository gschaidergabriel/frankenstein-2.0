import unittest

from frankenstein2.perception_acceptance import (
    ASSESSMENT_BLOCKED,
    ASSESSMENT_ELIGIBLE_FOR_FINAL_REVIEW,
    ASSESSMENT_FAIL_CLOSED,
    CASE_RESULT_FAIL,
    CASE_RESULT_NOT_RUN,
    CASE_RESULT_PASS,
    EXPECTED_UPSTREAM_ACCEPTANCES,
    REQUIRED_CASE_IDS,
    REQUIRED_UPSTREAM_WORKPACKAGES,
    PerceptionAcceptanceCase,
    PerceptionAcceptanceError,
    UpstreamAcceptance,
    assess_perception_acceptance,
)

H = "1" * 64


def upstreams(*, omit=(), overrides=None):
    overrides = overrides or {}
    values = []
    for workpackage_id in REQUIRED_UPSTREAM_WORKPACKAGES:
        if workpackage_id in set(omit):
            continue
        expected = dict(EXPECTED_UPSTREAM_ACCEPTANCES[workpackage_id])
        expected.update(overrides.get(workpackage_id, {}))
        values.append(
            UpstreamAcceptance(
                workpackage_id=workpackage_id,
                generation=expected["generation"],
                claim_id=expected["claim_id"],
                accepted_scope=expected["accepted_scope"],
                receipt_ref=expected["receipt_ref"],
                receipt_sha256=H,
            )
        )
    return tuple(values)


def cases(*, overrides=None, local_synthetic=False, clock_synthetic=False):
    overrides = overrides or {}
    values = []
    for case_id in REQUIRED_CASE_IDS:
        if case_id == "LOCAL_REAL_DEVICE_OS_PERMISSION_ACCEPTANCE":
            synthetic = local_synthetic
        elif case_id == "CLOCK_ALIGNMENT_WITNESS_EVIDENCE_DEREFERENCE":
            synthetic = clock_synthetic
        else:
            synthetic = True
        values.append(
            PerceptionAcceptanceCase(
                case_id=case_id,
                result=overrides.get(case_id, CASE_RESULT_PASS),
                evidence_refs=(f"runs/wp714/{case_id}.json",),
                synthetic=synthetic,
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

    def test_superseded_wp711_generation_one_receipt_cannot_satisfy_current_dependency(self):
        assessment = assess_perception_acceptance(
            upstream_acceptances=upstreams(
                overrides={
                    "F2-WP-711": {
                        "generation": 1,
                        "claim_id": "F2-WP-711-G1-GPT56SOL-TEMPORAL-OBSERVATION-WINDOW-20260829",
                        "accepted_scope": "TEMPORAL_OBSERVATION_WINDOW_CROSS_SOURCE_ALIGNMENT_REPOSITORY_HOSTED_COMPONENT_CI_ONLY",
                        "receipt_ref": "workpackages/receipts/F2-WP-711_G1_TEMPORAL_OBSERVATION_WINDOW_MAIN_CI_STALE.json",
                    }
                }
            ),
            cases=cases(),
        )
        self.assertEqual(assessment.assessment, ASSESSMENT_BLOCKED)
        self.assertIn("F2-WP-711:CURRENT_ACCEPTANCE_IDENTITY_MISMATCH", assessment.dependency_blockers)

    def test_superseded_wp711_generation_two_receipt_cannot_satisfy_generation_three_dependency(self):
        assessment = assess_perception_acceptance(
            upstream_acceptances=upstreams(
                overrides={
                    "F2-WP-711": {
                        "generation": 2,
                        "claim_id": "F2-WP-711-G2-GPT56SOL-CLOCK-ALIGNMENT-WITNESS-REPAIR-20260829",
                        "accepted_scope": "TEMPORAL_OBSERVATION_WINDOW_PROVENANCE_BOUND_CLOCK_ALIGNMENT_REPAIR_REPOSITORY_HOSTED_COMPONENT_CI_ONLY",
                        "receipt_ref": "workpackages/receipts/F2-WP-711_G2_CLOCK_ALIGNMENT_WITNESS_MAIN_CI_33250544513.json",
                    }
                }
            ),
            cases=cases(),
        )
        self.assertEqual(assessment.assessment, ASSESSMENT_BLOCKED)
        self.assertIn("F2-WP-711:CURRENT_ACCEPTANCE_IDENTITY_MISMATCH", assessment.dependency_blockers)

    def test_caller_invented_scope_cannot_self_admit_current_workpackage(self):
        assessment = assess_perception_acceptance(
            upstream_acceptances=upstreams(
                overrides={"F2-WP-710": {"accepted_scope": "CALLER_SAYS_ACCEPTED"}}
            ),
            cases=cases(),
        )
        self.assertEqual(assessment.assessment, ASSESSMENT_BLOCKED)
        self.assertIn("F2-WP-710:CURRENT_ACCEPTANCE_IDENTITY_MISMATCH", assessment.dependency_blockers)

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

    def test_synthetic_clock_witness_dereference_cannot_satisfy_alignment_gate(self):
        assessment = assess_perception_acceptance(
            upstream_acceptances=upstreams(),
            cases=cases(clock_synthetic=True),
        )
        self.assertEqual(assessment.assessment, ASSESSMENT_BLOCKED)
        self.assertFalse(assessment.alignment_witness_evidence_bound)
        self.assertIn(
            "CLOCK_ALIGNMENT_WITNESS_EVIDENCE_DEREFERENCE:NON_SYNTHETIC_REQUIRED",
            assessment.case_blockers,
        )
        self.assertFalse(assessment.terminal_acceptance_minted)

    def test_any_failed_case_dominates(self):
        assessment = assess_perception_acceptance(
            upstream_acceptances=upstreams(omit={"F2-WP-708"}),
            cases=cases(overrides={"RESOURCE_PRESSURE_DEGRADES_PERCEPTION_FIRST": CASE_RESULT_FAIL}),
        )
        self.assertEqual(assessment.assessment, ASSESSMENT_FAIL_CLOSED)
        self.assertEqual(assessment.failed_cases, ("RESOURCE_PRESSURE_DEGRADES_PERCEPTION_FIRST",))
        self.assertFalse(assessment.terminal_acceptance_minted)

    def test_complete_evidence_is_only_eligible_for_final_review(self):
        assessment = assess_perception_acceptance(
            upstream_acceptances=upstreams(),
            cases=cases(local_synthetic=False, clock_synthetic=False),
        )
        self.assertEqual(assessment.assessment, ASSESSMENT_ELIGIBLE_FOR_FINAL_REVIEW)
        self.assertTrue(assessment.local_hardware_receipt_bound)
        self.assertTrue(assessment.alignment_witness_evidence_bound)
        self.assertEqual(assessment.dependency_blockers, ())
        self.assertEqual(assessment.case_blockers, ())
        self.assertEqual(assessment.failed_cases, ())
        self.assertFalse(assessment.terminal_acceptance_minted)
        self.assertEqual(assessment.as_dict()["effect_authority"], "NONE")
        self.assertEqual(assessment.as_dict()["completion_authority"], "NONE")

    def test_case_order_does_not_change_provenance_digest(self):
        ordered = cases()
        reversed_cases = tuple(reversed(ordered))
        a = assess_perception_acceptance(upstream_acceptances=upstreams(), cases=ordered)
        b = assess_perception_acceptance(
            upstream_acceptances=tuple(reversed(upstreams())),
            cases=reversed_cases,
        )
        self.assertEqual(a.provenance_digest, b.provenance_digest)
        self.assertEqual(a.sha256(), b.sha256())

    def test_duplicate_case_ids_fail_closed(self):
        duplicate = cases() + (cases()[0],)
        with self.assertRaises(PerceptionAcceptanceError):
            assess_perception_acceptance(upstream_acceptances=upstreams(), cases=duplicate)

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
                generation=1,
                claim_id="F2-WP-999-G1-FAKE",
                accepted_scope="MADE_UP",
                receipt_ref="workpackages/receipts/fake.json",
                receipt_sha256=H,
            ),
        )
        with self.assertRaises(PerceptionAcceptanceError):
            assess_perception_acceptance(upstream_acceptances=unexpected, cases=cases())

    def test_current_upstream_identity_table_covers_exact_required_set(self):
        self.assertEqual(set(EXPECTED_UPSTREAM_ACCEPTANCES), set(REQUIRED_UPSTREAM_WORKPACKAGES))
        self.assertEqual(EXPECTED_UPSTREAM_ACCEPTANCES["F2-WP-711"]["generation"], 3)
        self.assertEqual(
            EXPECTED_UPSTREAM_ACCEPTANCES["F2-WP-711"]["claim_id"],
            "F2-WP-711-G3-GPT56SOL-WITNESS-ADMISSION-FENCE-20260829",
        )
        self.assertIn(
            "SEPARATELY_ADMITTED_CLOCK_WITNESS",
            EXPECTED_UPSTREAM_ACCEPTANCES["F2-WP-711"]["accepted_scope"],
        )


if __name__ == "__main__":
    unittest.main()
