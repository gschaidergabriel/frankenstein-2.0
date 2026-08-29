from __future__ import annotations

import unittest

from frankenstein2.target_completion_epistemics import (
    CompletionEpistemicsError,
    CompletionStatus,
    CounterevidenceProbe,
    FidelityLevel,
    ObligationStatus,
    PositiveReadback,
    TargetCompletionReport,
    TargetObligation,
)


def obligation(
    obligation_id: str,
    *,
    fidelity: FidelityLevel = FidelityLevel.T1_UBUNTU_USERSPACE,
    mandatory: bool = True,
    positive: PositiveReadback = PositiveReadback.UNKNOWN,
    counter: CounterevidenceProbe = CounterevidenceProbe.UNKNOWN,
) -> TargetObligation:
    return TargetObligation(
        obligation_id=obligation_id,
        target_id="host-a",
        required_fidelity=fidelity,
        mandatory=mandatory,
        positive_readback=positive,
        positive_evidence_refs=(f"readback:{obligation_id}",) if positive is not PositiveReadback.UNKNOWN else (),
        counterevidence_probe=counter,
        counterevidence_refs=(f"probe:{obligation_id}",) if counter is not CounterevidenceProbe.UNKNOWN else (),
    )


class TargetCompletionEpistemicsTests(unittest.TestCase):
    def test_missing_mandatory_evidence_is_unknown_not_pass(self) -> None:
        item = obligation("service-bound")
        report = TargetCompletionReport(
            target_id="host-a",
            evaluated_fidelity=FidelityLevel.T1_UBUNTU_USERSPACE,
            obligations=(item,),
        )
        self.assertIs(item.status, ObligationStatus.UNKNOWN)
        self.assertIs(report.status, CompletionStatus.UNKNOWN)
        self.assertEqual(report.unknown_obligation_ids, ("service-bound",))
        self.assertFalse(report.physical_credit)

    def test_positive_readback_without_counterevidence_probe_stays_unknown(self) -> None:
        item = obligation("host-adapter", positive=PositiveReadback.PASS)
        self.assertIs(item.status, ObligationStatus.UNKNOWN)

    def test_counterevidence_found_fails_even_with_positive_readback(self) -> None:
        item = obligation(
            "wrong-owner-probe",
            positive=PositiveReadback.PASS,
            counter=CounterevidenceProbe.FOUND,
        )
        report = TargetCompletionReport(
            target_id="host-a",
            evaluated_fidelity=FidelityLevel.T1_UBUNTU_USERSPACE,
            obligations=(item,),
        )
        self.assertIs(item.status, ObligationStatus.FAIL)
        self.assertIs(report.status, CompletionStatus.FAILED)
        self.assertEqual(report.failed_obligation_ids, ("wrong-owner-probe",))

    def test_complete_requires_all_mandatory_in_scope_to_pass_both_paths(self) -> None:
        report = TargetCompletionReport(
            target_id="host-a",
            evaluated_fidelity=FidelityLevel.T2_DEVICE_SESSION_FAULT_TWIN,
            obligations=(
                obligation("install", positive=PositiveReadback.PASS, counter=CounterevidenceProbe.CLEAR),
                obligation(
                    "session",
                    fidelity=FidelityLevel.T2_DEVICE_SESSION_FAULT_TWIN,
                    positive=PositiveReadback.PASS,
                    counter=CounterevidenceProbe.CLEAR,
                ),
                obligation("optional-debug", mandatory=False),
            ),
        )
        self.assertIs(report.status, CompletionStatus.COMPLETE)
        self.assertEqual(report.unknown_obligation_ids, ("optional-debug",))
        self.assertFalse(report.physical_credit)

    def test_future_fidelity_obligation_does_not_block_lower_scope(self) -> None:
        report = TargetCompletionReport(
            target_id="host-a",
            evaluated_fidelity=FidelityLevel.T1_UBUNTU_USERSPACE,
            obligations=(
                obligation("userspace", positive=PositiveReadback.PASS, counter=CounterevidenceProbe.CLEAR),
                obligation("physical-camera", fidelity=FidelityLevel.T4_PHYSICAL),
            ),
        )
        self.assertIs(report.status, CompletionStatus.COMPLETE)
        self.assertEqual(tuple(item.obligation_id for item in report.in_scope), ("userspace",))
        self.assertFalse(report.physical_completion_candidate)
        self.assertFalse(report.physical_credit)
        self.assertIn("physical-camera", report.canonical_json())

    def test_t4_evidence_can_only_form_candidate_not_physical_credit(self) -> None:
        report = TargetCompletionReport(
            target_id="host-a",
            evaluated_fidelity=FidelityLevel.T4_PHYSICAL,
            obligations=(
                obligation(
                    "physical-readback",
                    fidelity=FidelityLevel.T4_PHYSICAL,
                    positive=PositiveReadback.PASS,
                    counter=CounterevidenceProbe.CLEAR,
                ),
            ),
        )
        self.assertIs(report.status, CompletionStatus.COMPLETE)
        self.assertTrue(report.physical_completion_candidate)
        self.assertFalse(report.physical_credit)

    def test_t4_scope_without_t4_obligation_cannot_form_physical_candidate(self) -> None:
        report = TargetCompletionReport(
            target_id="host-a",
            evaluated_fidelity=FidelityLevel.T4_PHYSICAL,
            obligations=(
                obligation("userspace", positive=PositiveReadback.PASS, counter=CounterevidenceProbe.CLEAR),
            ),
        )
        self.assertIs(report.status, CompletionStatus.COMPLETE)
        self.assertFalse(report.physical_completion_candidate)
        self.assertFalse(report.physical_credit)

    def test_non_unknown_evidence_states_require_references(self) -> None:
        with self.assertRaises(CompletionEpistemicsError):
            TargetObligation(
                obligation_id="no-ref",
                target_id="host-a",
                required_fidelity=FidelityLevel.T1_UBUNTU_USERSPACE,
                mandatory=True,
                positive_readback=PositiveReadback.PASS,
            )
        with self.assertRaises(CompletionEpistemicsError):
            TargetObligation(
                obligation_id="no-probe-ref",
                target_id="host-a",
                required_fidelity=FidelityLevel.T1_UBUNTU_USERSPACE,
                mandatory=True,
                counterevidence_probe=CounterevidenceProbe.CLEAR,
            )

    def test_target_mismatch_and_duplicate_ids_fail_closed(self) -> None:
        good = obligation("a", positive=PositiveReadback.PASS, counter=CounterevidenceProbe.CLEAR)
        wrong_target = TargetObligation(
            obligation_id="b",
            target_id="host-b",
            required_fidelity=FidelityLevel.T1_UBUNTU_USERSPACE,
            mandatory=True,
        )
        with self.assertRaises(CompletionEpistemicsError):
            TargetCompletionReport(
                target_id="host-a",
                evaluated_fidelity=FidelityLevel.T1_UBUNTU_USERSPACE,
                obligations=(good, wrong_target),
            )
        with self.assertRaises(CompletionEpistemicsError):
            TargetCompletionReport(
                target_id="host-a",
                evaluated_fidelity=FidelityLevel.T1_UBUNTU_USERSPACE,
                obligations=(good, good),
            )

    def test_empty_report_is_rejected_not_vacuously_complete(self) -> None:
        with self.assertRaises(CompletionEpistemicsError):
            TargetCompletionReport(
                target_id="host-a",
                evaluated_fidelity=FidelityLevel.T0_CONTRACT,
                obligations=(),
            )


if __name__ == "__main__":
    unittest.main()
