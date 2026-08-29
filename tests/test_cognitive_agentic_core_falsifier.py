import unittest

from frankenstein2.cognitive_agentic_core_falsifier import (
    ACCEPTED,
    ACTIVE,
    CAPABILITY_EVIDENCE_SCHEMA,
    EXPLORATION,
    FALSIFIED,
    GOAL_SETTING,
    MODELING,
    NOT_EVALUABLE,
    PLANNING_EXECUTION,
    POLICY_SCHEMA,
    REPORT_SCHEMA,
    SUPPORTED_AT_COMPONENT_SCOPE,
    AgenticCoreFalsifierError,
    AgenticCoreReport,
    CapabilityEvidence,
    FalsifierPolicy,
    evaluate_agentic_core,
)


CAP_TO_WP = {
    EXPLORATION: "F2-WP-802",
    MODELING: "F2-WP-803",
    GOAL_SETTING: "F2-WP-804",
    PLANNING_EXECUTION: "F2-WP-805",
}
CAP_INDEX = {
    EXPLORATION: 1,
    MODELING: 2,
    GOAL_SETTING: 3,
    PLANNING_EXECUTION: 4,
}


def sha(value: int) -> str:
    return format(value, "064x")


def evidence(
    capability: str,
    *,
    state: str = ACCEPTED,
    holdout: str = "heldout-family-A",
    baseline: int = 300_000,
    intervention: int = 700_000,
    samples: int = 20,
    successes: int = 14,
    actions: int = 60,
    receipt_override: str | None = None,
) -> CapabilityEvidence:
    index = CAP_INDEX[capability]
    return CapabilityEvidence(
        CAPABILITY_EVIDENCE_SCHEMA,
        capability,
        CAP_TO_WP[capability],
        1,
        f"claim-{capability.lower()}",
        state,
        f"{capability}_REPOSITORY_HOSTED_COMPONENT_CI_ONLY",
        sha(index),
        receipt_override or sha(index + 100),
        f"benchmark-{capability.lower()}",
        holdout,
        f"baseline-{capability.lower()}",
        baseline,
        intervention,
        samples,
        successes,
        actions,
    )


def complete_evidence() -> tuple[CapabilityEvidence, ...]:
    return tuple(evidence(cap) for cap in (EXPLORATION, MODELING, GOAL_SETTING, PLANNING_EXECUTION))


def policy(**overrides) -> FalsifierPolicy:
    values = dict(
        schema=POLICY_SCHEMA,
        policy_id="wp807-policy-1",
        generation=1,
        min_intervention_score_ppm=600_000,
        min_delta_over_baseline_ppm=100_000,
        min_sample_count_per_capability=10,
        require_shared_holdout_set=True,
    )
    values.update(overrides)
    return FalsifierPolicy(**values)


