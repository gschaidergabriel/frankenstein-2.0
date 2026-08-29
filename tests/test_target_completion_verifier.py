#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from frankenstein2 import target_completion_verifier as tcv  # noqa: E402


PROFILE = "a" * 64
OTHER_PROFILE = "b" * 64


def obligation(
    obligation_id: str = "O-1",
    *,
    minimum_fidelity: str = "T2_DEVICE_SESSION_FAULT_TWIN",
    physical_required: bool = False,
) -> dict[str, object]:
    return {
        "schema": "FRANKENSTEIN2_TARGET_OBLIGATION/v1",
        "obligation_id": obligation_id,
        "target_profile_digest": PROFILE,
        "scope": "test",
        "description": "test obligation",
        "preconditions": [],
        "action": "exercise target path",
        "expected_observation": "independent readback succeeds",
        "positive_probe": {"probe_id": "positive"},
        "counterevidence_probes": [
            {"probe_id": "counter-1"},
            {"probe_id": "counter-2"},
        ],
        "restart_requirements": [],
        "fault_scenarios": [],
        "minimum_fidelity": minimum_fidelity,
        "physical_required": physical_required,
        "status": "NOT_RUN",
        "evidence_refs": [],
    }


def clear_negative_space() -> dict[str, str]:
    return {category: "CLEAR" for category in tcv.NEGATIVE_SPACE_CATEGORIES}


def observation(
    obligation_id: str = "O-1",
    *,
    profile: str = PROFILE,
    fidelity: str = "T2_DEVICE_SESSION_FAULT_TWIN",
    source_class: str = "OS_READBACK",
    positive_readback: str = "PASS",
    negative_space: dict[str, str] | None = None,
    counterevidence: dict[str, str] | None = None,
    evidence_refs: list[str] | None = None,
) -> dict[str, object]:
    return {
        "obligation_id": obligation_id,
        "target_profile_digest": profile,
        "fidelity": fidelity,
        "source_class": source_class,
        "positive_readback": positive_readback,
        "negative_space": clear_negative_space()
        if negative_space is None
        else negative_space,
        "counterevidence": {
            "counter-1": "CLEAR",
            "counter-2": "CLEAR",
        }
        if counterevidence is None
        else counterevidence,
        "evidence_refs": ["receipt:independent-readback"]
        if evidence_refs is None
        else evidence_refs,
    }


