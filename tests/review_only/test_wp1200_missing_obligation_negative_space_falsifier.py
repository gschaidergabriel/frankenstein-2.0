"""REVIEW_ONLY falsifier for F2-WP-1200 generation 1.

This test intentionally demonstrates that the current TargetCompletionReport can mint
T4 physical completion from a subset of obligations because it has no bound expected
obligation manifest / required-obligation universe.
"""

from frankenstein2.target_completion_epistemics import (
    CompletionStatus,
    CounterevidenceProbe,
    FidelityLevel,
    PositiveReadback,
    TargetCompletionReport,
    TargetObligation,
)


def test_t4_physical_credit_requires_declared_complete_obligation_universe():
    only_t0_obligation = TargetObligation(
        obligation_id="contract-present",
        target_id="target-host-A",
        required_fidelity=FidelityLevel.T0_CONTRACT,
        mandatory=True,
        positive_readback=PositiveReadback.PASS,
        positive_evidence_refs=("readback:t0-contract",),
        counterevidence_probe=CounterevidenceProbe.CLEAR,
        counterevidence_refs=("probe:t0-contract-negative-space",),
    )

    report = TargetCompletionReport(
        target_id="target-host-A",
        evaluated_fidelity=FidelityLevel.T4_PHYSICAL,
        obligations=(only_t0_obligation,),
    )

    # Contract expectation: omitted mandatory T1-T4 obligations are missing evidence,
    # therefore the T4 report must remain UNKNOWN and must not mint physical credit.
    assert report.status is CompletionStatus.UNKNOWN
    assert report.physical_credit is False