class AgenticCoreFalsifierTests(unittest.TestCase):
    def test_complete_matched_four_capability_set_is_supported_only_at_component_scope(self):
        report = evaluate_agentic_core(complete_evidence(), policy=policy(), report_id="report-1")
        self.assertEqual(report.verdict, SUPPORTED_AT_COMPONENT_SCOPE)
        self.assertEqual(report.reasons, ())
        self.assertEqual(report.min_capability_score_ppm, 700_000)
        self.assertEqual(report.min_delta_over_baseline_ppm, 400_000)
        self.assertEqual(report.total_sample_count, 80)
        self.assertEqual(report.total_success_count, 56)
        self.assertEqual(report.total_action_count, 240)
        self.assertEqual(report.external_arc_agi3_credit, 0)
        self.assertEqual(report.runtime_credit, 0)
        self.assertEqual(report.physical_grid10_credit, 0)
        self.assertEqual(report.gwt_jspace_credit, 0)
        self.assertEqual(report.effect_credit, 0)
        self.assertEqual(report.completion_credit, 0)
        self.assertFalse(report.whole_system_acceptance)

    def test_missing_capability_is_not_evaluable_not_false_success(self):
        values = complete_evidence()[:-1]
        report = evaluate_agentic_core(values, policy=policy(), report_id="report-missing")
        self.assertEqual(report.verdict, NOT_EVALUABLE)
        self.assertIn(f"MISSING_CAPABILITY:{PLANNING_EXECUTION}", report.reasons)

    def test_active_upstream_source_is_not_evaluable(self):
        values = list(complete_evidence())
        values[2] = evidence(GOAL_SETTING, state=ACTIVE)
        report = evaluate_agentic_core(tuple(values), policy=policy(), report_id="report-active")
        self.assertEqual(report.verdict, NOT_EVALUABLE)
        self.assertIn(f"SOURCE_NOT_ACCEPTED:{GOAL_SETTING}", report.reasons)

    def test_mixed_holdout_falsifies_cross_capability_claim(self):
        values = list(complete_evidence())
        values[1] = evidence(MODELING, holdout="heldout-family-B")
        report = evaluate_agentic_core(tuple(values), policy=policy(), report_id="report-mixed")
        self.assertEqual(report.verdict, FALSIFIED)
        self.assertIn("MIXED_HOLDOUT_SET", report.reasons)

    def test_duplicate_receipt_falsifies_independence(self):
        values = list(complete_evidence())
        duplicate = values[0].source_receipt_sha256
        values[1] = evidence(MODELING, receipt_override=duplicate)
        report = evaluate_agentic_core(tuple(values), policy=policy(), report_id="report-duplicate")
        self.assertEqual(report.verdict, FALSIFIED)
        self.assertIn("NONINDEPENDENT_DUPLICATE_RECEIPT", report.reasons)

    def test_score_and_delta_floors_are_both_fail_closed(self):
        values = list(complete_evidence())
        values[3] = evidence(PLANNING_EXECUTION, baseline=650_000, intervention=650_000)
        report = evaluate_agentic_core(tuple(values), policy=policy(), report_id="report-floor")
        self.assertEqual(report.verdict, FALSIFIED)
        self.assertIn(f"DELTA_BELOW_BASELINE_FLOOR:{PLANNING_EXECUTION}", report.reasons)

    def test_action_count_is_observational_not_an_efficiency_gate(self):
        low_action = complete_evidence()
        high_action = tuple(
            evidence(capability, actions=200_000_000)
            for capability in (EXPLORATION, MODELING, GOAL_SETTING, PLANNING_EXECUTION)
        )
        low_report = evaluate_agentic_core(low_action, policy=policy(), report_id="report-low-action")
        high_report = evaluate_agentic_core(high_action, policy=policy(), report_id="report-high-action")
        self.assertEqual(low_report.verdict, SUPPORTED_AT_COMPONENT_SCOPE)
        self.assertEqual(high_report.verdict, SUPPORTED_AT_COMPONENT_SCOPE)
        self.assertEqual(low_report.total_action_count, 240)
        self.assertEqual(high_report.total_action_count, 800_000_000)
        self.assertEqual(low_report.reasons, high_report.reasons)

    def test_capability_cannot_be_bound_to_wrong_workpackage(self):
        with self.assertRaisesRegex(AgenticCoreFalsifierError, "canonical source workpackage F2-WP-803"):
            CapabilityEvidence(
                CAPABILITY_EVIDENCE_SCHEMA,
                MODELING,
                "F2-WP-804",
                1,
                "wrong-binding",
                ACCEPTED,
                "scope",
                sha(1),
                sha(2),
                "benchmark",
                "holdout",
                "baseline",
                1,
                2,
                1,
                1,
                1,
            )

    def test_report_cannot_be_self_attested_by_constructor(self):
        with self.assertRaisesRegex(AgenticCoreFalsifierError, "must be created by evaluator API"):
            AgenticCoreReport(
                REPORT_SCHEMA,
                "forged-report",
                "policy",
                1,
                sha(1),
                (),
                SUPPORTED_AT_COMPONENT_SCOPE,
                (),
                None,
                None,
                0,
                0,
                0,
            )

    def test_boolean_is_not_accepted_as_integer_threshold(self):
        with self.assertRaises(AgenticCoreFalsifierError):
            policy(min_intervention_score_ppm=True)

    def test_input_order_does_not_change_evidence_binding(self):
        values = complete_evidence()
        a = evaluate_agentic_core(values, policy=policy(), report_id="same-report")
        b = evaluate_agentic_core(tuple(reversed(values)), policy=policy(), report_id="same-report")
        self.assertEqual(a.capability_evidence_sha256, b.capability_evidence_sha256)
        self.assertEqual(a.sha256(), b.sha256())


if __name__ == "__main__":
    unittest.main()
