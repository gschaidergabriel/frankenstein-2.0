from __future__ import annotations

from dataclasses import fields
import unittest

from frankenstein2.cognitive_agentic_core_falsifier import (
    ACCEPTED,
    CAPABILITY_EVIDENCE_SCHEMA,
    EXPLORATION,
    GOAL_SETTING,
    MODELING,
    PLANNING_EXECUTION,
    POLICY_SCHEMA,
    SUPPORTED_AT_COMPONENT_SCOPE,
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


def evidence(capability: str) -> CapabilityEvidence:
    index = CAP_INDEX[capability]
    return CapabilityEvidence(
        CAPABILITY_EVIDENCE_SCHEMA,
        capability,
        CAP_TO_WP[capability],
        1,
        f"claim-{capability.lower()}",
        ACCEPTED,
        f"{capability}_REPOSITORY_HOSTED_COMPONENT_CI_ONLY",
        sha(index),
        sha(index + 100),
        f"benchmark-distinct-family-{capability.lower()}",
        "ALIASED_SHARED_HOLDOUT_LABEL",
        f"baseline-{capability.lower()}",
        300_000,
        700_000,
        20,
        14,
        60,
    )


class WP807SharedFamilyAliasFalsifier(unittest.TestCase):
    """REVIEW_ONLY executable witness for the current WP807 family-binding gap.

    Green means the negative control reproduced. The current evidence ABI has no
    provenance-bound shared fixture/task-family digest. Four distinct benchmark/source
    identities can therefore reuse the same caller-supplied holdout label and still be
    reported SUPPORTED_AT_COMPONENT_SCOPE when all score thresholds pass.

    This does NOT prove that canonical WP802-WP805 receipts actually come from mixed
    families. It grants no runtime, GRID10, GWT/J-Space, model, training, effect,
    completion, external benchmark, or whole-system credit.
    """

    def test_current_evidence_abi_has_no_provenance_bound_shared_family_digest(self) -> None:
        names = {field.name for field in fields(CapabilityEvidence)}
        self.assertNotIn("shared_fixture_family_sha256", names)

    def test_same_text_holdout_alias_still_supports_distinct_benchmark_identities(self) -> None:
        records = tuple(
            evidence(capability)
            for capability in (EXPLORATION, MODELING, GOAL_SETTING, PLANNING_EXECUTION)
        )
        self.assertEqual(len({item.benchmark_id for item in records}), 4)
        self.assertEqual(len({item.source_receipt_sha256 for item in records}), 4)
        self.assertEqual(len({item.source_reconciliation_sha256 for item in records}), 4)
        self.assertEqual({item.holdout_set_id for item in records}, {"ALIASED_SHARED_HOLDOUT_LABEL"})

        policy = FalsifierPolicy(
            POLICY_SCHEMA,
            "wp807-review-family-alias-policy",
            1,
            600_000,
            100_000,
            10,
            True,
        )
        report = evaluate_agentic_core(
            records,
            policy=policy,
            report_id="wp807-review-family-alias-report",
        )

        self.assertEqual(report.verdict, SUPPORTED_AT_COMPONENT_SCOPE)
        self.assertEqual(report.reasons, ())
        self.assertEqual(report.runtime_credit, 0)
        self.assertEqual(report.physical_grid10_credit, 0)
        self.assertEqual(report.gwt_jspace_credit, 0)
        self.assertFalse(report.whole_system_acceptance)


if __name__ == "__main__":
    unittest.main()