class TargetCompletionVerifierTests(unittest.TestCase):
    def test_all_independent_evidence_clear_is_complete_at_twin_scope(self) -> None:
        report = tcv.verify_target_obligations([obligation()], [observation()])
        self.assertEqual(report["status"], "COMPLETE_AT_TWIN_SCOPE")
        self.assertEqual(report["passed_count"], 1)
        self.assertFalse(report["whole_product_credit"])
        self.assertFalse(report["physical_host_credit"])
        self.assertEqual(
            report["physical_acceptance_minting"], "FORBIDDEN_IN_THIS_COMPONENT"
        )

    def test_missing_observation_is_unknown_not_pass(self) -> None:
        report = tcv.verify_target_obligations([obligation()], [])
        self.assertEqual(report["status"], "UNKNOWN")
        self.assertEqual(report["unknown_obligation_ids"], ["O-1"])
        self.assertIn("MISSING_OBSERVATION", report["obligations"][0]["reasons"])

    def test_installer_self_report_cannot_satisfy_independent_readback(self) -> None:
        report = tcv.verify_target_obligations(
            [obligation()], [observation(source_class="INSTALLER_SELF_REPORT")]
        )
        self.assertEqual(report["status"], "UNKNOWN")
        self.assertIn(
            "NON_INDEPENDENT_SELF_REPORT_SOURCE", report["obligations"][0]["reasons"]
        )

    def test_model_self_report_cannot_satisfy_independent_readback(self) -> None:
        report = tcv.verify_target_obligations(
            [obligation()], [observation(source_class="MODEL_SELF_REPORT")]
        )
        self.assertEqual(report["status"], "UNKNOWN")

    def test_detected_negative_space_defect_fails_obligation(self) -> None:
        negative = clear_negative_space()
        negative["wrong_user"] = "DETECTED"
        report = tcv.verify_target_obligations(
            [obligation()], [observation(negative_space=negative)]
        )
        self.assertEqual(report["status"], "DEGRADED")
        self.assertIn(
            "NEGATIVE_SPACE_WRONG_USER_DETECTED", report["obligations"][0]["reasons"]
        )

    def test_counterevidence_detection_fails_obligation(self) -> None:
        report = tcv.verify_target_obligations(
            [obligation()],
            [
                observation(
                    counterevidence={
                        "counter-1": "COUNTEREVIDENCE",
                        "counter-2": "CLEAR",
                    }
                )
            ],
        )
        self.assertEqual(report["status"], "DEGRADED")
        self.assertIn(
            "COUNTEREVIDENCE_DETECTED:counter-1",
            report["obligations"][0]["reasons"],
        )

    def test_missing_negative_space_category_is_unknown(self) -> None:
        negative = clear_negative_space()
        del negative["wrong_session"]
        report = tcv.verify_target_obligations(
            [obligation()], [observation(negative_space=negative)]
        )
        self.assertEqual(report["status"], "UNKNOWN")
        self.assertIn(
            "NEGATIVE_SPACE_WRONG_SESSION_MISSING",
            report["obligations"][0]["reasons"],
        )

    def test_missing_counterevidence_probe_is_unknown(self) -> None:
        report = tcv.verify_target_obligations(
            [obligation()],
            [observation(counterevidence={"counter-1": "CLEAR"})],
        )
        self.assertEqual(report["status"], "UNKNOWN")
        self.assertIn(
            "COUNTEREVIDENCE_PROBE_MISSING:counter-2",
            report["obligations"][0]["reasons"],
        )

    def test_profile_mismatch_is_unknown_not_current_target_credit(self) -> None:
        report = tcv.verify_target_obligations(
            [obligation()], [observation(profile=OTHER_PROFILE)]
        )
        self.assertEqual(report["status"], "UNKNOWN")
        self.assertIn(
            "TARGET_PROFILE_DIGEST_MISMATCH", report["obligations"][0]["reasons"]
        )

    def test_below_minimum_fidelity_is_unknown(self) -> None:
        report = tcv.verify_target_obligations(
            [obligation(minimum_fidelity="T3_TARGET_TRACE_REPLAY")],
            [observation(fidelity="T2_DEVICE_SESSION_FAULT_TWIN")],
        )
        self.assertEqual(report["status"], "UNKNOWN")
        self.assertIn("BELOW_MINIMUM_FIDELITY", report["obligations"][0]["reasons"])

    def test_physical_required_remains_ready_for_physical_not_physically_accepted(self) -> None:
        report = tcv.verify_target_obligations(
            [obligation(physical_required=True)],
            [observation(fidelity="T2_DEVICE_SESSION_FAULT_TWIN")],
        )
        self.assertEqual(report["status"], "READY_FOR_PHYSICAL_ACCEPTANCE")
        self.assertEqual(report["physical_only_pending_obligation_ids"], ["O-1"])
        self.assertFalse(report["physical_host_credit"])

    def test_no_evidence_refs_is_unknown(self) -> None:
        report = tcv.verify_target_obligations(
            [obligation()], [observation(evidence_refs=[])]
        )
        self.assertEqual(report["status"], "UNKNOWN")
        self.assertIn("NO_EVIDENCE_REFS", report["obligations"][0]["reasons"])

    def test_unexpected_observation_for_undeclared_obligation_is_negative_space_unknown(self) -> None:
        report = tcv.verify_target_obligations(
            [obligation()], [observation(), observation(obligation_id="O-UNDECLARED")]
        )
        self.assertEqual(report["status"], "UNKNOWN")
        self.assertEqual(report["unexpected_observation_ids"], ["O-UNDECLARED"])

    def test_duplicate_obligation_id_fails_closed(self) -> None:
        with self.assertRaisesRegex(
            tcv.TargetCompletionVerificationError, "duplicate obligation_id"
        ):
            tcv.verify_target_obligations([obligation(), obligation()], [observation()])

    def test_counter_probe_without_explicit_id_has_deterministic_index_key(self) -> None:
        item = obligation()
        item["counterevidence_probes"] = [{"kind": "probe"}]
        obs = observation(counterevidence={"counterevidence[0]": "CLEAR"})
        report = tcv.verify_target_obligations([item], [obs])
        self.assertEqual(report["status"], "COMPLETE_AT_TWIN_SCOPE")

    def test_report_digest_is_deterministic(self) -> None:
        first = tcv.verify_target_obligations([obligation()], [observation()])
        second = tcv.verify_target_obligations([obligation()], [observation()])
        self.assertEqual(first["report_digest"], second["report_digest"])
        self.assertEqual(len(first["report_digest"]), 64)


if __name__ == "__main__":
    unittest.main()
