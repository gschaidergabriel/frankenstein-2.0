"""REVIEW_ONLY falsifier for F2-WP-1200 evidence-path independence.

The owner acceptance contract requires each mandatory target obligation to have an
independent positive readback and counterevidence probe. Reusing the same evidence
identity for both paths must therefore never be sufficient to mint PASS.
"""
from frankenstein2.target_completion_epistemics import (
    CounterevidenceProbe,
    FidelityLevel,
    ObligationStatus,
    PositiveReadback,
    TargetObligation,
)


def main() -> None:
    shared_ref = "evidence:single-self-confirming-observation"
    item = TargetObligation(
        obligation_id="independent-readback-and-probe",
        target_id="host-a",
        required_fidelity=FidelityLevel.T1_UBUNTU_USERSPACE,
        mandatory=True,
        positive_readback=PositiveReadback.PASS,
        positive_evidence_refs=(shared_ref,),
        counterevidence_probe=CounterevidenceProbe.CLEAR,
        counterevidence_refs=(shared_ref,),
    )
    if item.status is ObligationStatus.PASS:
        raise AssertionError(
            "F2-WP-1200 accepted one shared evidence identity as both positive readback "
            "and independent counterevidence probe; expected fail-closed non-PASS"
        )


if __name__ == "__main__":
    main()
