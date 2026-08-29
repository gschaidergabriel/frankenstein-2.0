"""REVIEW_ONLY falsifier for F2-WP-1200 generation 1.

Physical-host credit must require at least one mandatory T4_PHYSICAL obligation with
independent positive readback and a clear counterevidence probe. Merely evaluating a
lower-fidelity obligation set at the T4 report level must not mint physical credit.
"""

from frankenstein2.target_completion_epistemics import (
    CompletionStatus,
    CounterevidenceProbe,
    FidelityLevel,
    PositiveReadback,
    TargetCompletionReport,
    TargetObligation,
)


def test_t4_evaluation_without_any_mandatory_t4_obligation_must_not_mint_physical_credit():
    userspace_only = TargetObligation(
        obligation_id="userspace-service-readback",
        target_id="host-a",
        required_fidelity=FidelityLevel.T1_UBUNTU_USERSPACE,
        mandatory=True,
        positive_readback=PositiveReadback.PASS,
        positive_evidence_refs=("readback:userspace-service",),
        counterevidence_probe=CounterevidenceProbe.CLEAR,
        counterevidence_refs=("probe:userspace-service",),
    )

    report = TargetCompletionReport(
        target_id="host-a",
        evaluated_fidelity=FidelityLevel.T4_PHYSICAL,
        obligations=(userspace_only,),
    )

    # Lower-fidelity scope can be complete on its own evidence, but this report contains
    # zero physical proof obligations. Therefore physical credit must remain false.
    assert report.status is CompletionStatus.COMPLETE
    assert report.physical_credit is False
