import pytest

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


def test_missing_mandatory_evidence_is_unknown_not_pass():
    item = obligation("service-bound")
    report = TargetCompletionReport(
        target_id="host-a",
        evaluated_fidelity=FidelityLevel.T1_UBUNTU_USERSPACE,
        obligations=(item,),
    )
    assert item.status is ObligationStatus.UNKNOWN
    assert report.status is CompletionStatus.UNKNOWN
    assert report.unknown_obligation_ids == ("service-bound",)
    assert report.physical_credit is False


def test_positive_readback_without_counterevidence_probe_stays_unknown():
    item = obligation("host-adapter", positive=PositiveReadback.PASS)
    assert item.status is ObligationStatus.UNKNOWN


def test_counterevidence_found_fails_even_when_positive_readback_passes():
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
    assert item.status is ObligationStatus.FAIL
    assert report.status is CompletionStatus.FAILED
    assert report.failed_obligation_ids == ("wrong-owner-probe",)


def test_complete_requires_all_mandatory_in_scope_to_pass_both_evidence_paths():
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
    assert report.status is CompletionStatus.COMPLETE
    assert report.unknown_obligation_ids == ("optional-debug",)
    assert report.physical_credit is False


def test_future_fidelity_obligation_does_not_block_lower_scope_but_is_preserved():
    report = TargetCompletionReport(
        target_id="host-a",
        evaluated_fidelity=FidelityLevel.T1_UBUNTU_USERSPACE,
        obligations=(
            obligation("userspace", positive=PositiveReadback.PASS, counter=CounterevidenceProbe.CLEAR),
            obligation("physical-camera", fidelity=FidelityLevel.T4_PHYSICAL),
        ),
    )
    assert report.status is CompletionStatus.COMPLETE
    assert tuple(item.obligation_id for item in report.in_scope) == ("userspace",)
    assert report.physical_credit is False
    assert "physical-camera" in report.canonical_json()


def test_t4_physical_credit_requires_complete_mandatory_t4_evidence():
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
    assert report.status is CompletionStatus.COMPLETE
    assert report.physical_credit is True


def test_pass_or_clear_cannot_be_asserted_without_evidence_reference():
    with pytest.raises(CompletionEpistemicsError):
        TargetObligation(
            obligation_id="no-ref",
            target_id="host-a",
            required_fidelity=FidelityLevel.T1_UBUNTU_USERSPACE,
            mandatory=True,
            positive_readback=PositiveReadback.PASS,
            counterevidence_probe=CounterevidenceProbe.UNKNOWN,
        )
    with pytest.raises(CompletionEpistemicsError):
        TargetObligation(
            obligation_id="no-probe-ref",
            target_id="host-a",
            required_fidelity=FidelityLevel.T1_UBUNTU_USERSPACE,
            mandatory=True,
            positive_readback=PositiveReadback.UNKNOWN,
            counterevidence_probe=CounterevidenceProbe.CLEAR,
        )


def test_target_mismatch_and_duplicate_obligation_ids_fail_closed():
    good = obligation("a", positive=PositiveReadback.PASS, counter=CounterevidenceProbe.CLEAR)
    wrong_target = TargetObligation(
        obligation_id="b",
        target_id="host-b",
        required_fidelity=FidelityLevel.T1_UBUNTU_USERSPACE,
        mandatory=True,
    )
    with pytest.raises(CompletionEpistemicsError):
        TargetCompletionReport(
            target_id="host-a",
            evaluated_fidelity=FidelityLevel.T1_UBUNTU_USERSPACE,
            obligations=(good, wrong_target),
        )
    with pytest.raises(CompletionEpistemicsError):
        TargetCompletionReport(
            target_id="host-a",
            evaluated_fidelity=FidelityLevel.T1_UBUNTU_USERSPACE,
            obligations=(good, good),
        )


def test_empty_report_rejected_not_vacuously_complete():
    with pytest.raises(CompletionEpistemicsError):
        TargetCompletionReport(
            target_id="host-a",
            evaluated_fidelity=FidelityLevel.T0_CONTRACT,
            obligations=(),
        )
